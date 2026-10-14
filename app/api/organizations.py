"""Organization endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organizations import OrganizationCreate, OrganizationPublic

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationPublic])
def list_organizations(db: Session = Depends(get_db)) -> list[Organization]:
    """List active organizations."""
    query = (
        select(Organization)
        .where(Organization.is_active.is_(True))
        .order_by(Organization.name)
    )
    return list(db.scalars(query).all())


@router.post(
    "",
    response_model=OrganizationPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> Organization:
    """Create an organization; only organizers and admins may do this."""
    organization = Organization(
        name=payload.name.strip(),
        slug=payload.slug.lower(),
        description=payload.description,
    )
    db.add(organization)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Organization slug already exists",
        ) from None
    db.refresh(organization)
    return organization


@router.get("/{organization_id}", response_model=OrganizationPublic)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
) -> Organization:
    """Get one active organization."""
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization
