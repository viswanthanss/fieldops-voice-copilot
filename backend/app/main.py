# -*- coding: utf-8 -*-
"""
FastAPI application entry point for FieldOps Voice Copilot backend.

Security pipeline (per request):
  1. CORS check (middleware)
  2. Rate limit check (slowapi middleware)
  3. JWT auth + user resolution (Depends)
  4. Authorization context derivation (server-side, not client-supplied)
  5. Input validation (Pydantic schemas)
  6. Business logic
  7. Server-side audit logging (never trust browser-submitted records)
"""
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, assets as asset_service, privacy as privacy_service
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db import create_tables, get_db
from app.models import Asset, Feedback, User
from app.rate_limit import limiter
from app.sessions import initialize_session
from app.telemetry import setup_telemetry

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup; clean up on shutdown."""
    if settings.ENVIRONMENT == "production" and settings.SECRET_KEY.startswith("dev-"):
        logger.critical("FATAL: Weak SECRET_KEY detected in production. Aborting.")
        raise RuntimeError("Production SECRET_KEY must not use the development default.")
    await create_tables()
    logger.info("FieldOps backend started -- environment=%s", settings.ENVIRONMENT)
    yield
    logger.info("FieldOps backend shutting down.")


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="FieldOps Voice Copilot API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

# ── Telemetry ─────────────────────────────────────────────────────────────────
setup_telemetry(app)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Security headers middleware ────────────────────────────────────────────────


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Inject security headers on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


# ── Request size limiter ───────────────────────────────────────────────────────


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    """Reject requests with bodies larger than 1 MB."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_048_576:
        return JSONResponse({"detail": "Request body too large (max 1 MB)"}, status_code=413)
    return await call_next(request)


# ── User email state middleware (for rate-limit key) ──────────────────────────


@app.middleware("http")
async def extract_user_state(request: Request, call_next):
    """
    If a valid Bearer token is present, store the user email in request.state
    so the rate limiter can key on it rather than IP.
    """
    request.state.user_email = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.auth import verify_token

            payload = verify_token(auth_header[7:])
            request.state.user_email = payload.get("email")
        except Exception:
            pass
    return await call_next(request)


# ── Error handler (production-safe) ───────────────────────────────────────────


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """Return safe error responses in production (no stack traces)."""
    if settings.ENVIRONMENT == "production":
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    raise exc


# ══════════════════════════════════════════════════════════════════════════════
# Pydantic request / response schemas
# ══════════════════════════════════════════════════════════════════════════════


class UserRegisterRequest(BaseModel):
    """Schema for demo user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    tenant_id: str = Field(..., min_length=1, max_length=36)
    site_ids: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default=["technician"])


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str = "bearer"


class SessionInitRequest(BaseModel):
    """Request body for session initialisation."""

    asset_id: Optional[str] = None


class AssetResponse(BaseModel):
    """Public asset view."""

    asset_id: str
    tenant_id: str
    site_id: str
    equipment_type: str
    model: str
    status: str
    authorized_roles: List[str]

    class Config:
        from_attributes = True


class FeedbackRequest(BaseModel):
    """Feedback submission body."""

    session_id: str
    turn_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class PrivacyDeleteRequest(BaseModel):
    """Request to delete own data."""

    confirm: bool = Field(..., description="Must be true to confirm data deletion")


class AssetCreateRequest(BaseModel):
    """Admin: create an asset."""

    asset_id: str
    tenant_id: str
    site_id: str
    equipment_type: str
    model: str = ""
    status: str = "operational"
    authorized_roles: List[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# Helper to get client IP
# ══════════════════════════════════════════════════════════════════════════════


def _client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For in production."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and settings.ENVIRONMENT == "production":
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """
    Health check endpoint -- no authentication required.

    Returns:
        JSON with service status and environment.
    """
    return {"status": "ok", "environment": settings.ENVIRONMENT}


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.post("/api/v1/auth/register", response_model=TokenResponse, tags=["auth"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def register_user(
    request: Request,
    body: UserRegisterRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user (demo / development only).

    In production this should be replaced by SSO/IdP integration.

    Args:
        body: Registration details.
        db: Database session.

    Returns:
        JWT access token for the newly created user.
    """
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        tenant_id=body.tenant_id,
        site_ids=body.site_ids,
        roles=body.roles,
    )
    db.add(user)
    await db.flush()

    await audit.log_event(
        db,
        audit.USER_REGISTERED,
        user_id=user.id,
        event_data={"email_domain": body.email.split("@")[1]},  # Don't log full email
        ip_address=_client_ip(request),
    )

    token = create_access_token({"sub": user.id, "email": user.email})
    logger.info("User registered: id=%s", user.id[-8:])
    return TokenResponse(access_token=token)


@app.post("/api/v1/auth/token", response_model=TokenResponse, tags=["auth"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    db: AsyncSession = Depends(get_db),
):
    """
    OAuth2 password flow -- exchange credentials for a JWT token.

    Args:
        form_data: username (email) and password.
        db: Database session.

    Returns:
        JWT access token.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        await audit.log_event(
            db,
            audit.LOGIN_FAILURE,
            event_data={"username": form_data.username[:3] + "***"},  # Partial masking
            ip_address=_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    token = create_access_token({"sub": user.id, "email": user.email})
    await audit.log_event(
        db,
        audit.LOGIN_SUCCESS,
        user_id=user.id,
        ip_address=_client_ip(request),
    )
    return TokenResponse(access_token=token)


# ── Sessions ──────────────────────────────────────────────────────────────────


@app.post("/api/v1/session/initialize", tags=["sessions"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def init_session(
    request: Request,
    body: SessionInitRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize a new LiveKit voice session.

    Authorization context is derived SERVER-SIDE before a LiveKit token is issued.
    Users cannot supply their own auth context.

    Args:
        body: Optional asset_id to scope the session.
        current_user: Authenticated user (from JWT).
        db: Database session.

    Returns:
        session_id, livekit_token, livekit_url, auth_context, expires_at.
    """
    session_info = await initialize_session(current_user, db, asset_id=body.asset_id)

    # Log ASSET_DENIED if an asset was requested but not in auth context
    if body.asset_id and body.asset_id not in session_info.auth_context.get("asset_ids", []):
        await audit.log_event(
            db,
            audit.ASSET_DENIED,
            user_id=current_user.id,
            session_id=session_info.session_id,
            event_data={"asset_id": body.asset_id},
            ip_address=_client_ip(request),
        )
    else:
        await audit.log_event(
            db,
            audit.SESSION_INIT,
            user_id=current_user.id,
            session_id=session_info.session_id,
            event_data={"asset_id": body.asset_id},
            ip_address=_client_ip(request),
        )

    return session_info.to_dict()


# ── Assets ────────────────────────────────────────────────────────────────────


@app.get("/api/v1/assets", response_model=List[AssetResponse], tags=["assets"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def list_assets(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all assets accessible to the authenticated user.

    Returns only assets within the user's authorised site_ids.

    Returns:
        List of AssetResponse objects.
    """
    return await asset_service.list_assets(current_user, db)


@app.get("/api/v1/assets/{asset_id}", response_model=AssetResponse, tags=["assets"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_asset(
    request: Request,
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get details for a specific asset.

    Returns 404 if asset does not exist or is outside user's authorised sites
    (to avoid leaking asset existence to unauthorised callers).

    Args:
        asset_id: The asset identifier.

    Returns:
        AssetResponse if found and authorised.
    """
    asset = await asset_service.get_asset(asset_id, current_user, db)
    await audit.log_event(
        db,
        audit.ASSET_ACCESS,
        user_id=current_user.id,
        event_data={"asset_id": asset_id},
        ip_address=_client_ip(request),
    )
    return asset


@app.post("/api/v1/assets", response_model=AssetResponse, tags=["assets"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def create_asset(
    request: Request,
    body: AssetCreateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new asset. Admin role required.

    Args:
        body: Asset creation payload.

    Returns:
        The created AssetResponse.
    """
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    new_asset = await asset_service.create_asset(
        asset_id=body.asset_id,
        tenant_id=body.tenant_id,
        site_id=body.site_id,
        equipment_type=body.equipment_type,
        model=body.model,
        status=body.status,
        authorized_roles=body.authorized_roles,
        requesting_user=current_user,
        db=db,
    )
    return new_asset


# ── Feedback ──────────────────────────────────────────────────────────────────


@app.post("/api/v1/feedback", tags=["feedback"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit per-turn feedback for a voice session.

    Args:
        body: Feedback payload.

    Returns:
        Confirmation with feedback ID.
    """
    feedback = Feedback(
        session_id=body.session_id,
        user_id=current_user.id,
        turn_id=body.turn_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(feedback)
    await db.flush()

    await audit.log_event(
        db,
        audit.FEEDBACK_SUBMITTED,
        user_id=current_user.id,
        session_id=body.session_id,
        event_data={"turn_id": body.turn_id, "rating": body.rating},
        ip_address=_client_ip(request),
    )

    return {"feedback_id": feedback.id, "status": "submitted"}


# ── Privacy ───────────────────────────────────────────────────────────────────


@app.post("/api/v1/privacy/delete", tags=["privacy"])
@limiter.limit("10/minute")
async def delete_my_data(
    request: Request,
    body: PrivacyDeleteRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete all personal data for the authenticated user (GDPR Art. 17).

    Requires explicit confirmation in the request body.

    Returns:
        Summary of what was deleted/anonymised.
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Must set confirm=true to delete data")

    # Audit BEFORE deletion so the event is captured
    await audit.log_event(
        db,
        audit.DATA_DELETION_REQUEST,
        user_id=current_user.id,
        event_data={"requested_by": "self"},
        ip_address=_client_ip(request),
    )

    summary = await privacy_service.delete_user_data(current_user.id, db)
    return summary


@app.get("/api/v1/privacy/export", tags=["privacy"])
@limiter.limit("10/minute")
async def export_my_data(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all personal data for the authenticated user (GDPR Art. 15).

    Returns:
        JSON export of all user data held by the system.
    """
    await audit.log_event(
        db,
        audit.DATA_EXPORT_REQUEST,
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    return await privacy_service.export_user_data(current_user.id, db)
