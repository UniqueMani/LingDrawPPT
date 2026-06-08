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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round_score(value: float) -> float:
    return round(_clamp01(value), 3)


def _as_number_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    numbers: list[float] = []
    for item in value:
        try:
            numbers.append(float(item))
        except Exception:
            continue
    return numbers


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coverage_score(items: list[Any], combined: str) -> float:
    tokens = [str(item).strip() for item in items if str(item).strip()]
    if not tokens:
        return 0.0
    hits = 0
    for token in tokens:
        if token in combined:
            hits += 1
            continue
        try:
            if str(float(token)).rstrip("0").rstrip(".") in combined:
                hits += 1
        except Exception:
            pass
    return hits / len(tokens)


def _keyword_evidence(intent: str, combined: str) -> list[str]:
    patterns = {
        "trend": (r"趋势|变化|走势|增长|下降|环比|同比|月|季度|年|时间", "检测到时间或趋势语义"),
        "comparison": (r"对比|比较|排名|TOP|差异|高于|低于|分别|各", "检测到对比语义"),
        "proportion": (r"占比|构成|份额|比例|分布|拆分|整体", "检测到占比或构成语义"),
        "process": (r"流程|步骤|阶段|先|然后|最后|审批|流转", "检测到流程步骤语义"),
        "hierarchy": (r"层级|组织|架构|目录|父级|子级|包含", "检测到层级结构语义"),
        "relation": (r"流向|来源|去向|转化|从.+到|关系|链路", "检测到关系或流向语义"),
    }
    pattern, label = patterns.get(intent, ("", ""))
    return [label] if pattern and re.search(pattern, combined, re.I) else []


def _has_effective_extracted(chart_type: str, extracted: Dict[str, Any]) -> bool:
    if chart_type == "trend_line":
        return len(_string_items(extracted.get("x"))) >= 2 and len(_as_number_list(extracted.get("y"))) >= 2
    if chart_type in ("comparison_bar", "proportion_pie"):
        return len(_string_items(extracted.get("labels"))) >= 2 and len(_as_number_list(extracted.get("values"))) >= 2
    if chart_type == "comparison_grouped":
        return bool(extracted.get("categories")) and bool(extracted.get("series"))
    if chart_type == "process_flow":
        return len(_string_items(extracted.get("steps"))) >= 2
    if chart_type == "hierarchy_tree":
        return len(_string_items(extracted.get("chain"))) >= 2
    if chart_type == "relation_sankey":
        return len(_as_list(extracted.get("links"))) >= 1
    if chart_type == "data_table":
        return bool(extracted.get("columns")) and bool(extracted.get("rows"))
    return bool(extracted)


def _data_extraction_score(chart_type: str, extracted: Dict[str, Any], combined: str) -> Dict[str, Any]:
    checks: list[str] = []
    penalties: list[str] = []
    schema = numeric = coverage = consistency = 0.0

    if chart_type == "trend_line":
        x = _string_items(extracted.get("x"))
        y = _as_number_list(extracted.get("y"))
        schema = 1.0 if len(x) >= 2 and len(y) >= 2 else 0.35
        numeric = min(1.0, len(y) / max(1, len(x))) if x else 0.0
        consistency = 1.0 if len(x) == len(y) and len(x) >= 2 else 0.5 if min(len(x), len(y)) >= 2 else 0.0
        coverage = _coverage_score(x, combined)
        if schema == 1.0:
            checks.append("x/y 至少包含两个点")
        if consistency == 1.0:
            checks.append("x/y 长度一致")
        if coverage >= 0.6:
            checks.append("时间标签可在原文中找到")

    elif chart_type in ("comparison_bar", "proportion_pie"):
        labels = _string_items(extracted.get("labels"))
        values = _as_number_list(extracted.get("values"))
        schema = 1.0 if len(labels) >= 2 and len(values) >= 2 else 0.35
        numeric = min(1.0, len(values) / max(1, len(labels))) if labels else 0.0
        consistency = 1.0 if len(labels) == len(values) and len(labels) >= 2 else 0.5 if min(len(labels), len(values)) >= 2 else 0.0
        coverage = _coverage_score(labels, combined)
        if len(labels) != len(set(labels)):
            penalties.append("标签存在重复")
        if any(v < 0 for v in values):
            penalties.append("数值存在负数")
        if chart_type == "proportion_pie":
            total = sum(values)
            if not re.search(r"占比|构成|份额|比例|分布|整体|拆分", combined):
                penalties.append("缺少整体构成语义")
            if values and not (75 <= total <= 125) and not re.search(r"占比|构成|份额|比例|分布|整体|拆分", combined):
                penalties.append("切片合计不接近 100")
        if schema == 1.0:
            checks.append("标签和值数量充足")
        if consistency == 1.0:
            checks.append("标签和值长度一致")

    elif chart_type == "comparison_grouped":
        categories = _string_items(extracted.get("categories"))
        series = _as_list(extracted.get("series"))
        valid_series = [s for s in series if isinstance(s, dict) and len(_as_number_list(s.get("values"))) == len(categories)]
        schema = 1.0 if categories and valid_series else 0.35
        numeric = min(1.0, len(valid_series) / max(1, len(series))) if series else 0.0
        consistency = 1.0 if series and len(valid_series) == len(series) else 0.4
        coverage = _coverage_score(categories, combined)
        if valid_series:
            checks.append("分组系列长度匹配")
        if series and len(valid_series) != len(series):
            penalties.append("部分系列长度不匹配")

    elif chart_type == "process_flow":
        steps = _string_items(extracted.get("steps"))
        schema = numeric = consistency = 1.0 if len(steps) >= 2 else 0.25
        coverage = _coverage_score(steps, combined)
        if len(steps) >= 2:
            checks.append("流程步骤数量充足")

    elif chart_type == "hierarchy_tree":
        chain = _string_items(extracted.get("chain"))
        schema = numeric = consistency = 1.0 if len(chain) >= 2 else 0.25
        coverage = _coverage_score(chain, combined)
        if len(chain) >= 2:
            checks.append("层级链路数量充足")

    elif chart_type == "relation_sankey":
        nodes = set(_string_items(extracted.get("nodes")))
        links = [link for link in _as_list(extracted.get("links")) if isinstance(link, dict)]
        valid_links = [
            link for link in links
            if str(link.get("source", "")).strip()
            and str(link.get("target", "")).strip()
            and _as_number_list([link.get("value")])
        ]
        schema = 1.0 if nodes and valid_links else 0.35
        numeric = min(1.0, len(valid_links) / max(1, len(links))) if links else 0.0
        consistency = 1.0 if valid_links and all(str(l.get("source")) in nodes and str(l.get("target")) in nodes for l in valid_links) else 0.45
        coverage = _coverage_score(list(nodes), combined)
        if valid_links:
            checks.append("关系边包含 source、target、value")
        if consistency < 1.0:
            penalties.append("部分关系边未对应节点")

    elif chart_type == "data_table":
        columns = _string_items(extracted.get("columns"))
        rows = _as_list(extracted.get("rows"))
        matched_rows = [r for r in rows if isinstance(r, list) and len(r) == len(columns)]
        schema = 1.0 if columns and rows else 0.3
        numeric = 0.8 if rows else 0.0
        consistency = 1.0 if rows and len(matched_rows) == len(rows) else 0.5
        coverage = _coverage_score(columns, combined)
        if columns and rows:
            checks.append("表格行列非空")
        if consistency < 1.0:
            penalties.append("部分表格行列数不一致")

    penalty_value = min(0.35, 0.08 * len(penalties))
    score = 0.40 * schema + 0.25 * numeric + 0.20 * coverage + 0.15 * consistency - penalty_value
    return {
        "score": _round_score(score),
        "checks": checks,
        "penalties": penalties,
        "components": {
            "schemaCompleteness": _round_score(schema),
            "numericQuality": _round_score(numeric),
            "sourceCoverage": _round_score(coverage),
            "lengthConsistency": _round_score(consistency),
        },
    }


def _chart_suitability_score(intent: str, chart_type: str, extracted: Dict[str, Any], combined: str, warnings: list[str]) -> Dict[str, Any]:
    checks: list[str] = []
    penalties: list[str] = []
    expected = {
        "trend": "trend_line",
        "comparison": ("comparison_bar", "comparison_grouped", "data_table"),
        "proportion": "proportion_pie",
        "process": "process_flow",
        "hierarchy": "hierarchy_tree",
        "relation": "relation_sankey",
    }
    expected_chart = expected.get(intent)
    if isinstance(expected_chart, tuple):
        intent_match = 1.0 if chart_type in expected_chart else 0.25
    else:
        intent_match = 1.0 if chart_type == expected_chart else 0.25
    if intent_match == 1.0:
        checks.append("图表类型与意图匹配")
    else:
        penalties.append("图表类型与意图不完全匹配")

    requirement = 1.0 if _has_effective_extracted(chart_type, extracted) else 0.25
    if requirement == 1.0:
        checks.append("满足当前图表的最低数据要求")
    else:
        penalties.append("当前图表所需数据不足")

    data_shape = requirement
    safety = 0.9
    if chart_type == "proportion_pie":
        values = _as_number_list(extracted.get("values"))
        has_part_whole = bool(re.search(r"占比|构成|份额|比例|分布|整体|拆分", combined))
        if has_part_whole:
            checks.append("存在整体构成语义")
        else:
            penalties.append("缺少饼图需要的整体构成语义")
            data_shape = min(data_shape, 0.55)
        if values and any(v < 0 for v in values):
            safety = 0.45
    if warnings:
        penalties.extend([f"校验警告：{w}" for w in warnings[:3]])

    validation_penalty = min(0.36, 0.08 * len(warnings))
    score = 0.45 * requirement + 0.25 * intent_match + 0.20 * data_shape + 0.10 * safety - validation_penalty
    return {
        "score": _round_score(score),
        "checks": checks,
        "penalties": penalties,
        "components": {
            "chartRequirementPass": _round_score(requirement),
            "intentChartMatch": _round_score(intent_match),
            "dataShapeFit": _round_score(data_shape),
            "visualizationSafety": _round_score(safety),
            "validationPenalty": _round_score(validation_penalty),
        },
    }


def compute_semantic_confidence(
    req: SlideRequest,
    normalized: Dict[str, Any],
    local_rule_result: Dict[str, Any],
    warnings: list[str],
    *,
    fallback_used: bool = False,
) -> Dict[str, Any]:
    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")
    intent = str(normalized.get("intent") or "comparison")
    chart_type = str(normalized.get("chartType") or "comparison_bar")
    extracted = normalized.get("extracted") if isinstance(normalized.get("extracted"), dict) else {}

    raw_scores = local_rule_result.get("scores") if isinstance(local_rule_result.get("scores"), dict) else {}
    scores = {str(k): _clamp01(float(v or 0)) for k, v in raw_scores.items()} if raw_scores else {}
    rule_intent = str(local_rule_result.get("intent") or intent)
    rule_chart_type = str(local_rule_result.get("chartType") or chart_type)
    if not scores:
        scores = {rule_intent: _bounded_confidence(local_rule_result.get("confidence"), 0.75)}
    selected_score = scores.get(intent, 0.0)
    sorted_scores = sorted(scores.values(), reverse=True)
    top_score = sorted_scores[0] if sorted_scores else selected_score
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    margin_score = _clamp01(top_score - second_score)

    evidence = _keyword_evidence(intent, combined)
    agreement_bonus = 0.0
    conflict_penalty = 0.0
    if intent == rule_intent and chart_type == rule_chart_type:
        agreement = "intent_and_chart_match"
        agreement_bonus = 0.10
    elif intent == rule_intent:
        agreement = "intent_match_chart_differs"
        agreement_bonus = 0.05
    else:
        agreement = "conflict_with_local_rule"
        if top_score >= 0.55 and top_score - selected_score >= 0.25:
            conflict_penalty = 0.20

    keyword_bonus = 0.05 if evidence else 0.0
    intent_score = 0.35 + 0.35 * selected_score + 0.20 * margin_score + agreement_bonus + keyword_bonus - conflict_penalty
    if not _has_effective_extracted(chart_type, extracted) and not evidence:
        intent_score = min(intent_score, 0.55)

    data = _data_extraction_score(chart_type, extracted, combined)
    chart = _chart_suitability_score(intent, chart_type, extracted, combined, warnings)

    global_penalty = 0.05 if fallback_used else 0.0
    if not _has_effective_extracted(chart_type, extracted):
        global_penalty += 0.15
    if chart["score"] < 0.45 or data["score"] < 0.45:
        global_penalty += 0.05

    confidence = 0.35 * _clamp01(intent_score) + 0.35 * data["score"] + 0.30 * chart["score"] - global_penalty
    if not _has_effective_extracted(chart_type, extracted):
        confidence = min(confidence, 0.70)
    if chart["score"] < 0.45:
        confidence = min(confidence, 0.60)

    return {
        "confidence": _round_score(confidence),
        "intentConfidence": _round_score(intent_score),
        "dataExtractionConfidence": data["score"],
        "chartSuitabilityConfidence": chart["score"],
        "confidenceSource": "local_explainable",
        "confidenceBreakdown": {
            "intent": {
                "score": _round_score(intent_score),
                "ruleIntent": rule_intent,
                "ruleChartType": rule_chart_type,
                "ruleScoreForIntent": _round_score(selected_score),
                "marginScore": _round_score(margin_score),
                "agreement": agreement,
                "evidence": evidence,
                "penalties": ["与本地规则明显冲突"] if conflict_penalty else [],
            },
            "dataExtraction": data,
            "chartSuitability": chart,
            "overall": {
                "score": _round_score(confidence),
                "globalPenalty": _round_score(global_penalty),
                "formula": "0.35*intent + 0.35*dataExtraction + 0.30*chartSuitability - globalPenalty",
            },
        },
    }


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
    warnings = _as_list(out.get("warnings"))
    confidence_info = compute_semantic_confidence(req, out, out, warnings)
    return {
        "intent": out["intent"],
        "chartType": out["chartType"],
        "extracted": out["extracted"],
        "reason": out["reason"],
        **confidence_info,
        "dataQuality": {
            "sourceUsed": "local_rules",
            "structuredEnough": confidence_info["confidence"] >= 0.7,
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
    confidence_info = compute_semantic_confidence(
        req,
        fallback,
        fallback,
        _as_list(fallback.get("warnings")),
        fallback_used=True,
    )
    fallback.update(confidence_info)
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
        "不要输出 confidence、intentConfidence、dataExtractionConfidence、chartSuitabilityConfidence；这些置信度由后端本地规则计算。"
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
        local_rule_result = rule_based_visualization(combined)
        confidence_info = compute_semantic_confidence(req, normalized, local_rule_result, validation_warnings)
        data_quality = parsed.get("dataQuality") if isinstance(parsed.get("dataQuality"), dict) else {}
        data_quality["structuredEnough"] = confidence_info["dataExtractionConfidence"] >= 0.7
        data_quality["confidenceSource"] = "local_explainable"
        source = "deepseek+validated" if validation_warnings else "deepseek"
        return {
            "intent": normalized["intent"],
            "chartType": normalized["chartType"],
            "extracted": normalized["extracted"],
            "reason": str(parsed.get("reason") or normalized.get("reason") or ""),
            **confidence_info,
            "dataQuality": data_quality,
            "scores": local_rule_result.get("scores"),
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

