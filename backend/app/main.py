from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import engine, Base
from backend.app.routers import cases, evidence, verify

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Chronicle Shield - AI Digital Evidence Platform (Module 1)",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(verify.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": "1.0.0"}

