"""Registration, token issuance, and current-user endpoints."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, oauth2_scheme
from app.core.config import get_settings
from app.core.email import send_password_reset_email
from app.core.rate_limit import consume_rate_limit
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.token_revocation import revoke_access_token
from app.db.session import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestAccepted,
    TokenResponse,
    UserPublic,
    UserRegister,
)

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

    token, expires_in = create_access_token(str(user.id), user.auth_version)
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


_PASSWORD_RESET_MESSAGE = (
    "If an account matches that email address, password-reset instructions will be sent."
)


def _reset_email_key(email: str) -> str:
    """Return a non-reversible Redis key for a normalized email address."""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"auth:password-reset:email:{digest}"


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> PasswordResetRequestAccepted:
    """Start recovery without revealing whether the account exists."""
    settings = get_settings()
    consume_rate_limit(
        key=f"auth:password-reset:ip:{_client_ip(request)}",
        limit=settings.password_reset_request_limit_per_ip,
        window_seconds=settings.password_reset_rate_window_seconds,
    )
    email = str(payload.email).strip().lower()
    consume_rate_limit(
        key=_reset_email_key(email),
        limit=settings.password_reset_request_limit_per_email,
        window_seconds=settings.password_reset_rate_window_seconds,
    )

    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is not None:
        now = datetime.now(UTC)
        # A new request invalidates any previous unused reset token.
        db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
            )
        )
        db.commit()
        reset_link = f"{settings.password_reset_url}?token={quote(raw_token, safe='')}"
        # Do not log or return the raw token. Delivery happens after the generic
        # response is sent so SMTP latency/failure does not reveal account state.
        background_tasks.add_task(send_password_reset_email, email, reset_link)

    return PasswordResetRequestAccepted(message=_PASSWORD_RESET_MESSAGE)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Consume a reset token once, change the password, and invalidate old JWTs."""
    settings = get_settings()
    consume_rate_limit(
        key=f"auth:password-reset:confirm:ip:{_client_ip(request)}",
        limit=settings.password_reset_confirm_limit_per_ip,
        window_seconds=settings.password_reset_rate_window_seconds,
    )
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired password-reset token",
    )
    if record is None:
        raise invalid

    now = datetime.now(UTC)
    # Conditional UPDATE is the single-use gate: only one transaction can
    # change the unused, unexpired record and continue with the password update.
    consumed = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == record.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise invalid

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        db.rollback()
        raise invalid

    user.password_hash = hash_password(payload.new_password)
    user.auth_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
