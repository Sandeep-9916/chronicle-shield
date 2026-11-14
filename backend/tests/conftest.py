import os
import shutil
import tempfile
import jwt
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import settings
import backend.app.database as db_mod
import backend.app.services.processor as proc_mod
import backend.llm as llm_mod
import backend.app.routers.events as events_router_mod
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.services.storage import storage_service

# Test JWT Secret
TEST_JWT_SECRET = "test-secret-key-for-chronicle-shield-unit-tests-123"
settings.SUPABASE_JWT_SECRET = TEST_JWT_SECRET
settings.TESTING = True
settings.LLM_PROVIDER = "mock"
settings.LLM_MODEL = "mock-model"

USER_A_ID = "11111111-1111-4111-8111-111111111111"
USER_B_ID = "22222222-2222-4222-8222-222222222222"


def create_token_for_user(user_id: str, email: str = "test@example.com") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def user_a_headers():
    token = create_token_for_user(USER_A_ID, "user_a@test.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def user_b_headers():
    token = create_token_for_user(USER_B_ID, "user_b@test.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def db_session():
    # Use StaticPool with sqlite :memory: so all connections share the same in-memory DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    # Attach SQLite triggers that emulate PostgreSQL immutability triggers
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TRIGGER trg_test_audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(FAIL, 'Chronicle Shield security violation: audit_log is append-only and cannot be updated.');
            END;
        """))
        conn.execute(text("""
            CREATE TRIGGER trg_test_audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(FAIL, 'Chronicle Shield security violation: audit_log is append-only and cannot be deleted.');
            END;
        """))
        conn.commit()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Override SessionLocal across modules
    orig_db_session = db_mod.SessionLocal
    orig_proc_session = proc_mod.SessionLocal
    orig_llm_session = llm_mod.SessionLocal
    orig_events_session = events_router_mod.SessionLocal

    db_mod.SessionLocal = TestingSessionLocal
    proc_mod.SessionLocal = TestingSessionLocal
    llm_mod.SessionLocal = TestingSessionLocal
    events_router_mod.SessionLocal = TestingSessionLocal

    # Configure temporary storage directory
    temp_dir = tempfile.mkdtemp()
    storage_service.local_dir = temp_dir
    storage_service.client = None

    yield session

    session.close()
    db_mod.SessionLocal = orig_db_session
    proc_mod.SessionLocal = orig_proc_session
    llm_mod.SessionLocal = orig_llm_session
    events_router_mod.SessionLocal = orig_events_session
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        session = db_mod.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
