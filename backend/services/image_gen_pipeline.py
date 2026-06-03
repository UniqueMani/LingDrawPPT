from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.config import IMAGE_GEN_MAX_ATTEMPTS
from backend.services.image_quality import (
    ImageQualityReport,
    build_regeneration_hints,
    evaluate_generated_image,
)
from backend.services.wan_t2i import WanT2iError, generate_image

logger = logging.getLogger(__name__)


def _append_hints(prompt: str, hints: str) -> str:
    extra = (hints or "").strip()
    if not extra:
        return prompt
    if extra in prompt:
        return prompt
    return f"{prompt} {extra}"


async def generate_evaluate_regenerate(
    prompt: str,
    *,
    source_text: str,
    aspect_ratio: str,
    model: str,
    prompt_extend: bool,
    preview_path: Optional[str] = None,
) -> Dict[str, Any]:
    attempts_log: List[Dict[str, Any]] = []
    current_prompt = prompt
    last_result: Optional[Dict[str, Any]] = None
    last_eval: Optional[ImageQualityReport] = None

    max_attempts = max(1, IMAGE_GEN_MAX_ATTEMPTS)

    for attempt in range(1, max_attempts + 1):
        logger.info("Image pipeline attempt %s/%s", attempt, max_attempts)
        gen = await generate_image(
            current_prompt,
            aspect_ratio=aspect_ratio,
            model=model,
            prompt_extend=prompt_extend and attempt == 1,
        )
        image_url = str(gen.get("resultImageUrl") or "")
        if not image_url:
            raise WanT2iError("生成结果缺少图片 URL")

        evaluation = await evaluate_generated_image(
            image_url=image_url,
            source_text=source_text,
            prompt_used=current_prompt,
            preview_path=preview_path,
        )
        attempts_log.append(
            {
                "attempt": attempt,
                "promptUsed": current_prompt,
                "resultImageUrl": image_url,
                "evaluation": evaluation.to_dict(),
            }
        )
        last_result = gen
        last_eval = evaluation

        if evaluation.passed or attempt >= max_attempts:
            break

        hints = build_regeneration_hints(evaluation)
        current_prompt = _append_hints(prompt, hints)
        logger.info(
            "Image quality below threshold (%.1f), regenerating: %s",
            evaluation.total_score,
            evaluation.feedback,
        )

    assert last_result is not None and last_eval is not None
    return {
        "taskId": str(last_result.get("taskId") or ""),
        "resultImageUrl": str(last_result["resultImageUrl"]),
        "originImageUrl": last_result.get("originImageUrl"),
        "mode": "generate",
        "promptUsed": attempts_log[-1]["promptUsed"],
        "attempts": len(attempts_log),
        "evaluation": last_eval.to_dict(),
        "attemptsLog": attempts_log,
        "regenerated": len(attempts_log) > 1,
    }
