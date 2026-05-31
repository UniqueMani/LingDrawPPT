from fastapi import APIRouter, Depends, HTTPException

from backend.db import record_event
from backend.deps import require_user
from backend.models import IllustrationResponse, IllustrationStrategyResponse, SlideRequest
from backend.services.illus_strategy import generate_illustration_strategy
from backend.services.semantic import analyze_semantics


router = APIRouter()


@router.post("/illustration", response_model=IllustrationStrategyResponse)
async def illustration(req: SlideRequest, _: dict = Depends(require_user)) -> IllustrationStrategyResponse:
    try:
        sem = analyze_semantics(req)
        intent = sem.get("intent", "") or ""

        illus = generate_illustration_strategy(req, intent=intent)

        record_event(int(_["id"]), "generate")
        return IllustrationStrategyResponse(
            illustration=IllustrationResponse(**illus)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"illustration failed: {e}")

