import csv
from io import StringIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from backend.config import UPLOAD_DIR
from backend.db import (
    clear_usage_logs,
    get_admin_overview,
    get_uploaded_file,
    list_admin_users,
    list_audit_logs,
    list_uploaded_files,
    list_usage_logs,
    record_admin_audit,
    soft_delete_uploaded_file,
)
from backend.deps import require_admin, require_user
from backend.models import (
    AdminOverviewDTO,
    AdminResetPasswordRequest,
    AdminUserDTO,
    AdminUserStatusRequest,
    AdminUserUpdateRequest,
    PaginatedResponse,
)
from backend.services.auth import get_user_by_id, set_user_active, update_user


router = APIRouter()


def admin_user(user: dict = Depends(require_user)) -> dict:
    return require_admin(user)


def _admin_user_dto(row: dict) -> AdminUserDTO:
    return AdminUserDTO(
        id=int(row["id"]),
        username=str(row["username"]),
        is_admin=bool(row["is_admin"]),
        is_active=bool(row.get("is_active", 1)),
        disabled_at=row.get("disabled_at"),
        full_name=str(row.get("full_name", "") or ""),
        email=str(row.get("email", "") or ""),
        organization=str(row.get("organization", "") or ""),
        created_at=str(row["created_at"]),
    )


@router.get("/admin/overview", response_model=AdminOverviewDTO)
async def admin_overview(_: dict = Depends(admin_user)) -> AdminOverviewDTO:
    return AdminOverviewDTO(**get_admin_overview())


@router.get("/admin/users", response_model=PaginatedResponse)
async def admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = "",
    active: Optional[bool] = None,
    _: dict = Depends(admin_user),
) -> PaginatedResponse:
    result = list_admin_users(page, page_size, keyword.strip(), active)
    result["items"] = [_admin_user_dto(row) for row in result["items"]]
    return PaginatedResponse(**result)


@router.patch("/admin/users/{user_id}", response_model=AdminUserDTO)
async def admin_update_user(
    user_id: int,
    req: AdminUserUpdateRequest,
    admin: dict = Depends(admin_user),
) -> AdminUserDTO:
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    email = req.email.strip() if req.email is not None else None
    if email and ("@" not in email or "." not in email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    updated = update_user(
        user_id,
        full_name=req.full_name.strip() if req.full_name is not None else None,
        email=email,
        organization=req.organization.strip() if req.organization is not None else None,
    )
    record_admin_audit(int(admin["id"]), "update_user", "user", user_id, f"编辑用户 {target['username']}")
    return _admin_user_dto(updated)


@router.post("/admin/users/{user_id}/status", response_model=AdminUserDTO)
async def admin_set_user_status(
    user_id: int,
    req: AdminUserStatusRequest,
    admin: dict = Depends(admin_user),
) -> AdminUserDTO:
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user_id == int(admin["id"]):
        raise HTTPException(status_code=400, detail="不能禁用当前管理员账号")
    if bool(target.get("is_admin")):
        raise HTTPException(status_code=400, detail="不能通过此接口变更管理员账号状态")
    updated = set_user_active(user_id, req.is_active)
    action = "enable_user" if req.is_active else "disable_user"
    record_admin_audit(int(admin["id"]), action, "user", user_id, f"{'启用' if req.is_active else '禁用'}用户 {target['username']}")
    return _admin_user_dto(updated)


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: int,
    req: AdminResetPasswordRequest,
    admin: dict = Depends(admin_user),
) -> dict:
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if bool(target.get("is_admin")):
        raise HTTPException(status_code=400, detail="不能通过此接口重置管理员密码")
    password = req.password.strip()
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="临时密码至少 6 位")
    update_user(user_id, password=password)
    record_admin_audit(int(admin["id"]), "reset_password", "user", user_id, f"重置用户 {target['username']} 的密码")
    return {"ok": True}


@router.get("/admin/files", response_model=PaginatedResponse)
async def admin_files(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = "",
    user_id: Optional[int] = None,
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    include_deleted: bool = False,
    _: dict = Depends(admin_user),
) -> PaginatedResponse:
    return PaginatedResponse(
        **list_uploaded_files(page, page_size, keyword.strip(), user_id, status.strip(), date_from, date_to, include_deleted)
    )


@router.get("/admin/files/{file_id}/download")
async def admin_download_file(file_id: int, _: dict = Depends(admin_user)) -> FileResponse:
    item = get_uploaded_file(file_id)
    if not item or item.get("deleted_at"):
        raise HTTPException(status_code=404, detail="文件不存在或已删除")
    root = Path(UPLOAD_DIR).resolve()
    path = Path(str(item["file_path"])).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="原始文件不可用")
    return FileResponse(path, filename=str(item["original_filename"]), media_type=str(item.get("mime_type") or "application/octet-stream"))


@router.delete("/admin/files/{file_id}")
async def admin_delete_file(file_id: int, admin: dict = Depends(admin_user)) -> dict:
    item = get_uploaded_file(file_id)
    if not item:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not soft_delete_uploaded_file(file_id):
        raise HTTPException(status_code=400, detail="文件已删除")
    record_admin_audit(int(admin["id"]), "soft_delete_file", "file", file_id, f"软删除文件 {item['original_filename']}")
    return {"ok": True}


@router.get("/admin/logs", response_model=PaginatedResponse)
async def admin_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    event_type: str = "",
    date_from: str = "",
    date_to: str = "",
    _: dict = Depends(admin_user),
) -> PaginatedResponse:
    return PaginatedResponse(**list_usage_logs(page, page_size, user_id, event_type.strip(), date_from, date_to))


@router.get("/admin/logs/export")
async def admin_export_logs(
    user_id: Optional[int] = None,
    event_type: str = "",
    date_from: str = "",
    date_to: str = "",
    _: dict = Depends(admin_user),
) -> StreamingResponse:
    rows = []
    page = 1
    while True:
        batch = list_usage_logs(page, 100, user_id, event_type.strip(), date_from, date_to)
        rows.extend(batch["items"])
        if len(rows) >= batch["total"]:
            break
        page += 1
    stream = StringIO()
    stream.write("\ufeff")
    writer = csv.writer(stream)
    writer.writerow(["日志ID", "用户ID", "用户名", "事件类型", "发生时间"])
    for row in rows:
        writer.writerow([row["id"], row["user_id"], row["username"], row["event_type"], row["created_at"]])
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=usage-logs.csv"})


@router.delete("/admin/logs")
async def admin_clear_logs(before: str, admin: dict = Depends(admin_user)) -> dict:
    if not before.strip():
        raise HTTPException(status_code=400, detail="必须提供日志清理截止时间")
    deleted = clear_usage_logs(before.strip())
    record_admin_audit(int(admin["id"]), "clear_logs", "usage_log", before.strip(), f"清理 {deleted} 条使用日志")
    return {"ok": True, "deleted": deleted}


@router.get("/admin/audit-logs", response_model=PaginatedResponse)
async def admin_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(admin_user),
) -> PaginatedResponse:
    return PaginatedResponse(**list_audit_logs(page, page_size))
