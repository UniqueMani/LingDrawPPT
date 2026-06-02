from fastapi import APIRouter, Depends, HTTPException

from backend.db import record_event
from backend.deps import require_user
from backend.models import AnalyzeResponse, ChartResponse, SlideRequest
from backend.services.chart_context import merge_slide_context
from backend.services.chart_gen import generate_echarts_option
from backend.services.semantic import analyze_semantics


router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: SlideRequest, _: dict = Depends(require_user)) -> AnalyzeResponse:
    try:
        sem = analyze_semantics(req)
        intent = sem.get("intent", "")
        chartType = sem.get("chartType", "")
        extracted = sem.get("extracted", {}) or {}
        reason = sem.get("reason", "") or ""

        ctx = merge_slide_context(req.topic, req.body, req.data_description)
        option = generate_echarts_option(
            intent=intent,
            chartType=chartType,
            topic=req.topic,
            extracted=extracted,
            context_text=ctx,
        )

        chart = ChartResponse(
            intent=intent,
            chartType=chartType,
            echartsOption=option,
            reason=reason,
            extracted=extracted,
        )

        record_event(int(_["id"]), "analyze")
        return AnalyzeResponse(semantic=sem, chart=chart)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}")

