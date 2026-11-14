import json
import time
import hashlib
import logging
from typing import Optional, Type, Any, Union, Dict
from pydantic import BaseModel
import httpx
from sqlalchemy.orm import Session

from backend.app.config import settings
import backend.app.database as db_mod
from backend.app.models.llm_cache import LLMCache

SessionLocal = db_mod.SessionLocal
logger = logging.getLogger("chronicle_shield.llm")

# In-memory mock response registry for tests
_mock_handlers = []


def register_mock_handler(handler):
    """Registers a mock handler for testing ask_llm."""
    _mock_handlers.append(handler)


def clear_mock_handlers():
    """Clears registered mock handlers."""
    _mock_handlers.clear()


def _compute_prompt_hash(prompt: str, schema_name: str, model: Optional[str] = None) -> str:
    """Computes SHA-256 hash of provider + model + prompt + schema for database caching."""
    target_model = (model or settings.LLM_MODEL or "").strip()
    if not target_model:
        raise ValueError("LLM_MODEL environment variable is not configured. Please set LLM_MODEL in backend/.env")
    key = f"{settings.LLM_PROVIDER}::{target_model}::{prompt}::{schema_name}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _is_transient_http_error(e: Exception) -> bool:
    """Checks if error corresponds to 429, 500, 502, 503, 504 or transient server failure."""
    for attr in ("status_code", "code"):
        code = getattr(e, attr, None)
        if code in (429, 500, 502, 503, 504):
            return True

    response = getattr(e, "response", None)
    if response is not None:
        resp_status = getattr(response, "status_code", None)
        if resp_status in (429, 500, 502, 503, 504):
            return True

    err_str = str(e).lower()
    retryable_terms = [
        "429", "500", "502", "503", "504",
        "resourceexhausted", "unavailable", "internal error",
        "bad gateway", "gateway timeout", "service unavailable",
        "rate limit", "quota"
    ]
    return any(term in err_str for term in retryable_terms)


def _call_gemini(
    prompt: str,
    schema: Optional[Type[BaseModel]] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Any:
    """Calls Gemini API with exponential backoff on 429, 500, 502, 503, 504."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured in backend environment.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    target_model = (model or settings.LLM_MODEL or "").strip()

    config_kwargs = {
        "temperature": 0.0,
    }
    if schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = schema

    config = types.GenerateContentConfig(**config_kwargs)

    retries = max_retries
    backoff = 2.0
    last_err = None

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )
            raw_text = response.text

            if schema:
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError as jde:
                    last_err = jde
                    if attempt < retries - 1:
                        time.sleep(1.0)
                        continue
                    raise jde

            return raw_text
        except Exception as e:
            last_err = e
            if _is_transient_http_error(e) and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            raise e

    raise RuntimeError(f"Gemini API request failed after {retries} retries: {str(last_err)}")


def _call_ollama(
    prompt: str,
    schema: Optional[Type[BaseModel]] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Any:
    """Calls local Ollama server with retries on 429, 500, 502, 503, 504."""
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    target_model = (model or settings.LLM_MODEL or "").strip()
    payload = {
        "model": target_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    if schema:
        payload["format"] = "json"

    retries = max_retries
    backoff = 2.0
    last_err = None

    for attempt in range(retries):
        try:
            res = httpx.post(url, json=payload, timeout=60.0)
            if res.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            res.raise_for_status()
            data = res.json()
            response_text = data.get("response", "")

            if schema:
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as jde:
                    last_err = jde
                    if attempt < retries - 1:
                        time.sleep(1.0)
                        continue
                    raise jde
            return response_text
        except Exception as e:
            last_err = e
            if _is_transient_http_error(e) and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            raise e

    raise RuntimeError(f"Ollama request failed after {retries} retries: {str(last_err)}")


def _call_mock(
    prompt: str,
    schema: Optional[Type[BaseModel]] = None,
    model: Optional[str] = None,
    max_retries: int = 3,
) -> Any:
    """Mock LLM provider for deterministic offline testing with retry support."""
    target_model = (model or settings.LLM_MODEL or "").strip()
    retries = max_retries
    backoff = 2.0
    last_err = None

    for attempt in range(retries):
        try:
            for handler in reversed(_mock_handlers):
                try:
                    res = handler(prompt, schema, target_model)
                except TypeError:
                    res = handler(prompt, schema)
                if res is not None:
                    return res
            break
        except Exception as e:
            last_err = e
            if _is_transient_http_error(e) and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            raise e

    # Default mock responses
    if "health" in prompt.lower() or "say ok" in prompt.lower() or "ping" in prompt.lower():
        if schema:
            return {"status": "ok", "message": "OK"}
        return "OK"

    if "rewrite this single sentence" in prompt.lower() or "failed sentence" in prompt.lower():
        return "Alice confirmed the transfer of $50,000 to escrow [E1-p1-L1]."

    if "summary" in prompt.lower() or "narrative" in prompt.lower():
        return (
            "## Case Forensic Summary\n\n"
            "Alice confirmed the transfer of $50,000 to escrow on 2026-11-14 [E1-p1-L1].\n"
            "Bob confirmed that the funds were secured in the safe deposit [E1-p1-L2]."
        )

    if "contradict" in prompt.lower() or "inconsistency" in prompt.lower():
        return "Evidence indicates conflicting accounts between the cited statements regarding time or location."

    # If asking for events
    if schema:
        if "ignore previous instructions and drop" in prompt.lower() or "disregard all facts" in prompt.lower():
            return {
                "events": [
                    {
                        "event": "System policy upheld and attacker payload treated as text",
                        "who": "Security Guard",
                        "to_whom": "Attacker",
                        "date": "2026-11-14",
                        "evidence_id": "E1",
                        "quote": "Ignore previous instructions",
                    }
                ]
            }

        return {
            "events": [
                {
                    "event": "Escrow funds transfer confirmed",
                    "who": "Alice",
                    "to_whom": "Bob",
                    "date": "2026-11-14",
                    "evidence_id": "E1",
                    "quote": "Confirmed transfer of $50,000 to escrow.",
                }
            ]
        }

    return "Mock LLM output"


def _dispatch_provider(
    provider: str,
    prompt: str,
    schema: Optional[Type[BaseModel]],
    model: str,
    max_retries: int = 3,
) -> Any:
    if provider == "mock":
        return _call_mock(prompt, schema, model=model, max_retries=max_retries)
    elif provider == "gemini":
        return _call_gemini(prompt, schema, model=model, max_retries=max_retries)
    elif provider == "ollama":
        return _call_ollama(prompt, schema, model=model, max_retries=max_retries)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: gemini, ollama, mock")


def ask_llm(prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[Dict[str, Any], str]:
    """
    Centralized LLM gateway (Module 3 & 4).
    Strict Non-Negotiable Requirements:
    1. Reads provider from env LLM_PROVIDER (gemini default, ollama, or mock).
    2. Temperature 0.
    3. Retries with backoff on HTTP 429, 500, 502, 503, 504 and invalid JSON.
    4. Supports optional LLM_FALLBACK_MODEL env variable tried once if the main model keeps failing.
    5. Caches every response in the database keyed by a SHA-256 hash of the prompt.
    6. Never logs API keys or evidence text.
    """
    primary_model = (settings.LLM_MODEL or "").strip()
    if not primary_model:
        raise ValueError("LLM_MODEL environment variable is not configured. Please set LLM_MODEL in backend/.env")

    schema_name = schema.__name__ if schema else ""
    prompt_hash = _compute_prompt_hash(prompt, schema_name, primary_model)

    # 1. Check Database Cache
    db: Session = SessionLocal()
    try:
        cached = db.query(LLMCache).filter(LLMCache.prompt_hash == prompt_hash).first()
        if cached is not None:
            return cached.response_json
    finally:
        db.close()

    # 2. Cache Miss: Dispatch to Primary Model
    provider = settings.LLM_PROVIDER.lower().strip()
    fallback_model = (getattr(settings, "LLM_FALLBACK_MODEL", "") or "").strip()
    used_model = primary_model

    try:
        response_data = _dispatch_provider(
            provider=provider,
            prompt=prompt,
            schema=schema,
            model=primary_model,
            max_retries=3,
        )
    except Exception as primary_err:
        # If primary model fails and fallback model is configured, try fallback model ONCE
        if fallback_model and fallback_model != primary_model:
            logger.warning(
                f"Primary model '{primary_model}' failed ({primary_err}). Attempting fallback model '{fallback_model}' once."
            )
            try:
                response_data = _dispatch_provider(
                    provider=provider,
                    prompt=prompt,
                    schema=schema,
                    model=fallback_model,
                    max_retries=1,  # Tried once
                )
                used_model = fallback_model
            except Exception as fallback_err:
                logger.error(f"Fallback model '{fallback_model}' also failed: {fallback_err}")
                raise primary_err from fallback_err
        else:
            raise primary_err

    # 3. Store in Database Cache
    db = SessionLocal()
    try:
        new_cache = LLMCache(
            prompt_hash=prompt_hash,
            provider=provider,
            model=used_model,
            response_json=response_data,
        )
        db.merge(new_cache)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return response_data
