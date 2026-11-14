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


def _compute_prompt_hash(prompt: str, schema_name: str) -> str:
    """Computes SHA-256 hash of provider + model + prompt + schema for database caching."""
    if not settings.LLM_MODEL or not settings.LLM_MODEL.strip():
        raise ValueError("LLM_MODEL environment variable is not configured. Please set LLM_MODEL in backend/.env")
    key = f"{settings.LLM_PROVIDER}::{settings.LLM_MODEL}::{prompt}::{schema_name}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _call_gemini(prompt: str, schema: Optional[Type[BaseModel]] = None) -> Any:
    """Calls Gemini API using google-genai SDK with exponential backoff on 429."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured in backend environment.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    config_kwargs = {
        "temperature": 0.0,
    }
    if schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = schema

    config = types.GenerateContentConfig(**config_kwargs)

    retries = 3
    backoff = 2.0
    last_err = None

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=prompt,
                config=config,
            )
            raw_text = response.text

            if schema:
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError as jde:
                    last_err = jde
                    time.sleep(1.0)
                    continue

            return raw_text
        except Exception as e:
            err_str = str(e).lower()
            last_err = e
            if "429" in err_str or "resourceexhausted" in err_str or "quota" in err_str:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            else:
                raise e

    raise RuntimeError(f"Gemini API request failed after {retries} retries: {str(last_err)}")


def _call_ollama(prompt: str, schema: Optional[Type[BaseModel]] = None) -> Any:
    """Calls local Ollama server."""
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": settings.LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    if schema:
        payload["format"] = "json"

    retries = 3
    backoff = 2.0
    last_err = None

    for attempt in range(retries):
        try:
            res = httpx.post(url, json=payload, timeout=60.0)
            if res.status_code == 429:
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
                    time.sleep(1.0)
                    continue
            return response_text
        except Exception as e:
            last_err = e
            time.sleep(backoff)
            backoff *= 2.0

    raise RuntimeError(f"Ollama request failed after {retries} retries: {str(last_err)}")


def _call_mock(prompt: str, schema: Optional[Type[BaseModel]] = None) -> Any:
    """Mock LLM provider for deterministic offline testing."""
    for handler in reversed(_mock_handlers):
        res = handler(prompt, schema)
        if res is not None:
            return res

    # Default mock responses
    if "health" in prompt.lower() or "say ok" in prompt.lower() or "ping" in prompt.lower():
        if schema:
            return {"status": "ok", "message": "OK"}
        return "OK"

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


def ask_llm(prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[Dict[str, Any], str]:
    """
    Centralized LLM gateway (Module 3).
    Strict Non-Negotiable Requirements:
    1. Reads provider from env LLM_PROVIDER (gemini default, ollama, or mock).
    2. Temperature 0.
    3. Retries with backoff on 429 and invalid JSON.
    4. Caches every response in the database keyed by a SHA-256 hash of the prompt.
    5. Never logs API keys or evidence text.
    """
    schema_name = schema.__name__ if schema else ""
    prompt_hash = _compute_prompt_hash(prompt, schema_name)

    # 1. Check Database Cache
    db: Session = SessionLocal()
    try:
        cached = db.query(LLMCache).filter(LLMCache.prompt_hash == prompt_hash).first()
        if cached is not None:
            return cached.response_json
    finally:
        db.close()

    # 2. Cache Miss: Dispatch to Provider
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "mock":
        response_data = _call_mock(prompt, schema)
    elif provider == "gemini":
        response_data = _call_gemini(prompt, schema)
    elif provider == "ollama":
        response_data = _call_ollama(prompt, schema)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: gemini, ollama, mock")

    # 3. Store in Database Cache
    db = SessionLocal()
    try:
        new_cache = LLMCache(
            prompt_hash=prompt_hash,
            provider=provider,
            model=settings.LLM_MODEL,
            response_json=response_data,
        )
        db.merge(new_cache)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    return response_data
