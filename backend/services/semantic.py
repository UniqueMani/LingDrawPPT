import json
import re
from typing import Any, Dict, Optional

try:
    # openai>=1.x
    from openai import OpenAI  # type: ignore
except Exception:
    # openai<1.x（或版本不匹配）时，示例改为自动降级 mock
    OpenAI = None  # type: ignore

from backend.config import DEEPSEEK_API_KEY, MOCK_MODE, USE_DEEPSEEK, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from backend.models import Mode, SlideRequest
from backend.services.preprocessor import (
    parse_hierarchy_chain,
    parse_label_value_pairs,
    parse_percent_map,
    parse_steps,
    parse_time_series,
    preprocess_text,
)


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


def _heuristic_intent(combined: str) -> str:
    text = combined or ""

    # 比例
    if re.search(r"-?\d+(?:\.\d+)?\s*%", text):
        return "proportion"

    # 流程
    if any(k in text for k in ["流程", "步骤", "阶段", "环节"]) or "->" in text or "→" in text:
        return "process"

    # 层级（组织/树/层级链）
    if any(k in text for k in ["层级", "树", "组织", "层次", "层级关系"]) or ">" in text or "/" in text:
        chain = parse_hierarchy_chain(text)
        if len(chain) >= 3:
            return "hierarchy"

    # 趋势
    if any(k in text for k in ["趋势", "逐年", "增长", "下降", "变化", "每年", "折线", "time series"]):
        return "trend"

    # 对比
    if any(k in text for k in ["对比", "比较", "vs", "vs.", "相比"]):
        return "comparison"

    # 默认基于数据特征兜底
    lv = parse_label_value_pairs(text)
    if len(lv) >= 2:
        return "comparison"
    ts = parse_time_series(text)
    if len(ts[0]) >= 2:
        return "trend"
    return "comparison"


def _map_intent_to_chart_type(intent: str) -> str:
    return {
        "trend": "trend_line",
        "comparison": "comparison_bar",
        "proportion": "proportion_pie",
        "process": "process_flow",
        "hierarchy": "hierarchy_tree",
    }.get(intent, "trend_line")


def _mock_analyze(req: SlideRequest) -> Dict[str, Any]:
    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")
    intent = _heuristic_intent(combined)
    chartType = _map_intent_to_chart_type(intent)

    extracted: Dict[str, Any] = {}
    reason = ""

    if intent == "trend":
        x, y = parse_time_series(combined)
        extracted = {"x": x, "y": y, "unit": ""}
        reason = "检测到随时间变化的描述，选择折线图展示趋势。"
    elif intent == "comparison":
        pairs = parse_label_value_pairs(combined)
        labels = [p[0] for p in pairs][:8]
        values = [p[1] for p in pairs][:8]
        extracted = {"labels": labels, "values": values}
        reason = "检测到多个对象/类别及对应数值，选择柱状图进行对比。"
    elif intent == "proportion":
        pairs = parse_percent_map(combined)
        labels = [p[0] for p in pairs][:8]
        values = [p[1] for p in pairs][:8]
        extracted = {"labels": labels, "values": values}
        reason = "检测到百分比占比信息，选择饼图展示比例结构。"
    elif intent == "process":
        steps = parse_steps(combined)
        extracted = {"steps": steps[:10]}
        reason = "检测到步骤/流程式表达，选择流程图展示阶段关系。"
    elif intent == "hierarchy":
        chain = parse_hierarchy_chain(combined)
        extracted = {"chain": chain[:10]}
        reason = "检测到层级/组织式链路表达，选择树图展示层级结构。"
    else:
        extracted = {}
        reason = "未能可靠识别意图，使用默认折线图模板。"

    # 兜底：如果 extracted 为空，补一点点结构，避免 chart_gen 崩溃
    if intent in {"trend", "comparison", "proportion"} and not extracted:
        extracted = {"x": [], "y": []} if intent == "trend" else {"labels": [], "values": []}
    if intent == "process" and "steps" not in extracted:
        extracted["steps"] = []
    if intent == "hierarchy" and "chain" not in extracted:
        extracted["chain"] = []

    return {"intent": intent, "chartType": chartType, "extracted": extracted, "reason": reason}


def _deepseek_analyze(req: SlideRequest) -> Dict[str, Any]:
    """
    DeepSeek 模式下的语义识别：输出结构化 intent/chartType/extracted（尽量由模型直接给 JSON）。
    """
    if not DEEPSEEK_API_KEY or OpenAI is None:
        return _mock_analyze(req)

    pre = preprocess_text(req.topic, req.body, req.data_description)
    combined = pre.get("combined", "")

    system_prompt = (
        "你是一个PPT可视化助手。给定一页PPT文本(标题+正文+可选数据描述)，"
        "请在以下意图中选择一个：trend(趋势), comparison(对比), proportion(比例), process(流程), hierarchy(层级)。"
        "然后输出用于ECharts渲染的结构化结果。"
        "必须输出严格JSON对象，且只输出JSON，不要输出多余文本。"
    )

    user_prompt = (
        f"标题/主题: {req.topic}\n"
        f"正文: {req.body or ''}\n"
        f"数据描述: {req.data_description or ''}\n\n"
        "输出JSON格式为：\n"
        "{\n"
        '  "intent": "trend|comparison|proportion|process|hierarchy",\n'
        '  "chartType": "trend_line|comparison_bar|proportion_pie|process_flow|hierarchy_tree",\n'
        '  "reason": "一句话解释选择原因",\n'
        '  "extracted": { ... 具体字段随intent而定 }\n'
        "}\n\n"
        "extracted字段约定：\n"
        "- trend: {\"x\": [分类/年份字符串], \"y\": [数值列表]}\n"
        "- comparison: {\"labels\": [名称], \"values\": [数值]}\n"
        "- proportion: {\"labels\": [名称], \"values\": [百分比数值]}\n"
        "- process: {\"steps\": [步骤名称...]}\n"
        "- hierarchy: {\"chain\": [层级链...]}\n"
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
        return parsed
    except Exception:
        # 模型失败时不影响 demo，可直接降级 mock
        return _mock_analyze(req)


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)

