import time
import logging
from typing import Optional, Dict, Any
import httpx
import jwt
from jwt import PyJWKSet, PyJWK
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from backend.app.config import settings

logger = logging.getLogger("chronicle_shield.auth")
security_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: Optional[str] = "authenticated"


class SupabaseJWKSCache:
    """
    Caches Supabase public signing keys retrieved from:
    {SUPABASE_URL}/auth/v1/.well-known/jwks.json

    Supports ES256 and RS256 token verification with in-memory caching and key rotation.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self.last_fetched: float = 0
        self.jwk_set: Optional[PyJWKSet] = None
        self._mock_jwk_dict: Optional[Dict[str, Any]] = None

    def set_mock_jwks(self, jwk_dict: Optional[Dict[str, Any]]):
        """Allows test fixtures to inject JWKS keys without external network calls."""
        self._mock_jwk_dict = jwk_dict
        if jwk_dict is not None:
            self.jwk_set = PyJWKSet.from_dict(jwk_dict)
            self.last_fetched = time.time()
        else:
            self.jwk_set = None
            self.last_fetched = 0

    def clear(self):
        """Resets the JWKS cache."""
        self.jwk_set = None
        self.last_fetched = 0
        self._mock_jwk_dict = None

    def fetch_jwks(self) -> PyJWKSet:
        """Fetches public JWKS keys from Supabase auth endpoint."""
        if self._mock_jwk_dict is not None:
            self.jwk_set = PyJWKSet.from_dict(self._mock_jwk_dict)
            self.last_fetched = time.time()
            return self.jwk_set

        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                res.raise_for_status()
                data = res.json()
                self.jwk_set = PyJWKSet.from_dict(data)
                self.last_fetched = time.time()
                return self.jwk_set
        except Exception as e:
            if self.jwk_set is not None:
                logger.warning(f"Failed to refresh JWKS from {url}, using cached keys: {e}")
                return self.jwk_set
            raise RuntimeError(f"Failed to fetch Supabase JWKS from {url}: {str(e)}")

    def get_signing_key_for_token(self, token: str) -> PyJWK:
        """Finds matching PyJWK key for a token using kid or algorithm, with rotation fallback."""
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")
        now = time.time()

        # If cache empty or TTL expired, fetch keys
        if self.jwk_set is None or (now - self.last_fetched) > self.ttl_seconds:
            self.fetch_jwks()

        # 1. Search by kid if available
        if kid and self.jwk_set:
            try:
                return self.jwk_set[kid]
            except KeyError:
                # Key rotation: re-fetch from Supabase once if kid was not in cache
                self.fetch_jwks()
                try:
                    return self.jwk_set[kid]
                except KeyError:
                    raise jwt.PyJWTError(f"Signing key with kid '{kid}' not found in Supabase JWKS")

        # 2. Search by matching algorithm if kid omitted
        if self.jwk_set:
            for k in self.jwk_set.keys:
                if getattr(k, "algorithm_name", None) == alg:
                    return k
            if len(self.jwk_set.keys) == 1:
                return self.jwk_set.keys[0]

        raise jwt.PyJWTError(f"No suitable key found in Supabase JWKS for token (alg: {alg}, kid: {kid})")


jwks_cache = SupabaseJWKSCache()


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> CurrentUser:
    """
    Extracts and cryptographically validates user identity from the Supabase JWT.
    Enforces Rule 5: User identity must come strictly from verified JWT, never request body.

    Supports:
    - Asymmetric ES256 and RS256 token verification using public keys from Supabase JWKS (audience="authenticated").
    - Symmetric HS256 token verification using SUPABASE_JWT_SECRET as a backward-compatible fallback.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = unverified_header.get("alg", "HS256")
    payload = None

    # 1. New Supabase Asymmetric Verification (ES256 / RS256 via JWKS)
    if alg in ("ES256", "RS256"):
        try:
            signing_key = jwks_cache.get_signing_key_for_token(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidAudienceError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience: must be 'authenticated'",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            # If asymmetric verification fails, attempt HS256 as fallback if configured
            if settings.SUPABASE_JWT_SECRET:
                try:
                    payload = jwt.decode(
                        token,
                        settings.SUPABASE_JWT_SECRET,
                        algorithms=["HS256"],
                        options={"verify_aud": False},
                    )
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Invalid authentication token: {str(e)}",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid authentication token: {str(e)}",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    # 2. Symmetric Fallback Verification (HS256 with SUPABASE_JWT_SECRET)
    else:
        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=str(user_id),
        email=payload.get("email"),
        role=payload.get("role", "authenticated"),
    )
