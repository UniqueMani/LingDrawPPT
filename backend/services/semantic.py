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
    }


def _deepseek_analyze(req: SlideRequest) -> Dict[str, Any]:
    """
    DeepSeek 模式下的语义识别：输出结构化 intent/chartType/extracted（尽量由模型直接给 JSON）。
    """
    if not DEEPSEEK_API_KEY or OpenAI is None:
        return _mock_analyze(req)

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
        }
    except Exception:
        # 模型失败时不影响 demo，可直接降级 mock
        return _mock_analyze(req)


def analyze_semantics(req: SlideRequest) -> Dict[str, Any]:
    runtime_mode = _env_mode_to_runtime(req.mode)
    if runtime_mode == "deepseek":
        return _deepseek_analyze(req)
    return _mock_analyze(req)

