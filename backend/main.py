"""
Crime Nexus API — Main Application Entry Point.
FastAPI application with case management and evidence upload capabilities.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)

from services.database import init_db
from api.cases import router as cases_router
from api.evidence import router as evidence_router
from api.audit import router as audit_router
from api.graph import router as graph_router
from api.auth import router as auth_router
from api.rag import router as rag_router
from api.devices import router as devices_router
from api.face import router as face_router
from api.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and Qdrant collection on startup."""
    await init_db()
    # Initialize Qdrant vector collection (idempotent)
    try:
        from services.vector_store import ensure_collection
        await ensure_collection()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Qdrant init skipped (is Qdrant running?): {e}")
    # Initialize face embeddings collection
    try:
        from services.face_recognition.qdrant_face_store import ensure_face_collection
        await ensure_face_collection()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Face Qdrant init skipped: {e}")
    yield


app = FastAPI(
    title="Crime Nexus API",
    description="AI-powered criminal intelligence platform for multi-modal evidence analysis",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server and production Vercel
frontend_url = os.environ.get("FRONTEND_URL", "https://sih-investigation.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Mount routers
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(f"DEBUG: Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

app.include_router(cases_router)
app.include_router(evidence_router)
app.include_router(audit_router)
app.include_router(graph_router)
app.include_router(auth_router)
app.include_router(rag_router)
app.include_router(devices_router)
app.include_router(face_router)
app.include_router(search_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.3.0"}
