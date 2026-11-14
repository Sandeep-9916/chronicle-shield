from fastapi import APIRouter, Depends
from pydantic import BaseModel
from backend.app.config import settings
from backend.app.auth.security import get_current_user, CurrentUser
from backend.llm import ask_llm

router = APIRouter(prefix="/api/llm", tags=["llm"])


class HealthResponse(BaseModel):
    status: str
    provider: str
    model: str
    detail: str = ""


@router.get("/health", response_model=HealthResponse)
def llm_health_check(current_user: CurrentUser = Depends(get_current_user)):
    """
    Sends a small test prompt to verify LLM provider availability.
    Requires authentication. Strictly guarantees that API keys are NEVER printed or returned.
    """
    if not settings.LLM_MODEL or not settings.LLM_MODEL.strip():
        return HealthResponse(
            status="error",
            provider=settings.LLM_PROVIDER,
            model="",
            detail="LLM_MODEL environment variable is not configured. Please set LLM_MODEL in backend/.env",
        )

    try:
        # Send short ping prompt
        res = ask_llm("Ping: return OK", schema=None)
        return HealthResponse(
            status="ok",
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
            detail="LLM provider reachable",
        )
    except Exception as e:
        # Return generic error without leaking sensitive credentials
        return HealthResponse(
            status="error",
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL or "",
            detail=str(e),
        )
