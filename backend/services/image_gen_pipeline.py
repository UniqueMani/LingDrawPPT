from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.config import IMAGE_GEN_MAX_ATTEMPTS
from backend.services.image_quality import evaluate_generated_image
from backend.services.wan_t2i import WanT2iError, generate_image

logger = logging.getLogger(__name__)


async def generate_evaluate_regenerate(
    prompt: str,
    *,
    source_text: str,
    aspect_ratio: str,
    model: str,
    prompt_extend: bool,
    generation_mode: str = "standard",
    preview_path: Optional[str] = None,
    slide_type: Optional[str] = None,
) -> Dict[str, Any]:
    attempts_log: List[Dict[str, Any]] = []
    base_prompt = prompt.strip()

    normalized_mode = (generation_mode or "standard").strip().lower()
    if normalized_mode == "fast":
        max_attempts = 1
    else:
        max_attempts = min(3, max(1, IMAGE_GEN_MAX_ATTEMPTS))

    gen: Dict[str, Any] = {}
    for attempt in range(1, max_attempts + 1):
        logger.info("Image pipeline candidate %s/%s (independent)", attempt, max_attempts)
        gen = await generate_image(
            base_prompt,
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
            prompt_used=base_prompt,
            preview_path=preview_path,
            slide_type=slide_type,
        )
        attempts_log.append(
            {
                "attempt": attempt,
                "promptUsed": base_prompt,
                "resultImageUrl": image_url,
                "evaluation": evaluation.to_dict(),
                "judgeFeedback": None,
            }
        )
        logger.info(
            "Candidate %s score=%.1f passed=%s",
            attempt,
            evaluation.total_score,
            evaluation.passed,
        )

    best_entry = max(
        attempts_log,
        key=lambda item: float((item.get("evaluation") or {}).get("totalScore") or 0),
    )
    best_eval_raw = best_entry.get("evaluation") or {}

    return {
        "taskId": str(gen.get("taskId") or ""),
        "resultImageUrl": str(best_entry["resultImageUrl"]),
        "originImageUrl": gen.get("originImageUrl"),
        "mode": "generate",
        "promptUsed": base_prompt,
        "attempts": len(attempts_log),
        "evaluation": best_eval_raw,
        "attemptsLog": attempts_log,
        "regenerated": len(attempts_log) > 1,
        "selectedAttempt": int(best_entry.get("attempt") or 1),
    }
