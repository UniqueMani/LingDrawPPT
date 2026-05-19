"""独立研究接口：意图分析 / 多形态图表代码 / 配图实验。"""

from fastapi import APIRouter, Depends, HTTPException

from backend.deps import require_user
from backend.models import (
    SlideRequest,
    VizLabChartCodeRequest,
    VizLabChartCodeResponse,
    VizLabIllustrationRequest,
    VizLabIllustrationResponse,
    VizLabIntentResponse,
)
from backend.services.chart_code_llm import generate_chart_code_bundle
from backend.services.illus_strategy import generate_illustration_strategy
from backend.services.semantic import analyze_semantics

router = APIRouter()


@router.post("/viz-lab/intent", response_model=VizLabIntentResponse)
async def viz_lab_intent(req: SlideRequest, _: dict = Depends(require_user)) -> VizLabIntentResponse:
    try:
        return VizLabIntentResponse(semantic=analyze_semantics(req))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"intent failed: {e}") from e


@router.post("/viz-lab/chart-code", response_model=VizLabChartCodeResponse)
async def viz_lab_chart_code(
    body: VizLabChartCodeRequest, _: dict = Depends(require_user)
) -> VizLabChartCodeResponse:
    try:
        bundle = generate_chart_code_bundle(body.slide, body.targets, body.instructions)
        return VizLabChartCodeResponse(
            echartsOption=bundle.get("echartsOption"),
            chartJsConfig=bundle.get("chartJsConfig"),
            mermaidSource=bundle.get("mermaidSource"),
            validationIssues=bundle.get("validationIssues") or [],
            source=bundle.get("source", "fallback"),
            rawLlmExcerpt=bundle.get("rawLlmExcerpt"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"chart-code failed: {e}") from e


@router.post("/viz-lab/illustration", response_model=VizLabIllustrationResponse)
async def viz_lab_illustration(
    body: VizLabIllustrationRequest, _: dict = Depends(require_user)
) -> VizLabIllustrationResponse:
    try:
        sem = analyze_semantics(body.slide)
        intent = str(sem.get("intent") or "")
        ill = generate_illustration_strategy(body.slide, intent)
        prompt = ill.get("prompt") or ""

        model = (body.image_model or "flux").lower()
        if model == "flux":
            prompt += " 目标引擎：类 FLUX；"
        elif model == "sd":
            prompt += " 目标引擎：Stable Diffusion；"
        else:
            prompt += f" 目标引擎：{body.image_model}；"
        if body.extra_style_words:
            prompt += f" 追加风格词：{body.extra_style_words.strip()}；"
        if body.lora_hint:
            prompt += f" LoRA/风格：{body.lora_hint.strip()}；"
        if body.style_ref_url:
            prompt += f" （参考图 URL：{body.style_ref_url.strip()}，待接 IP-Adapter）"

        return VizLabIllustrationResponse(
            needIllus=bool(ill.get("needIllus")),
            keywords=list(ill.get("keywords") or []),
            prompt=prompt,
            reason=str(ill.get("reason") or ""),
            experiment={
                "imageModel": body.image_model,
                "styleRefUrl": body.style_ref_url,
                "loraHint": body.lora_hint,
                "extraStyleWords": body.extra_style_words,
                "intentUsed": intent,
                "chartTypeHint": sem.get("chartType"),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"illustration lab failed: {e}") from e
