from fastapi import APIRouter, Depends, HTTPException

from backend.deps import require_user
from backend.models import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UpdateMeRequest,
    UpdateMeResponse,
    UserDTO,
)
from backend.services.auth import (
    create_token,
    create_user,
    get_user_by_username,
    update_user,
    verify_password,
)


router = APIRouter()


def _to_user_dto(user: dict) -> UserDTO:
    return UserDTO(
        id=int(user["id"]),
        username=str(user["username"]),
        is_admin=bool(user["is_admin"]),
        is_active=bool(user.get("is_active", 1)),
        full_name=str(user.get("full_name", "") or ""),
        email=str(user.get("email", "") or ""),
        organization=str(user.get("organization", "") or ""),
        created_at=str(user["created_at"]),
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest) -> AuthResponse:
    username = req.username.strip()
    password = req.password.strip()
    full_name = req.full_name.strip()
    email = req.email.strip()
    organization = req.organization.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少 3 位")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="姓名至少 2 位")
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(organization) < 2:
        raise HTTPException(status_code=400, detail="单位/组织至少 2 位")
    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = create_user(
        username=username,
        password=password,
        is_admin=False,
        full_name=full_name,
        email=email,
        organization=organization,
    )
    token = create_token(int(user["id"]), str(user["username"]), bool(user["is_admin"]))
    return AuthResponse(token=token, user=_to_user_dto(user))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    username = req.username.strip()
    password = req.password.strip()
    user = get_user_by_username(username)
    if not user or not verify_password(password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not bool(user.get("is_active", 1)):
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    token = create_token(int(user["id"]), str(user["username"]), bool(user["is_admin"]))
    return AuthResponse(token=token, user=_to_user_dto(user))


@router.get("/me", response_model=UserDTO)
async def me(user: dict = Depends(require_user)) -> UserDTO:
    return _to_user_dto(user)


@router.patch("/me", response_model=UpdateMeResponse)
async def update_me(
    req: UpdateMeRequest,
    user: dict = Depends(require_user),
) -> UpdateMeResponse:
    user_id = int(user["id"])
    next_username = req.username.strip() if req.username is not None else None
    next_email = req.email.strip() if req.email is not None else None
    next_full_name = req.full_name.strip() if req.full_name is not None else None
    next_organization = (
        req.organization.strip() if req.organization is not None else None
    )
    next_password = req.new_password.strip() if req.new_password is not None else None

    if next_username is not None:
        if len(next_username) < 3:
            raise HTTPException(status_code=400, detail="用户名至少 3 位")
        existing = get_user_by_username(next_username)
        if existing and int(existing["id"]) != user_id:
            raise HTTPException(status_code=400, detail="用户名已存在")

    if next_email is not None and next_email:
        if "@" not in next_email or "." not in next_email:
            raise HTTPException(status_code=400, detail="邮箱格式不正确")

    if next_password is not None:
        old_password = req.old_password or ""
        if len(next_password) < 6:
            raise HTTPException(status_code=400, detail="新密码至少 6 位")
        if not verify_password(old_password, str(user["password_hash"])):
            raise HTTPException(status_code=400, detail="当前密码不正确")

    updated = update_user(
        user_id,
        username=next_username,
        password=next_password,
        full_name=next_full_name,
        email=next_email,
        organization=next_organization,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="用户不存在")

    token = None
    if next_username is not None or next_password is not None:
        token = create_token(
            int(updated["id"]),
            str(updated["username"]),
            bool(updated["is_admin"]),
        )
    return UpdateMeResponse(user=_to_user_dto(updated), token=token)
