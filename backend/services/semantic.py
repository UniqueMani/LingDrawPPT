import json
import re
from typing import Any, Dict, Optional

try:
    # openai>=1.x
    from openai import OpenAI  # type: ignore
except Exception:
    # openai<1.x（或版本不匹配）时，示例改为自动降级 mock
    OpenAI = None  # type: ignore

from backend.config import DEEPSEEK_API_KEY, USE_DEEPSEEK, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from backend.models import Mode, SlideRequest
from backend.services.preprocessor import (
    grid_to_grouped_series_extracted,
    parse_entity_metric_grid,
    preprocess_text,
)
from backend.services.viz_engine import rule_based_visualization, validate_and_normalize


def _env_mode_to_runtime(req_mode: Mode) -> str:
    """
    返回 runtime 模式字符串：'mock' 或 'deepseek'
    """
    if req_mode == Mode.deepseek:
        # 即使用户强制 deepseek，也需要 API Key；没 key 则降级 mock
        return "deepseek" if DEEPSEEK_API_KEY else "mock"
    if req_mode == Mode.mock:
        return "mock"
    # auto
    return "deepseek" if USE_DEEPSEEK else "mock"


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    """
    从任意返回文本中提取 JSON 对象。
    """
    if not text:
        return None
    # 先尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 再尝试找第一个 {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _mock_analyze(req: SlideRequest) -> Dict[str, Any]:
    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")
    out = rule_based_visualization(combined)
    return {
        "intent": out["intent"],
        "chartType": out["chartType"],
        "extracted": out["extracted"],
        "reason": out["reason"],
        "confidence": out.get("confidence"),
        "scores": out.get("scores"),
        "warnings": out.get("warnings", []),
        "source": "mock",
    }


def _deepseek_analyze(req: SlideRequest) -> Dict[str, Any]:
    """
    DeepSeek 模式下的语义识别：输出结构化 intent/chartType/extracted（尽量由模型直接给 JSON）。
    """
    if not DEEPSEEK_API_KEY or OpenAI is None:
        fallback = _mock_analyze(req)
        fallback["source"] = "fallback"
        return fallback

    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")

    grid = parse_entity_metric_grid(combined)
    if grid:
        extracted = grid_to_grouped_series_extracted(grid)
        return {
            "intent": "comparison",
            "chartType": "comparison_grouped",
            "extracted": extracted,
            "reason": "结构化多实体多指标文本已由规则解析为分组柱状图（与 LLM 解耦，避免误选饼图）。",
            "confidence": 0.95,
            "scores": None,
            "warnings": [],
            "source": "fallback",
        }

    system_prompt = (
        "你是一个PPT可视化助手。给定一页PPT文本(标题+正文+可选数据描述)，"
        "在下列意图中选一个：trend(趋势), comparison(对比), proportion(占比构成), process(流程), "
        "hierarchy(层级), relation(关系/流向)。"
        "输出用于 ECharts 的结构化 JSON。约束："
        "多实体且每实体多指标→comparison + comparison_grouped，禁止饼图；"
        "饼图仅用于同一整体的构成且各%可加总约100、切片名不重复；"
        "多组「源→目标：数值」→ relation + relation_sankey；"
        "用户明确要求表格/矩阵→ data_table。"
        "必须只输出一个 JSON 对象。"
    )

    user_prompt = (
        f"标题/主题: {req.topic}\n"
        f"正文: {req.body or ''}\n"
        f"数据描述: {req.data_description or ''}\n\n"
        "输出JSON格式为：\n"
        "{\n"
        '  "intent": "trend|comparison|proportion|process|hierarchy|relation",\n'
        '  "chartType": "trend_line|comparison_bar|comparison_grouped|proportion_pie|process_flow|'
        'hierarchy_tree|relation_sankey|data_table",\n'
        '  "reason": "一句话解释选择原因",\n'
        '  "extracted": { ... }\n'
        "}\n\n"
        "extracted字段约定：\n"
        "- trend_line: {\"x\": [], \"y\": []}\n"
        "- comparison_bar: {\"labels\": [], \"values\": []}\n"
        "- comparison_grouped: {\"categories\": [], \"series\": [{\"name\":\"\",\"values\":[],\"yAxisIndex\":0|1}]}\n"
        "- proportion_pie: {\"labels\": [], \"values\": []}\n"
        "- process_flow: {\"steps\": []}\n"
        "- hierarchy_tree: {\"chain\": []}\n"
        "- relation_sankey: {\"nodes\": [名称...], \"links\": [{\"source\":\"\",\"target\":\"\",\"value\":数}]}\n"
        "- data_table: {\"columns\": [列名...], \"rows\": [[单元格...], ...]}\n"
    )

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    # 注意：不同 openai/兼容库对 response_format 支持可能不同，因此做异常兜底
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        parsed = _extract_json_obj(content)
        if not parsed:
            raise ValueError("deepseek 返回无法解析JSON")
        normalized = validate_and_normalize(parsed, combined)
        return {
            "intent": normalized["intent"],
            "chartType": normalized["chartType"],
            "extracted": normalized["extracted"],
            "reason": normalized["reason"],
            "confidence": None,
            "scores": None,
            "warnings": normalized.get("warnings", []),
            "source": "deepseek",
        }
    except Exception:
        # 模型失败时不影响 demo，可直接降级 mock
        fallback = _mock_analyze(req)
        fallback["source"] = "fallback"
        return fallback


def _env_mode_to_runtime(req_mode: Mode) -> str:
    if req_mode == Mode.mock:
        return "mock"
    if req_mode == Mode.deepseek:
        return "deepseek"
    return "deepseek" if USE_DEEPSEEK else "mock"


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)


# Final mode routing override: auto is AI-first when USE_DEEPSEEK is true;
# explicit deepseek always attempts the DeepSeek path so failures can be shown.
def _env_mode_to_runtime(req_mode: Mode) -> str:
    if req_mode == Mode.mock:
        return "mock"
    if req_mode == Mode.deepseek:
        return "deepseek"
    return "deepseek" if USE_DEEPSEEK else "mock"


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)


def _env_mode_to_runtime(req_mode: Mode) -> str:
    if req_mode == Mode.mock:
        return "mock"
    if req_mode == Mode.deepseek:
        return "deepseek"
    return "deepseek" if USE_DEEPSEEK else "mock"


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)


# Stable AI-first semantic entrypoints.  These definitions intentionally override
# the earlier demo implementations so the public API keeps the same import path.
def _bounded_confidence(value: Any, default: float) -> float:
    try:
        v = float(value)
    except Exception:
        v = default
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return v


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _semantic_diagnostics(
    req: SlideRequest,
    runtime_mode: str,
    *,
    source: str,
    llm_attempted: bool,
    llm_succeeded: bool,
    fallback_reason: str = "",
) -> Dict[str, Any]:
    return {
        "requestedMode": req.mode.value if hasattr(req.mode, "value") else str(req.mode),
        "runtimeMode": runtime_mode,
        "llmAttempted": llm_attempted,
        "llmSucceeded": llm_succeeded,
        "fallbackReason": fallback_reason,
        "source": source,
    }


def _mock_analyze(req: SlideRequest) -> Dict[str, Any]:
    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")
    out = rule_based_visualization(combined)
    confidence = _bounded_confidence(out.get("confidence"), 0.65)
    warnings = _as_list(out.get("warnings"))
    return {
        "intent": out["intent"],
        "chartType": out["chartType"],
        "extracted": out["extracted"],
        "reason": out["reason"],
        "confidence": confidence,
        "intentConfidence": confidence,
        "dataExtractionConfidence": confidence,
        "chartSuitabilityConfidence": confidence,
        "dataQuality": {
            "sourceUsed": "local_rules",
            "structuredEnough": confidence >= 0.7,
            "notes": warnings,
        },
        "scores": out.get("scores"),
        "warnings": warnings,
        "validationWarnings": warnings,
        **_semantic_diagnostics(
            req,
            "mock",
            source="mock",
            llm_attempted=False,
            llm_succeeded=False,
        ),
    }


def _fallback_semantic(req: SlideRequest, runtime_mode: str, reason: str, *, attempted: bool) -> Dict[str, Any]:
    fallback = _mock_analyze(req)
    fallback.update(
        _semantic_diagnostics(
            req,
            runtime_mode,
            source="fallback",
            llm_attempted=attempted,
            llm_succeeded=False,
            fallback_reason=reason,
        )
    )
    return fallback


def _semantic_system_prompt() -> str:
    return (
        "你是一个 PPT 数据可视化语义分析器。你必须只输出一个严格 JSON 对象，不能输出 Markdown、注释或解释文本。"
        "任务是从标题、正文和可选数据描述中判断图表意图、图表类型，并抽取可直接用于图表的数据。"
        "先识别字段语义角色，再抽取数据：时间、类别、实体、指标名、单位等维度字段只能作为标签、坐标轴或系列名；"
        "只有可度量数值字段才能进入 values、y 或 series.values。"
        "当正文和数据描述同时存在时，按结构化程度、字段完整性、数值可解释性和一致性选择更可靠的数据源；"
        "若存在冲突，在 warnings 中说明。"
        "chartType 判定优先级：显式表格/矩阵 > 流向关系 > 时间趋势 > 多实体多指标 > 占比构成 > 普通对比。"
        "百分数不天然代表构成占比；只有表达整体拆分、构成、份额、占比且切片互斥可合计时才使用饼图。"
        "增长率、转化率、同比率、达成率等默认按趋势或对比处理。"
        "confidence、intentConfidence、dataExtractionConfidence、chartSuitabilityConfidence 必须是 0 到 1 的数字。"
    )


def _semantic_user_prompt(req: SlideRequest) -> str:
    payload = {
        "topic": req.topic,
        "body": req.body or "",
        "data_description": req.data_description or "",
        "allowed_intents": ["trend", "comparison", "proportion", "process", "hierarchy", "relation"],
        "allowed_chartTypes": [
            "trend_line",
            "comparison_bar",
            "comparison_grouped",
            "proportion_pie",
            "process_flow",
            "hierarchy_tree",
            "relation_sankey",
            "data_table",
        ],
        "required_output_schema": {
            "intent": "trend|comparison|proportion|process|hierarchy|relation",
            "chartType": "trend_line|comparison_bar|comparison_grouped|proportion_pie|process_flow|hierarchy_tree|relation_sankey|data_table",
            "confidence": "number 0..1",
            "intentConfidence": "number 0..1",
            "dataExtractionConfidence": "number 0..1",
            "chartSuitabilityConfidence": "number 0..1",
            "reason": "one concise Chinese sentence",
            "dataQuality": {
                "sourceUsed": "body|data_description|both|none",
                "structuredEnough": "boolean",
                "notes": ["string"],
            },
            "warnings": ["string"],
            "extracted": {
                "trend_line": {"x": [], "y": []},
                "comparison_bar": {"labels": [], "values": []},
                "comparison_grouped": {"categories": [], "series": [{"name": "", "values": [], "yAxisIndex": 0}]},
                "proportion_pie": {"labels": [], "values": []},
                "process_flow": {"steps": []},
                "hierarchy_tree": {"chain": []},
                "relation_sankey": {"nodes": [], "links": [{"source": "", "target": "", "value": 0}]},
                "data_table": {"columns": [], "rows": []},
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _deepseek_analyze(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = "deepseek"
    if not DEEPSEEK_API_KEY:
        return _fallback_semantic(req, runtime_mode, "missing_api_key", attempted=False)
    if OpenAI is None:
        return _fallback_semantic(req, runtime_mode, "openai_sdk_unavailable", attempted=False)

    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _semantic_system_prompt()},
                {"role": "user", "content": _semantic_user_prompt(req)},
            ],
            temperature=0.1,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        parsed = _extract_json_obj(content)
        if not parsed:
            raise ValueError("deepseek_json_parse_failed")

        normalized = validate_and_normalize(parsed, combined)
        warnings = _as_list(parsed.get("warnings")) + _as_list(normalized.get("warnings"))
        validation_warnings = list(dict.fromkeys(str(w) for w in warnings if str(w).strip()))
        confidence = _bounded_confidence(parsed.get("confidence"), 0.75)
        data_quality = parsed.get("dataQuality") if isinstance(parsed.get("dataQuality"), dict) else {}
        source = "deepseek+validated" if validation_warnings else "deepseek"
        return {
            "intent": normalized["intent"],
            "chartType": normalized["chartType"],
            "extracted": normalized["extracted"],
            "reason": str(parsed.get("reason") or normalized.get("reason") or ""),
            "confidence": confidence,
            "intentConfidence": _bounded_confidence(parsed.get("intentConfidence"), confidence),
            "dataExtractionConfidence": _bounded_confidence(parsed.get("dataExtractionConfidence"), confidence),
            "chartSuitabilityConfidence": _bounded_confidence(parsed.get("chartSuitabilityConfidence"), confidence),
            "dataQuality": data_quality,
            "scores": None,
            "warnings": validation_warnings,
            "validationWarnings": validation_warnings,
            **_semantic_diagnostics(
                req,
                runtime_mode,
                source=source,
                llm_attempted=True,
                llm_succeeded=True,
            ),
        }
    except Exception as exc:
        return _fallback_semantic(req, runtime_mode, str(exc)[:300], attempted=True)


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)

