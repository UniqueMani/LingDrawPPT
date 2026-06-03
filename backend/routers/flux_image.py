from fastapi import APIRouter, Depends, HTTPException

from backend.db import record_event
from backend.deps import require_user
from backend.models import (
    FluxGenerateImageRequest,
    FluxGenerateImageResponse,
    ImageGenAttemptLog,
    ImageQualityDimensionScore,
    ImageQualityEvaluation,
)
from backend.services.doc_consistency import (
    build_consistency_prompt_suffix,
    get_slide_plan,
    resolve_entities_for_plan,
)
from backend.services.image_gen_pipeline import generate_evaluate_regenerate
from backend.services.wan_t2i import WanT2iError, build_wan_prompt

router = APIRouter()


def _parse_evaluation(raw: dict) -> ImageQualityEvaluation:
    dims = [
        ImageQualityDimensionScore(**item)
        for item in (raw.get("dimensions") or [])
        if isinstance(item, dict)
    ]
    return ImageQualityEvaluation(
        passed=bool(raw.get("passed")),
        totalScore=float(raw.get("totalScore") or 0),
        passThreshold=float(raw.get("passThreshold") or 72),
        dimensions=dims,
        feedback=str(raw.get("feedback") or ""),
    )


@router.post("/flux/generate-image", response_model=FluxGenerateImageResponse)
async def flux_generate_image(
    body: FluxGenerateImageRequest,
    _: dict = Depends(require_user),
) -> FluxGenerateImageResponse:
    try:
        if body.input_image_url or body.use_page_preview:
            raise WanT2iError(
                "当前使用阿里云万相文生图，不支持「编辑预览图/参考图」模式，请关闭相关选项后重试"
            )

        selected = body.selected_text.strip() or body.prompt.strip()
        source_text = selected or (body.topic or "").strip()

        consistency_suffix = ""
        if body.doc_consistency and (body.use_doc_style or body.use_entity_sync):
            style_dict = body.doc_consistency.style.model_dump()
            plans = [p.model_dump() for p in body.doc_consistency.slide_plans]
            entities = [e.model_dump() for e in body.doc_consistency.entities]
            plan = get_slide_plan(plans, body.slide_page)
            linked = resolve_entities_for_plan(entities, plan)
            consistency_suffix = build_consistency_prompt_suffix(
                style=style_dict,
                slide_plan=plan,
                entities=linked,
                use_doc_style=body.use_doc_style,
                use_entity_sync=body.use_entity_sync,
            )

        prompt_used = build_wan_prompt(
            selected_text=selected,
            topic=body.topic or "",
            extra_style=body.extra_style_words or "",
            consistency_suffix=consistency_suffix,
        )

        prompt_extend = body.prompt_extend or body.prompt_upsampling
        result = await generate_evaluate_regenerate(
            prompt_used,
            source_text=source_text,
            aspect_ratio=body.aspect_ratio,
            model=body.model,
            prompt_extend=prompt_extend,
            preview_path=body.preview_path,
        )

        eval_raw = result.get("evaluation") if isinstance(result.get("evaluation"), dict) else None
        evaluation = _parse_evaluation(eval_raw) if eval_raw else None
        attempts_log = [
            ImageGenAttemptLog(
                attempt=int(item.get("attempt") or 0),
                promptUsed=str(item.get("promptUsed") or ""),
                resultImageUrl=str(item.get("resultImageUrl") or ""),
                evaluation=_parse_evaluation(item["evaluation"]),
            )
            for item in (result.get("attemptsLog") or [])
            if isinstance(item, dict) and isinstance(item.get("evaluation"), dict)
        ]

        record_event(int(_["id"]), "generate")
        return FluxGenerateImageResponse(
            taskId=str(result["taskId"]),
            resultImageUrl=str(result["resultImageUrl"]),
            originImageUrl=result.get("originImageUrl"),
            promptUsed=str(result.get("promptUsed") or prompt_used),
            mode=str(result.get("mode") or "generate"),
            attempts=int(result.get("attempts") or 1),
            regenerated=bool(result.get("regenerated")),
            evaluation=evaluation,
            attemptsLog=attempts_log,
        )
    except WanT2iError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"image generate failed: {e}") from e
