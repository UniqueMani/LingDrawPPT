from fastapi import APIRouter, Depends, HTTPException

from backend.deps import require_admin, require_user
from backend.models import UserDTO
from backend.services.auth import list_users


router = APIRouter()


@router.get("/admin/users", response_model=list[UserDTO])
async def admin_users(user: dict = Depends(require_user)) -> list[UserDTO]:
    _ = require_admin(user)
    if not bool(user.get("is_admin")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    rows = list_users()
    return [
        UserDTO(
            id=int(r["id"]),
            username=str(r["username"]),
            is_admin=bool(r["is_admin"]),
            full_name=str(r.get("full_name", "") or ""),
            email=str(r.get("email", "") or ""),
            organization=str(r.get("organization", "") or ""),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]
