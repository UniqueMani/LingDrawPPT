from fastapi import APIRouter, Depends, HTTPException

from backend.deps import require_user
from backend.models import AuthResponse, LoginRequest, RegisterRequest, UserDTO
from backend.services.auth import (
    create_token,
    create_user,
    get_user_by_username,
    verify_password,
)


router = APIRouter()


def _to_user_dto(user: dict) -> UserDTO:
    return UserDTO(
        id=int(user["id"]),
        username=str(user["username"]),
        is_admin=bool(user["is_admin"]),
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

    token = create_token(int(user["id"]), str(user["username"]), bool(user["is_admin"]))
    return AuthResponse(token=token, user=_to_user_dto(user))


@router.get("/me", response_model=UserDTO)
async def me(user: dict = Depends(require_user)) -> UserDTO:
    return _to_user_dto(user)
