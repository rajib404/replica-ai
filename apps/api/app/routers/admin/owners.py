"""Admin owners listing + detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin_schemas import OwnerDetailResponse, OwnerListResponse
from app.services.admin import owners as owners_service

router = APIRouter()


@router.get("/owners", response_model=OwnerListResponse)
async def list_owners(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> OwnerListResponse:
    data = await owners_service.list_owners(
        db, page=page, page_size=page_size, search=search
    )
    return OwnerListResponse(**data)


@router.get("/owners/{owner_id}", response_model=OwnerDetailResponse)
async def get_owner(
    owner_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> OwnerDetailResponse:
    detail = await owners_service.get_owner_detail(db, owner_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found")
    return OwnerDetailResponse(**detail)
