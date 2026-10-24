"""Reusable authentication and authorization dependencies."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.token_revocation import is_access_token_revoked
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to an active database user."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_access_token(token)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise unauthorized from None

    if is_access_token_revoked(claims["jti"]):
        raise unauthorized

    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active or claims["ver"] != user.auth_version:
        raise unauthorized
    return user


def require_roles(*roles: str):
    """Return a dependency that permits only the listed database-backed roles."""

    def role_guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_guard


def require_organization_access(db: Session, user: User, organization_id: int) -> None:
    """Allow admins globally and organizers only for organizations they created.

    Legacy organizations without an assigned creator fail closed for organizers
    and can be administered only by a platform admin until ownership is assigned.
    """
    from app.models.organization import Organization

    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Organization not found")
    if user.role == "admin":
        return
    if user.role != "organizer" or organization.created_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="No access to this organization")
