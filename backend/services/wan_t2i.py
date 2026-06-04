from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

from backend.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    WAN_T2I_MAX_WAIT_SEC,
    WAN_T2I_POLL_INTERVAL_SEC,
)

logger = logging.getLogger(__name__)

ASPECT_TO_SIZE: Dict[str, str] = {
    "1:1": "1280*1280",
    "16:9": "1696*960",
    "4:3": "1472*1104",
    "3:4": "1104*1472",
    "9:16": "960*1696",
    "21:9": "1984*848",
}

DEFAULT_NEGATIVE_PROMPT = (
    "低分辨率，低画质，畸形，画面过饱和，蜡像感，"
    "乱码文字，扭曲文字，无关文字，水印，Logo，商标"
)


class WanT2iError(Exception):
    pass


def _require_api_key() -> None:
    if not DASHSCOPE_API_KEY:
        raise WanT2iError("未配置 DASHSCOPE_API_KEY，请在仓库根目录 .env 填写阿里云百炼 API Key")


def _base_url() -> str:
    return DASHSCOPE_BASE_URL.rstrip("/")


def _is_wan26(model: str) -> bool:
    return model.strip().lower().startswith("wan2.6")


def aspect_ratio_to_size(aspect_ratio: str) -> str:
    key = (aspect_ratio or "16:9").strip()
    return ASPECT_TO_SIZE.get(key, ASPECT_TO_SIZE["16:9"])


def build_wan_prompt(
    selected_text: str,
    topic: str = "",
    extra_style: str = "",
    *,
    consistency_suffix: str = "",
) -> str:
    base = (selected_text or topic or "").strip()
    if not base:
        raise WanT2iError("请先框选文字或填写正文后再生成图片")

    parts = [
        "为 PPT 幻灯片生成一张现代扁平矢量风格的信息图插图。",
        f"主题与内容：{base}。",
        "风格：简洁布局、柔和渐变、专业信息图；避免无关文字、乱码、水印和品牌 Logo；"
        "如画面需要标题、年份、数值等信息，必须清晰准确并服务主题。",
    ]
    extra = extra_style.strip()
    if extra:
        parts.append(f"附加风格：{extra}。")
    suffix = (consistency_suffix or "").strip()
    if suffix:
        parts.append(suffix)
    return "".join(parts)


def _api_error(payload: Dict[str, Any], http_status: int) -> str:
    return str(payload.get("message") or payload.get("msg") or f"HTTP {http_status}")


def _extract_image_from_choices(choices: Any) -> str:
    if not isinstance(choices, list):
        return ""
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image":
                url = str(item.get("image") or "").strip()
                if url:
                    return url
    return ""


def _extract_image_from_results(results: Any) -> str:
    if not isinstance(results, list):
        return ""
    for item in results:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            if url:
                return url
    return ""


async def _request(
    method: str,
    url: str,
    *,
    json_body: Optional[dict] = None,
    extra_headers: Optional[dict] = None,
) -> Dict[str, Any]:
    _require_api_key()
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    async with httpx.AsyncClient(timeout=120.0) as client:
        if method.upper() == "POST":
            resp = await client.post(url, headers=headers, json=json_body or {})
        else:
            resp = await client.get(url, headers=headers)

    try:
        payload = resp.json()
    except Exception as exc:
        raise WanT2iError(f"万相 API 返回非 JSON（HTTP {resp.status_code}）") from exc

    if resp.status_code != 200:
        raise WanT2iError(f"万相 API 错误: {_api_error(payload, resp.status_code)}")

    code = payload.get("code")
    if code and str(code).lower() not in {"200", "success"}:
        raise WanT2iError(f"万相 API 错误: {_api_error(payload, resp.status_code)}")

    return payload


async def _generate_wan26_sync(
    prompt: str,
    *,
    model: str,
    size: str,
    prompt_extend: bool,
    negative_prompt: str,
) -> Dict[str, Any]:
    url = f"{_base_url()}/api/v1/services/aigc/multimodal-generation/generation"
    body = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]
        },
        "parameters": {
            "prompt_extend": prompt_extend,
            "watermark": False,
            "n": 1,
            "negative_prompt": negative_prompt,
            "size": size,
        },
    }
    payload = await _request("POST", url, json_body=body)
    output = payload.get("output")
    if not isinstance(output, dict):
        raise WanT2iError("万相 API 未返回 output")

    image_url = _extract_image_from_choices(output.get("choices"))
    if not image_url:
        raise WanT2iError("任务完成但未返回图像 URL")

    return {
        "taskId": str(payload.get("request_id") or ""),
        "resultImageUrl": image_url,
        "originImageUrl": None,
        "mode": "generate",
    }


async def _create_async_task(
    prompt: str,
    *,
    model: str,
    size: str,
    prompt_extend: bool,
    negative_prompt: str,
) -> str:
    if _is_wan26(model):
        url = f"{_base_url()}/api/v1/services/aigc/image-generation/generation"
        body = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ]
            },
            "parameters": {
                "prompt_extend": prompt_extend,
                "watermark": False,
                "n": 1,
                "negative_prompt": negative_prompt,
                "size": size,
            },
        }
    else:
        url = f"{_base_url()}/api/v1/services/aigc/text2image/image-synthesis"
        body = {
            "model": model,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
            },
            "parameters": {
                "size": size,
                "n": 1,
                "prompt_extend": prompt_extend,
                "watermark": False,
            },
        }

    payload = await _request(
        "POST",
        url,
        json_body=body,
        extra_headers={"X-DashScope-Async": "enable"},
    )
    output = payload.get("output")
    if not isinstance(output, dict):
        raise WanT2iError("万相 API 未返回 output")
    task_id = str(output.get("task_id") or "").strip()
    if not task_id:
        raise WanT2iError("万相 API 未返回 task_id")
    return task_id


async def _poll_task(task_id: str, *, model: str) -> Dict[str, Any]:
    url = f"{_base_url()}/api/v1/tasks/{task_id}"
    started = time.monotonic()

    while True:
        if time.monotonic() - started > WAN_T2I_MAX_WAIT_SEC:
            raise WanT2iError("图像生成超时，请稍后重试")

        payload = await _request("GET", url)
        output = payload.get("output")
        if not isinstance(output, dict):
            raise WanT2iError("任务查询未返回 output")

        status = str(output.get("task_status") or "").upper()
        if status in {"PENDING", "RUNNING"}:
            await asyncio.sleep(WAN_T2I_POLL_INTERVAL_SEC)
            continue
        if status == "SUCCEEDED":
            image_url = _extract_image_from_choices(output.get("choices"))
            if not image_url:
                image_url = _extract_image_from_results(output.get("results"))
            if not image_url:
                raise WanT2iError("任务成功但未返回图像 URL")
            return {
                "taskId": task_id,
                "resultImageUrl": image_url,
                "originImageUrl": None,
                "mode": "generate",
            }
        if status == "FAILED":
            raise WanT2iError(str(output.get("message") or output.get("code") or "图像生成失败"))
        if status == "UNKNOWN":
            raise WanT2iError("任务不存在或已过期，请重新生成")
        raise WanT2iError(f"未知任务状态: {status or output}")


async def generate_image(
    prompt: str,
    *,
    aspect_ratio: str = "16:9",
    model: str = "wan2.6-t2i",
    prompt_extend: bool = True,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
) -> Dict[str, Any]:
    size = aspect_ratio_to_size(aspect_ratio)
    model = (model or "wan2.6-t2i").strip()

    if _is_wan26(model):
        try:
            result = await _generate_wan26_sync(
                prompt,
                model=model,
                size=size,
                prompt_extend=prompt_extend,
                negative_prompt=negative_prompt,
            )
            logger.info("Wan2.6 sync image generated: %s", result.get("taskId"))
            return result
        except WanT2iError:
            logger.info("Wan2.6 sync failed, falling back to async for model %s", model)

    task_id = await _create_async_task(
        prompt,
        model=model,
        size=size,
        prompt_extend=prompt_extend,
        negative_prompt=negative_prompt,
    )
    logger.info("Wan t2i task submitted: %s", task_id)
    return await _poll_task(task_id, model=model)