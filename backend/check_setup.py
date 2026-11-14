"""
Chronicle Shield setup checker.

Run from the backend folder:   python check_setup.py

Checks backend/.env, the Gemini key and model, and Supabase (auth, storage,
database, RLS, audit_log trigger). Never prints secret values.
Uses only the standard library, plus SQLAlchemy (already in your backend).
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
TAGS = {"ok": "[OK]  ", "warn": "[WARN]", "bad": "[FAIL]"}
counts = {"ok": 0, "warn": 0, "bad": 0}
SECRETS = []


def say(level, msg):
    for s in SECRETS:
        if s and len(s) > 5:
            msg = msg.replace(s, "***")
    counts[level] += 1
    print(f"{TAGS[level]} {msg}")


def parse_env(path):
    vals = {}
    if not path.exists():
        return vals
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def _load(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except Exception:
        return raw.decode("utf-8", "replace")[:200] if raw else None


def http(method, url, headers=None, body=None, timeout=25):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _load(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _load(e.read())
    except Exception as e:  # network, DNS, timeout
        return 0, str(e)


def err_text(body):
    if isinstance(body, dict):
        e = body.get("error")
        if isinstance(e, dict):
            return str(e.get("message", e))[:200]
        for k in ("message", "msg", "error_description", "error"):
            if body.get(k):
                return str(body[k])[:200]
    return str(body)[:200]


def key_role(key):
    """Tell a service key from a public (anon) key without printing it."""
    if key.startswith("sb_secret_"):
        return "service"
    if key.startswith("sb_publishable_"):
        return "anon"
    if key.count(".") == 2:
        try:
            part = key.split(".")[1]
            part += "=" * (-len(part) % 4)
            role = json.loads(base64.urlsafe_b64decode(part)).get("role")
            return "service" if role == "service_role" else role
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- 1. .env
def check_env_file(env):
    print("\n== 1. backend/.env ==")
    if not (HERE / ".env").exists():
        say("bad", "backend/.env not found. Copy .env.example to .env and fill it in.")
        return
    say("ok", "backend/.env exists.")
    example = parse_env(HERE / ".env.example")
    if not example:
        say("warn", ".env.example not found, so variable names could not be compared.")
        return
    empty = [k for k in example if not env.get(k)]
    placeholders = [k for k, v in env.items()
                    if v.lower().startswith("your-") or "your-project" in v.lower()
                    or "yourpassword" in v.lower() or "your-supabase" in v.lower()]
    if placeholders:
        say("bad", "Still the template placeholder (replace with your real value): " + ", ".join(placeholders))
    unknown = [k for k in env if k not in example]
    if empty:
        say("warn", "Empty or missing in .env (names taken from .env.example): " + ", ".join(empty))
    else:
        say("ok", "Every variable listed in .env.example has a value.")
    if unknown:
        say("warn", "In .env but NOT in .env.example (a typo in a name is ignored by the app): " + ", ".join(unknown))


# ---------------------------------------------------------------- 2. Gemini
def check_gemini(env):
    print("\n== 2. Gemini ==")
    provider = env.get("LLM_PROVIDER", "")
    key = env.get("GEMINI_API_KEY", "")
    model = env.get("LLM_MODEL", "").replace("models/", "")
    SECRETS.append(key)

    if provider and provider != "gemini":
        say("warn", f"LLM_PROVIDER is '{provider}', so Gemini will NOT be used by the app.")
    elif not provider:
        say("warn", "LLM_PROVIDER is empty. Set LLM_PROVIDER=gemini explicitly.")
    else:
        say("ok", "LLM_PROVIDER=gemini")

    if not key:
        say("bad", "GEMINI_API_KEY is empty or the variable name does not match .env.example.")
        return
    if not key.startswith("AIza"):
        say("warn", "Key does not start with 'AIza'. Check you copied the whole key from Google AI Studio.")
    say("ok", f"GEMINI_API_KEY is set ({len(key)} characters).")

    headers = {"x-goog-api-key": key}
    st, body = http("GET", f"{GEMINI}/models?pageSize=200", headers)
    if st != 200:
        hints = {
            0: "No connection. Check your internet, VPN or firewall.",
            400: "Google rejected the key. It is wrong, cut off, or has extra characters.",
            403: "Key has no permission. Create a new key in Google AI Studio.",
            429: "Rate limit reached. Wait a minute and run again.",
        }
        say("bad", f"Could not list models (HTTP {st}). {hints.get(st, '')} Detail: {err_text(body)}")
        return
    models = body.get("models", []) if isinstance(body, dict) else []
    usable = [m["name"].replace("models/", "") for m in models
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    say("ok", f"Key accepted. {len(usable)} models can generate text.")

    flash = [m for m in usable if "flash" in m and "image" not in m and "tts" not in m][:10]
    if not model:
        say("bad", "LLM_MODEL is empty. Pick one of: " + ", ".join(flash))
        return
    if model not in usable:
        say("bad", f"LLM_MODEL '{model}' is not available to your key. Try one of: " + ", ".join(flash))
        return
    say("ok", f"Model '{model}' exists for your key.")

    st, body = http("POST", f"{GEMINI}/models/{model}:generateContent", headers, {
        "contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
        "generationConfig": {"temperature": 0},
    })
    if st == 200:
        say("ok", "Real test call worked. Gemini is ready.")
    elif st == 429:
        say("warn", "Key and model are valid, but the free-tier limit was hit. Wait a minute and retry.")
    elif st == 404:
        say("bad", f"Model '{model}' not found for generateContent. Detail: {err_text(body)}")
    else:
        say("bad", f"Test call failed (HTTP {st}). Detail: {err_text(body)}")


# ---------------------------------------------------------------- 3. Supabase API
def check_supabase(env):
    print("\n== 3. Supabase (auth + storage) ==")
    url = env.get("SUPABASE_URL", "").rstrip("/")
    key = (env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_KEY")
           or env.get("SUPABASE_KEY") or "")
    SECRETS.append(key)

    if not url:
        say("bad", "SUPABASE_URL is empty (or the name does not match .env.example).")
        return
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc.endswith(".supabase.co"):
        say("bad", "SUPABASE_URL should look like https://YOUR-PROJECT-REF.supabase.co")
        return
    if parsed.path not in ("", "/"):
        say("bad", f"SUPABASE_URL has extra path '{parsed.path}'. Remove it; keep only https://ref.supabase.co")
        return
    say("ok", f"SUPABASE_URL format looks right ({parsed.netloc}).")

    if not key:
        say("bad", "Service/secret key is empty (or the variable name does not match .env.example).")
        return
    role = key_role(key)
    if role == "anon":
        say("bad", "The backend key is the PUBLIC (anon/publishable) key. The backend needs the service/secret key.")
    elif role == "service":
        say("ok", "Backend key is a service/secret key.")
    else:
        say("warn", "Could not tell whether the backend key is a service key.")

    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key

    st, body = http("GET", f"{url}/auth/v1/health", headers)
    if st == 200:
        say("ok", "Supabase Auth is reachable with your key.")
    elif st == 0:
        say("bad", f"Cannot reach Supabase. Wrong project URL or no internet. Detail: {err_text(body)}")
        return
    elif st in (401, 403):
        say("bad", "Supabase rejected the key. Copy the key again from Project Settings, no spaces or quotes.")
        return
    else:
        say("warn", f"Auth health returned HTTP {st}: {err_text(body)}")

    st, body = http("GET", f"{url}/storage/v1/bucket", headers)
    if st == 200 and isinstance(body, list):
        if not body:
            say("warn", "No storage buckets found. Create the private evidence bucket "
                        "(run schema.sql, or Storage > New bucket), or the key may be the anon key.")
        for b in body:
            if b.get("public"):
                say("bad", f"Bucket '{b.get('name')}' is PUBLIC. Evidence buckets must be private.")
            else:
                say("ok", f"Bucket '{b.get('name')}' is private.")
    else:
        say("warn", f"Could not list buckets (HTTP {st}): {err_text(body)}")


# ---------------------------------------------------------------- 4. Database
def check_database(env):
    print("\n== 4. Supabase database ==")
    dburl = env.get("DATABASE_URL", "")
    SECRETS.append(dburl)
    if not dburl or dburl.startswith("sqlite"):
        say("warn", "DATABASE_URL is empty or SQLite. The app is using the LOCAL file "
                    "chronicle_shield.db, NOT Supabase. Put the Supabase connection string here.")
        return
    if dburl.startswith("postgres://"):
        say("bad", "DATABASE_URL starts with postgres://. Change it to postgresql:// (SQLAlchemy needs this).")
    if "[" in dburl or "]" in dburl:
        say("bad", "DATABASE_URL still contains [ ] brackets. Remove them and keep only the password.")

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
    except ImportError:
        say("warn", "SQLAlchemy is not installed in this Python. Activate your backend environment and rerun.")
        return
    try:
        u = make_url(dburl)
    except Exception:
        say("bad", "DATABASE_URL could not be parsed. A special character in the password "
                   "(@ # / : ?) usually causes this. Use a letters-and-numbers password.")
        return
    if u.password:
        SECRETS.append(u.password)
    host = u.host or "?"
    say("ok", f"Parsed DATABASE_URL: host={host}, port={u.port}, database={u.database}")
    if host.startswith("db.") and host.endswith(".supabase.co"):
        say("warn", "This is the Direct connection, which often fails on IPv4-only networks. "
                    "Use the Session pooler string instead.")
    if "@" in host:
        say("bad", "Host contains '@': the password has an @ in it. Reset to a simple password.")

    try:
        engine = create_engine(dburl, connect_args={"connect_timeout": 10})
        with engine.connect() as c:
            c.execute(text("select 1"))
            say("ok", "Connected to the database.")
            rows = c.execute(text(
                "select tablename, rowsecurity from pg_tables where schemaname='public' order by 1"
            )).fetchall()
            tables = {r[0]: bool(r[1]) for r in rows}
            if not tables:
                say("bad", "Connected, but there are NO tables. Run supabase/schema.sql in the SQL Editor.")
                return
            say("ok", "Tables found: " + ", ".join(tables))
            expected = ["cases", "evidence", "audit_log", "chunks", "events", "llm_cache"]
            missing = [t for t in expected if t not in tables]
            if missing:
                say("warn", "Expected tables not found: " + ", ".join(missing)
                    + ". Re-run schema.sql (or ask the agent for a migration).")
            no_rls = [t for t, on in tables.items() if not on]
            if no_rls:
                say("bad", "Row Level Security is OFF on: " + ", ".join(no_rls))
            else:
                say("ok", "RLS is enabled on every public table.")
            if "audit_log" in tables:
                trig = c.execute(text(
                    "select tgname from pg_trigger "
                    "where tgrelid = 'public.audit_log'::regclass and not tgisinternal"
                )).fetchall()
                if trig:
                    say("ok", "audit_log has triggers: " + ", ".join(t[0] for t in trig))
                else:
                    say("bad", "audit_log has NO trigger. UPDATE/DELETE are not blocked. Re-run schema.sql.")
    except Exception as e:
        msg = str(e)
        hint = ""
        low = msg.lower()
        if "password authentication failed" in low:
            hint = "Wrong database password. Reset it in Project Settings > Database."
        elif "tenant or user not found" in low:
            hint = "With the pooler, the username must be postgres.YOUR-PROJECT-REF."
        elif "could not translate host" in low or "getaddrinfo" in low or "name or service" in low:
            hint = "Host name is wrong, or direct connection needs IPv6. Use the Session pooler string."
        elif "timeout" in low or "timed out" in low:
            hint = "Network or firewall is blocking the connection."
        say("bad", f"Database connection failed. {hint} Detail: {msg.splitlines()[0][:220]}")


# ---------------------------------------------------------------- 5. Frontend env
def check_frontend(env):
    print("\n== 5. frontend/.env.local ==")
    path = HERE.parent / "frontend" / ".env.local"
    if not path.exists():
        say("warn", "frontend/.env.local not found. Create it from frontend/.env.example.")
        return
    fe = parse_env(path)
    backend_key = (env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_KEY") or "")
    leaked = False
    for k, v in fe.items():
        if v and ("SERVICE" in k.upper() or v.startswith("sb_secret_")
                  or (backend_key and v == backend_key) or key_role(v) == "service"):
            say("bad", f"'{k}' in the FRONTEND holds a service/secret key. Remove it; backend only.")
            leaked = True
    if not leaked:
        say("ok", "No service/secret key found in the frontend env.")
    furl = fe.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    burl = env.get("SUPABASE_URL", "").rstrip("/")
    if not furl:
        say("warn", "NEXT_PUBLIC_SUPABASE_URL is empty in the frontend.")
    elif burl and furl != burl:
        say("bad", "Frontend and backend point to DIFFERENT Supabase projects.")
    else:
        say("ok", "Frontend and backend use the same Supabase URL.")
    pub = (fe.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or fe.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
           or fe.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY") or "")
    if not pub:
        say("warn", "No public key in the frontend env (publishable or legacy anon). Login will not work without it.")
    else:
        kind = "NEW publishable key (sb_publishable_...)" if pub.startswith("sb_publishable_") \
            else "LEGACY anon key (eyJ...)" if key_role(pub) == "anon" else None
        if kind:
            say("ok", f"Frontend public key is a {kind}.")
        elif key_role(pub) != "service":
            say("warn", "Frontend public key format is not recognised. Copy the publishable (or legacy anon) key again.")
    api = fe.get("NEXT_PUBLIC_API_BASE_URL", "") or fe.get("NEXT_PUBLIC_API_URL", "")
    if api.endswith("/"):
        say("warn", "The API base URL ends with '/'. Remove the trailing slash.")
    elif api:
        say("ok", f"API base URL = {api}")
    else:
        say("warn", "NEXT_PUBLIC_API_BASE_URL is empty (expected something like http://localhost:8000).")


# ---------------------------------------------------------------- 6. JWT
def check_jwt(env):
    print("\n== 6. Login token (JWT) verification ==")
    url = env.get("SUPABASE_URL", "").rstrip("/")
    secret = env.get("SUPABASE_JWT_SECRET", "")
    SECRETS.append(secret)
    uses_new = None
    if url:
        st, body = http("GET", f"{url}/auth/v1/.well-known/jwks.json")
        if st == 200 and isinstance(body, dict):
            keys = body.get("keys", [])
            if keys:
                uses_new = True
                algs = sorted({k.get("alg", "?") for k in keys})
                say("ok", "Project publishes public signing keys (" + ", ".join(algs) + "): NEW JWT signing keys.")
            else:
                uses_new = False
                say("warn", "No public signing keys listed: the project probably still signs logins "
                            "with the LEGACY shared JWT secret (HS256).")
        else:
            say("warn", f"Could not read the signing-keys endpoint (HTTP {st}).")

    sec = HERE / "app" / "auth" / "security.py"
    if not sec.exists():
        say("warn", "backend/app/auth/security.py not found, so token verification was not inspected.")
        return
    code = sec.read_text(encoding="utf-8-sig").lower()
    asks_supabase = "auth/v1/user" in code or "get_user" in code
    has_jwks = "jwks" in code
    has_hs = "hs256" in code or "jwt_secret" in code
    if asks_supabase:
        say("ok", "Backend validates tokens by asking Supabase directly. Works with old and new keys.")
    elif uses_new and not has_jwks:
        say("bad", "Project uses NEW signing keys, but the backend only checks the shared secret (HS256). "
                   "Real logins will fail with 401. Ask the agent to verify via the JWKS endpoint "
                   "(ES256/RS256) and keep HS256 as a fallback.")
    elif uses_new is False and has_hs and not secret:
        say("bad", "Project uses the legacy secret, but SUPABASE_JWT_SECRET is empty. "
                   "Copy it from Project Settings > JWT Keys (legacy secret).")
    elif uses_new is None:
        say("warn", "Could not compare, because the signing-keys endpoint was unreachable. Rerun with internet.")
    elif has_jwks or has_hs:
        say("ok", "Backend token verification matches how your project signs tokens.")
    else:
        say("warn", "Could not tell how the backend verifies tokens. Ask the agent to explain security.py.")


def main():
    env = parse_env(HERE / ".env")
    check_env_file(env)
    check_gemini(env)
    check_supabase(env)
    check_database(env)
    check_frontend(env)
    check_jwt(env)
    print(f"\nSummary: {counts['ok']} ok, {counts['warn']} warnings, {counts['bad']} failures.")
    print("Restart the backend after any change to backend/.env.")
    sys.exit(1 if counts["bad"] else 0)


if __name__ == "__main__":
    main()
