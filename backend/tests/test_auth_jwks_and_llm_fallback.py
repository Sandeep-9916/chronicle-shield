import json
import time
from datetime import datetime, timezone, timedelta
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from backend.app.config import settings
from backend.app.auth.security import get_current_user, jwks_cache, CurrentUser
import backend.llm as llm_mod


@pytest.fixture(scope="module")
def rsa_key_pair():
    """Generates an RSA 2048 keypair and matching JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk_dict = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = "test-rsa-kid-1"
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"
    return private_key, jwk_dict


@pytest.fixture(scope="module")
def ec_key_pair():
    """Generates an ECDSA P-256 keypair and matching JWK."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    jwk_dict = json.loads(ECAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = "test-ec-kid-1"
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "ES256"
    return private_key, jwk_dict


@pytest.fixture(autouse=True)
def setup_jwks_and_llm(rsa_key_pair, ec_key_pair):
    """Sets up mock JWKS in cache and resets mock handlers."""
    _, rsa_jwk = rsa_key_pair
    _, ec_jwk = ec_key_pair
    mock_jwks = {"keys": [rsa_jwk, ec_jwk]}
    jwks_cache.set_mock_jwks(mock_jwks)
    llm_mod.clear_mock_handlers()
    yield
    jwks_cache.clear()
    llm_mod.clear_mock_handlers()


# ============================================================================
# 1. AUTH JWKS TESTS (RS256, ES256, AUDIENCE, CACHING, ROTATION, HS256 FALLBACK)
# ============================================================================


def test_verify_rs256_token_success(rsa_key_pair):
    """Verifies RS256 token with audience='authenticated' against Supabase JWKS."""
    rsa_priv, _ = rsa_key_pair
    payload = {
        "sub": "user-rs256-1234",
        "email": "rs256@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, rsa_priv, algorithm="RS256", headers={"kid": "test-rsa-kid-1"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user(creds)
    assert user.id == "user-rs256-1234"
    assert user.email == "rs256@example.com"
    assert user.role == "authenticated"


def test_verify_es256_token_success(ec_key_pair):
    """Verifies ES256 token with audience='authenticated' against Supabase JWKS."""
    ec_priv, _ = ec_key_pair
    payload = {
        "sub": "user-es256-5678",
        "email": "es256@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, ec_priv, algorithm="ES256", headers={"kid": "test-ec-kid-1"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user(creds)
    assert user.id == "user-es256-5678"
    assert user.email == "es256@example.com"
    assert user.role == "authenticated"


def test_asymmetric_token_invalid_audience_rejected(rsa_key_pair):
    """Tokens with audience other than 'authenticated' must be rejected with 401."""
    rsa_priv, _ = rsa_key_pair
    payload = {
        "sub": "user-bad-aud",
        "email": "bad_aud@example.com",
        "aud": "public-or-untrusted-aud",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, rsa_priv, algorithm="RS256", headers={"kid": "test-rsa-kid-1"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(Exception) as exc_info:
        get_current_user(creds)
    assert exc_info.value.status_code == 401
    assert "audience" in exc_info.value.detail.lower() or "invalid" in exc_info.value.detail.lower()


def test_asymmetric_token_expired_rejected(ec_key_pair):
    """Expired ES256/RS256 token must be rejected with 401 'Token has expired'."""
    ec_priv, _ = ec_key_pair
    payload = {
        "sub": "user-expired",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    }
    token = jwt.encode(payload, ec_priv, algorithm="ES256", headers={"kid": "test-ec-kid-1"})

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(Exception) as exc_info:
        get_current_user(creds)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_jwks_in_memory_caching_and_rotation(rsa_key_pair):
    """In-memory cache serves keys without refetching, and triggers refetch on unknown kid."""
    rsa_priv, rsa_jwk = rsa_key_pair

    # Initial state has test-rsa-kid-1
    assert jwks_cache.jwk_set is not None
    initial_fetch_time = jwks_cache.last_fetched

    # Token with known kid hits cache
    payload = {"sub": "user-cached", "aud": "authenticated", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    token = jwt.encode(payload, rsa_priv, algorithm="RS256", headers={"kid": "test-rsa-kid-1"})
    get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert jwks_cache.last_fetched == initial_fetch_time

    # Simulate key rotation by generating a second key and updating mock source
    new_rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_jwk = json.loads(RSAAlgorithm.to_jwk(new_rsa.public_key()))
    new_jwk["kid"] = "rotated-kid-2"
    new_jwk["use"] = "sig"
    new_jwk["alg"] = "RS256"

    # Set mock source to contain the rotated key
    jwks_cache._mock_jwk_dict = {"keys": [rsa_jwk, new_jwk]}

    # Token signed with new rotated kid should trigger fetch and succeed
    token_rotated = jwt.encode(payload, new_rsa, algorithm="RS256", headers={"kid": "rotated-kid-2"})
    user_rot = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_rotated))
    assert user_rot.id == "user-cached"


def test_hs256_symmetric_fallback_success():
    """HS256 tokens signed with SUPABASE_JWT_SECRET continue to verify via fallback."""
    payload = {
        "sub": "user-hs256-legacy",
        "email": "legacy@example.com",
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = get_current_user(creds)
    assert user.id == "user-hs256-legacy"
    assert user.email == "legacy@example.com"


def test_hs256_wrong_secret_fails():
    """HS256 token signed with wrong secret must fail with 401."""
    payload = {
        "sub": "user-attacker",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "completely-wrong-secret-signature", algorithm="HS256")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(Exception) as exc_info:
        get_current_user(creds)
    assert exc_info.value.status_code == 401


# ============================================================================
# 2. LLM RETRIES (500, 502, 503, 504) AND LLM_FALLBACK_MODEL TESTS
# ============================================================================


def test_llm_retries_on_500_transient_error(monkeypatch):
    """llm.py retries on HTTP 500, 502, 503, 504 transient errors before succeeding."""
    call_count = 0

    def mock_handler_with_flakiness(prompt, schema, model):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Simulate transient 503 / 500 failure
            err = Exception("HTTP 503 Service Unavailable: High server load")
            setattr(err, "status_code", 503)
            raise err
        return {"status": "ok", "recovered": True}

    llm_mod.register_mock_handler(mock_handler_with_flakiness)

    # Fast backoff for test speed
    monkeypatch.setattr(time, "sleep", lambda s: None)

    settings.LLM_MODEL = "test-primary-model"
    settings.LLM_FALLBACK_MODEL = ""

    prompt_text = f"test transient failure retry prompt {time.time_ns()}"
    result = llm_mod.ask_llm(prompt_text, None)
    assert result == {"status": "ok", "recovered": True}
    assert call_count == 3  # Succeeded on 3rd attempt after 2 retries


def test_llm_fallback_model_tried_once_when_primary_fails(monkeypatch):
    """When primary model keeps failing, LLM_FALLBACK_MODEL is tried once and succeeds."""
    primary_calls = 0
    fallback_calls = 0

    def mock_handler_with_fallback(prompt, schema, model):
        nonlocal primary_calls, fallback_calls
        if model == "main-failing-model":
            primary_calls += 1
            err = Exception("HTTP 500 Internal Server Error: Model crashed")
            setattr(err, "status_code", 500)
            raise err
        elif model == "backup-fallback-model":
            fallback_calls += 1
            return {"status": "ok", "served_by": "fallback_model"}
        return None

    llm_mod.register_mock_handler(mock_handler_with_fallback)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    settings.LLM_MODEL = "main-failing-model"
    settings.LLM_FALLBACK_MODEL = "backup-fallback-model"

    prompt_text = f"test fallback model execution prompt {time.time_ns()}"
    result = llm_mod.ask_llm(prompt_text, None)

    assert result == {"status": "ok", "served_by": "fallback_model"}
    # Primary model retried and failed
    assert primary_calls >= 1
    # Fallback model was tried exactly once
    assert fallback_calls == 1

    # Second call should hit the database cache
    result_cached = llm_mod.ask_llm(prompt_text, None)
    assert result_cached == {"status": "ok", "served_by": "fallback_model"}
    # No extra calls made because it was cached
    assert fallback_calls == 1


def test_llm_fails_when_both_primary_and_fallback_fail(monkeypatch):
    """When both primary and fallback fail, exception is raised."""
    def always_fails(prompt, schema, model):
        err = Exception(f"HTTP 502 Bad Gateway: {model} unavailable")
        setattr(err, "status_code", 502)
        raise err

    llm_mod.register_mock_handler(always_fails)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    settings.LLM_MODEL = "broken-primary"
    settings.LLM_FALLBACK_MODEL = "broken-fallback"

    with pytest.raises(Exception) as exc_info:
        llm_mod.ask_llm("always failing prompt", None)

    assert "502" in str(exc_info.value)
