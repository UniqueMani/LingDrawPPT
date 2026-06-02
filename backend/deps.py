from fastapi import Header, HTTPException

from backend.services.auth import decode_token, get_user_by_id


def require_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或 token 缺失")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    uid = int(payload.get("sub", 0))
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not bool(user.get("is_active", 1)):
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return user


def require_admin(user: dict) -> dict:
    if not bool(user.get("is_admin")):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
