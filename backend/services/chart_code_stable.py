from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from backend.models import SlideRequest
from backend.services.chart_code_llm import (
    _extract_json_obj,
    _fallback_from_pipeline,
    validate_chartjs_config,
    validate_echarts_option,
    validate_mermaid,
)
from backend.services.semantic import analyze_semantics


def _chart_code_system_prompt(targets: List[str], instructions: Optional[str]) -> str:
    target_text = ", ".join(targets)
    extra = f"\nAdditional user constraints: {instructions}" if instructions else ""
    return (
        "你是一个资深数据可视化工程师。你必须只输出一个严格 JSON 对象，不能输出 Markdown、注释或解释文本。"
        "你会收到 slide 文本和 semantic_hint。semantic_hint 是唯一可信的数据语义来源，不能重新发明类别、数值或系列。"
        f"本次需要生成的目标代码类型是：{target_text}。"
        "固定输出字段为 echartsOption、chartJsConfig、mermaidSource、notes、warnings；不适用的目标返回 null。"
        "三种输出必须描述同一组数据，类别、系列、数值和单位必须一致。"
        "趋势图使用 line；普通对比使用 bar；分组对比必须多 series/dataset 且 legend 与 series/dataset 名称一致；"
        "构成占比使用 pie；流程和层级优先用 Mermaid flowchart；关系流向 ECharts 使用 sankey；"
        "表格用可读表格 fallback，无法原生表达的引擎返回 null 并在 warnings 中说明。"
        "ECharts 和 Chart.js 必须包含 title、tooltip、legend、坐标轴名称或等效标签；坐标轴单位应从语义或文本中继承。"
        "Mermaid 必须使用合法语法：pie、xychart-beta 或 flowchart。"
        "xychart-beta 的 title 必须写成 title \"标题\"；x-axis 必须写成 x-axis [\"1月\", \"2月\"] 或 x-axis \"月份\" [\"1月\", \"2月\"]；"
        "趋势图必须使用 line [数值...]，普通对比图使用 bar [数值...]；不要使用中文弯引号。"
        + extra
    )


def _chart_code_user_prompt(slide: SlideRequest, sem: Dict[str, Any]) -> str:
    payload = {
        "topic": slide.topic,
        "body": slide.body or "",
        "data_description": slide.data_description or "",
        "semantic_hint": {
            "intent": sem.get("intent"),
            "chartType": sem.get("chartType"),
            "extracted": sem.get("extracted"),
            "reason": sem.get("reason"),
            "confidence": sem.get("confidence"),
            "dataQuality": sem.get("dataQuality"),
            "warnings": sem.get("warnings"),
        },
        "required_output_schema": {
            "echartsOption": "object|null",
            "chartJsConfig": "object|null",
            "mermaidSource": "string|null",
            "notes": ["string"],
            "warnings": ["string"],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _present_targets(opt: Any, cjs: Any, mer: Any) -> List[str]:
    out: List[str] = []
    if isinstance(opt, dict) and opt:
        out.append("echarts")
    if isinstance(cjs, dict) and cjs:
        out.append("chartjs")
    if isinstance(mer, str) and mer.strip():
        out.append("mermaid")
    return out


def _missing_reason() -> str:
    if not DEEPSEEK_API_KEY:
        return "missing_api_key"
    if OpenAI is None:
        return "openai_sdk_unavailable"
    return ""


def _has_mermaid_error(src: Optional[str]) -> bool:
    return any(sev == "error" for sev, _msg in validate_mermaid(src))


def generate_chart_code_bundle(
    slide: SlideRequest,
    targets: List[str],
    instructions: Optional[str],
) -> Dict[str, Any]:
    targets_set = {t.lower() for t in targets} if targets else {"echarts", "chartjs", "mermaid"}
    want_e = "echarts" in targets_set
    want_c = "chartjs" in targets_set
    want_m = "mermaid" in targets_set

    opt: Optional[Dict[str, Any]] = None
    cjs: Optional[Dict[str, Any]] = None
    mer: Optional[str] = None
    raw_llm: Optional[str] = None
    issues: List[Dict[str, str]] = []
    llm_attempted = False
    llm_succeeded = False
    fallback_reason = _missing_reason()
    source = "fallback"

    if not fallback_reason:
        llm_attempted = True
        try:
            sem = analyze_semantics(slide)
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _chart_code_system_prompt(sorted(targets_set), instructions)},
                    {"role": "user", "content": _chart_code_user_prompt(slide, sem)},
                ],
                temperature=0.1,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw_llm = resp.choices[0].message.content or ""
            parsed = _extract_json_obj(raw_llm)
            if not parsed:
                raise ValueError("chart_code_json_parse_failed")
            if isinstance(parsed.get("echartsOption"), dict):
                opt = parsed["echartsOption"]
            if isinstance(parsed.get("chartJsConfig"), dict):
                cjs = parsed["chartJsConfig"]
            if isinstance(parsed.get("mermaidSource"), str):
                mer = parsed["mermaidSource"]
            llm_succeeded = any([opt, cjs, mer])
            source = "llm" if llm_succeeded else "fallback"
            if not llm_succeeded:
                fallback_reason = "llm_returned_no_supported_targets"
        except Exception as exc:
            fallback_reason = str(exc)[:500]

    mermaid_needs_repair = want_m and mer is not None and _has_mermaid_error(mer)
    needs_fallback = (want_e and opt is None) or (want_c and cjs is None) or (want_m and (mer is None or mermaid_needs_repair))
    if needs_fallback:
        fo, fc, fm, _meta = _fallback_from_pipeline(slide)
        if opt is None and want_e:
            opt = fo
        if cjs is None and want_c:
            cjs = fc
        if want_m and (mer is None or mermaid_needs_repair):
            if mermaid_needs_repair:
                issues.append({
                    "target": "mermaid",
                    "severity": "warn",
                    "message": "LLM 返回的 Mermaid 语法不稳定，已使用本地规则重新生成。",
                })
            mer = fm
        source = "llm+fallback" if llm_succeeded else "fallback"
        if not fallback_reason and llm_succeeded:
            fallback_reason = "llm_mermaid_invalid" if mermaid_needs_repair else "llm_output_missing_requested_targets"

    if not want_e:
        opt = None
    if not want_c:
        cjs = None
    if not want_m:
        mer = None

    if opt is not None:
        for sev, msg in validate_echarts_option(opt):
            issues.append({"target": "echarts", "severity": sev, "message": msg})
    if cjs is not None:
        for sev, msg in validate_chartjs_config(cjs):
            issues.append({"target": "chartjs", "severity": sev, "message": msg})
    if mer is not None:
        for sev, msg in validate_mermaid(mer):
            issues.append({"target": "mermaid", "severity": sev, "message": msg})

    return {
        "echartsOption": opt,
        "chartJsConfig": cjs,
        "mermaidSource": mer,
        "validationIssues": issues,
        "generatedTargets": _present_targets(opt, cjs, mer),
        "source": source,
        "llmAttempted": llm_attempted,
        "llmSucceeded": llm_succeeded,
        "fallbackReason": fallback_reason,
        "rawLlmExcerpt": (raw_llm[:1200] + "...") if raw_llm and len(raw_llm) > 1200 else raw_llm,
    }
