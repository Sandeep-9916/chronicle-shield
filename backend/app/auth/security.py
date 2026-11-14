import jwt
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from backend.app.config import settings

security_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: str
    email: Optional[str] = None
    role: Optional[str] = "authenticated"


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> CurrentUser:
    """
    Extracts and cryptographically validates user identity from the Supabase JWT.
    Enforces Rule 5: User identity must come strictly from verified JWT, never request body.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Decode and verify Supabase JWT
        # In production, Supabase signs JWTs with the project JWT Secret using HS256
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}  # Supabase tokens may omit or customize audience
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
            role=payload.get("role", "authenticated")
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

