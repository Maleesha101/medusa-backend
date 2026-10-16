"""Registration, token issuance, and current-user endpoints."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, oauth2_scheme
from app.core.config import get_settings
from app.core.rate_limit import consume_rate_limit
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.token_revocation import revoke_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import TokenResponse, UserPublic, UserRegister

router = APIRouter(prefix="/auth", tags=["authentication"])


def _client_ip(request: Request) -> str:
    """Use the direct peer address; forwarded headers require trusted proxy handling."""
    return request.client.host if request.client is not None else "unknown"


def _account_key(username: str) -> str:
    """Hash the normalized account identifier so it is not stored in Redis keys."""
    normalized = username.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"auth:token:account:{digest}"


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Create a participant account. Public input cannot assign roles or active status."""
    settings = get_settings()
    consume_rate_limit(
        key=f"auth:register:ip:{_client_ip(request)}",
        limit=settings.registration_request_limit,
        window_seconds=settings.registration_rate_window_seconds,
    )
    email = str(payload.email).strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(email=email, password_hash=hash_password(payload.password), role="participant")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    db.refresh(user)
    return user


@router.post("/token", response_model=TokenResponse)
def issue_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange account credentials for a short-lived bearer token.

    The OAuth2 form field named username must contain the user's email address.
    """
    settings = get_settings()
    ip = _client_ip(request)
    consume_rate_limit(
        key=f"auth:token:ip:{ip}",
        limit=settings.token_request_limit_per_ip,
        window_seconds=settings.token_rate_window_seconds,
    )
    consume_rate_limit(
        key=_account_key(form_data.username),
        limit=settings.token_request_limit_per_account,
        window_seconds=settings.token_rate_window_seconds,
    )
    email = form_data.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not verify_password(form_data.password, user.password_hash)
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserPublic)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    """Return only the safe profile of the authenticated user."""
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),
) -> Response:
    """Revoke the presented bearer token until its natural expiration."""
    claims = decode_access_token(token)
    revoke_access_token(claims["jti"], int(claims["exp"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
