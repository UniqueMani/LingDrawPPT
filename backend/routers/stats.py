from fastapi import APIRouter, Depends, Query

from backend.db import get_user_stats, record_event
from backend.deps import require_user
from backend.models import RecordEventRequest, UsageStatsResponse

router = APIRouter()


@router.get("/stats", response_model=UsageStatsResponse)
async def get_stats(
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(require_user),
) -> UsageStatsResponse:
    events = get_user_stats(int(user["id"]), days=days)
    detail = [
        {"name": k, "label": EVENT_LABELS.get(k, k), "count": v}
        for k, v in sorted(events.items(), key=lambda x: -x[1])
    ]
    return UsageStatsResponse(events=events, detail=detail)


@router.post("/stats/event")
async def post_event(
    req: RecordEventRequest,
    user: dict = Depends(require_user),
) -> dict:
    record_event(int(user["id"]), req.event_type)
    return {"ok": True}


EVENT_LABELS: dict[str, str] = {
    "upload": "上传",
    "analyze": "解析",
    "generate": "生成",
    "adopt": "采用",
}
