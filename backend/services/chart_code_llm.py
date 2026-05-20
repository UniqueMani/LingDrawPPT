from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from backend.models import SlideRequest
from backend.services.chart_context import merge_slide_context
from backend.services.chart_gen import generate_echarts_option
from backend.services.semantic import analyze_semantics


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def validate_echarts_option(opt: Any) -> List[Tuple[str, str]]:
    issues: List[Tuple[str, str]] = []
    if not isinstance(opt, dict):
        return [("error", "echartsOption 不是 JSON 对象")]
    if "series" not in opt and "graphic" not in opt:
        issues.append(("warn", "缺少 series/graphic，可能无法渲染常见统计图"))
    ser = opt.get("series") if "series" in opt else None
    if ser is not None:
        if not isinstance(ser, list) or len(ser) == 0:
            issues.append(("error", "series 为空或类型错误"))
        elif len(ser) > 1:
            leg = opt.get("legend")
            leg_data = leg.get("data") if isinstance(leg, dict) else None
            if not leg_data:
                issues.append(("warn", "多组 series 时建议配置 legend.data，便于区分数据映射"))

    if "xAxis" in opt and ser is not None:
        xa = opt.get("xAxis")
        if isinstance(xa, dict) and xa.get("type") == "category":
            xd = xa.get("data")
            if isinstance(xd, list) and len(xd) == 0:
                issues.append(("warn", "xAxis.data 为空"))
            if not xa.get("name"):
                issues.append(("warn", "建议为 category 横轴设置 name（类别/时间等）"))

    ya = opt.get("yAxis")
    if isinstance(ya, dict) and ya.get("type") == "value" and not ya.get("name"):
        issues.append(("warn", "建议为数值纵轴设置 name（含单位更佳）"))
    elif isinstance(ya, list):
        for i, ax in enumerate(ya):
            if isinstance(ax, dict) and ax.get("type") == "value" and not ax.get("name"):
                issues.append(("warn", f"yAxis[{i}] 建议设置名称以标明单位或口径"))

    return issues


def validate_chartjs_config(cfg: Any) -> List[Tuple[str, str]]:
    issues: List[Tuple[str, str]] = []
    if not isinstance(cfg, dict):
        return [("error", "chartJsConfig 不是 JSON 对象")]
    if "type" not in cfg:
        issues.append(("error", "缺少 Chart.js type（如 bar/line/pie）"))
    data = cfg.get("data")
    if not isinstance(data, dict):
        issues.append(("error", "缺少 data 对象"))
    else:
        if cfg.get("type") in ("bar", "line") and not data.get("labels"):
            issues.append(("warn", "data.labels 为空"))
        ds = data.get("datasets")
        if not isinstance(ds, list) or len(ds) == 0:
            issues.append(("warn", "data.datasets 为空"))
    return issues


def validate_mermaid(src: Any) -> List[Tuple[str, str]]:
    if not isinstance(src, str) or not src.strip():
        return [("error", "mermaid 源码为空或非字符串")]
    s = src.strip()
    if len(s) > 20000:
        return [("error", "mermaid 过长")]
    # 常见图类型前缀
    if not re.match(
        r"^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|xychart|gitGraph|mindmap|timeline)",
        s,
        re.I,
    ):
        return [("warn", "未识别常见 Mermaid 图类型前缀，仍尝试渲染")]
    if re.match(r"^xychart-beta\b", s, re.I):
        for line in s.splitlines():
            stripped = line.strip()
            if stripped.startswith("title ") and not re.match(r'^title\s+"[^"]+"$', stripped):
                return [("error", "xychart-beta 的 title 必须使用英文双引号包裹")]
            if stripped.startswith("x-axis "):
                if not re.match(r'^x-axis(\s+"[^"]+")?\s+\[[^\]]*\]$', stripped):
                    return [("error", "xychart-beta 的 x-axis 必须使用合法的可选标题和类目数组")]
                if "“" in stripped or "”" in stripped:
                    return [("error", "xychart-beta 不支持中文弯引号，请使用英文双引号")]
            if stripped.startswith("y-axis "):
                if not re.match(r'^y-axis(\s+"[^"]+")?\s+[-+]?\d+(\.\d+)?\s+-->\s+[-+]?\d+(\.\d+)?$', stripped):
                    return [("error", "xychart-beta 的 y-axis 必须使用合法的数值范围")]
    return []


def _fallback_from_pipeline(slide: SlideRequest) -> Tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, Any]]:
    sem = analyze_semantics(slide)
    intent = sem.get("intent", "") or "comparison"
    chart_type = sem.get("chartType", "") or "comparison_bar"
    extracted = sem.get("extracted", {}) or {}
    ctx = merge_slide_context(slide.topic, slide.body, slide.data_description)
    opt = generate_echarts_option(
        intent=intent,
        chartType=chart_type,
        topic=slide.topic,
        extracted=extracted if isinstance(extracted, dict) else {},
        context_text=ctx,
    )
    chartjs = _extracted_to_chartjs(intent, chart_type, extracted)
    mermaid = _extracted_to_mermaid(intent, chart_type, extracted, slide.topic)
    meta = {"intent": intent, "chartType": chart_type, "extracted": extracted}
    return opt, chartjs, mermaid, meta


def _extracted_to_chartjs(intent: str, chart_type: str, extracted: Dict[str, Any]) -> Dict[str, Any]:
    ex = extracted or {}
    if chart_type == "trend_line" or intent == "trend":
        x = ex.get("x") or []
        y = ex.get("y") or []
        return {
            "type": "line",
            "data": {
                "labels": [str(v) for v in x],
                "datasets": [{"label": "序列", "data": [float(v) for v in y]}],
            },
            "options": {"responsive": True, "plugins": {"legend": {"display": True}}},
        }
    if chart_type == "proportion_pie" or intent == "proportion":
        labels = ex.get("labels") or []
        values = ex.get("values") or []
        return {
            "type": "pie",
            "data": {
                "labels": [str(v) for v in labels],
                "datasets": [{"label": "占比", "data": [float(v) for v in values]}],
            },
            "options": {"responsive": True},
        }
    labels = ex.get("labels") or ex.get("categories") or ex.get("x") or []
    values = ex.get("values") or ex.get("y") or []
    if not values and ex.get("series") and isinstance(ex["series"], list) and ex["series"]:
        s0 = ex["series"][0]
        if isinstance(s0, dict) and s0.get("values"):
            values = s0.get("values") or []
            labels = ex.get("categories") or labels
    return {
        "type": "bar",
        "data": {
            "labels": [str(v) for v in labels] or ["A", "B"],
            "datasets": [{"label": "值", "data": [float(v) for v in values] or [0, 0]}],
        },
        "options": {"responsive": True, "plugins": {"legend": {"display": False}}},
    }


def _mermaid_text(value: Any, limit: int = 40) -> str:
    text = str(value if value is not None else "").strip() or "未命名"
    replacements = {
        '"': "'",
        "“": "'",
        "”": "'",
        "\n": " ",
        "\r": " ",
        "[": "(",
        "]": ")",
        "{": "(",
        "}": ")",
        "|": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text[:limit]


def _mermaid_quoted(value: Any, limit: int = 40) -> str:
    return '"' + _mermaid_text(value, limit) + '"'


def _float_values(values: Any, limit: int = 12) -> List[float]:
    out: List[float] = []
    if not isinstance(values, list):
        return out
    for value in values[:limit]:
        try:
            out.append(float(value))
        except Exception:
            continue
    return out


def _extracted_to_mermaid(intent: str, chart_type: str, extracted: Dict[str, Any], title: str) -> str:
    ex = extracted or {}
    t = _mermaid_text(title or "图表", 40)
    if chart_type == "proportion_pie" or intent == "proportion":
        labels = ex.get("labels") or []
        values = _float_values(ex.get("values") or [], 10)
        lines = [
            f"    {_mermaid_quoted(labels[i], 28)} : {values[i]:.6g}"
            for i in range(min(len(labels), len(values)))
        ]
        if not lines:
            lines = ['    "A" : 50', '    "B" : 50']
        return f"pie title {t}\n" + "\n".join(lines)
    if chart_type == "process_flow" or intent == "process":
        steps = ex.get("steps") or []
        if len(steps) < 2:
            return "flowchart LR\n    A[步骤1] --> B[步骤2]"
        out = "flowchart LR\n"
        for i, s in enumerate(steps[:12]):
            sid = f"S{i}"
            label = _mermaid_text(s, 24)
            out += f"    {sid}[{label}]\n"
        for i in range(min(len(steps), 12) - 1):
            out += f"    S{i} --> S{i+1}\n"
        return out
    # 柱状/折线：使用 xychart-beta（Mermaid 10+）
    labels = ex.get("labels") or ex.get("categories") or ex.get("x") or []
    values = ex.get("values") or ex.get("y") or []
    if not values and ex.get("series") and isinstance(ex["series"], list) and ex["series"]:
        s0 = ex["series"][0]
        if isinstance(s0, dict):
            values = s0.get("values") or []
            labels = ex.get("categories") or labels
    if not labels:
        labels = ["A", "B"]
    if not values:
        values = [1, 2]
    numeric_values = _float_values(values, 8)
    n = min(len(labels), len(numeric_values), 8)
    labels = [_mermaid_quoted(labels[i], 12) for i in range(n)]
    numeric_values = numeric_values[:n]
    ymax = max(numeric_values) * 1.1 if numeric_values else 10
    if ymax <= 0:
        ymax = 10
    data_list = "[" + ", ".join(f"{v:.6g}" for v in numeric_values) + "]"
    x_list = "[" + ", ".join(labels) + "]"
    mark = "line" if chart_type == "trend_line" or intent == "trend" else "bar"
    return (
        f"xychart-beta\n"
        f'    title "{t}"\n'
        f"    x-axis {x_list}\n"
        f'    y-axis "值" 0 --> {ymax:.6g}\n'
        f"    {mark} {data_list}\n"
    )


def generate_chart_code_bundle(
    slide: SlideRequest,
    targets: List[str],
    instructions: Optional[str],
) -> Dict[str, Any]:
    """
    返回 echartsOption, chartJsConfig, mermaidSource, validation_issues, source
    """
    targets_set = {t.lower() for t in targets} if targets else {"echarts", "chartjs", "mermaid"}
    want_e = "echarts" in targets_set
    want_c = "chartjs" in targets_set
    want_m = "mermaid" in targets_set

    opt: Optional[Dict[str, Any]] = None
    cjs: Optional[Dict[str, Any]] = None
    mer: Optional[str] = None
    source = "fallback"
    raw_llm: Optional[str] = None
    issues: List[Dict[str, str]] = []

    use_llm = bool(DEEPSEEK_API_KEY and OpenAI is not None)

    if use_llm:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        sem = analyze_semantics(slide)
        sys_p = (
            "你是数据可视化工程师。根据幻灯片文本，输出严格 JSON（不要 Markdown），键名固定为："
            "echartsOption, chartJsConfig, mermaidSource（不适用则 null）。"
            "信息表达须准确完整：坐标轴须有 name（含单位如万元、%）；类目轴标明类别或时间；"
            "多系列必须有 legend.data 且与 series.name 一致；tooltip 能区分系列；"
            "柱状/折线需 grid 与 splitLine；饼图须 avoidLabelOverlap。"
            "三套输出描述同一数据，数值与类别标签严格一致。"
            "Mermaid 使用合法 pie / flowchart / xychart-beta；xychart-beta 的 title 必须加英文双引号，"
            "x-axis 类目必须是英文双引号数组，如 x-axis [\"1月\", \"2月\"]；趋势图使用 line。"
        )
        if instructions:
            sys_p += f" 附加要求：{instructions}"
        user_p = json.dumps(
            {
                "topic": slide.topic,
                "body": slide.body,
                "data_description": slide.data_description,
                "semantic_hint": {k: sem.get(k) for k in ("intent", "chartType", "extracted", "reason") if k in sem},
            },
            ensure_ascii=False,
        )
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
                temperature=0.15,
                max_tokens=2500,
                response_format={"type": "json_object"},
            )
            raw_llm = resp.choices[0].message.content or ""
            parsed = _extract_json_obj(raw_llm) or {}
            if isinstance(parsed.get("echartsOption"), dict):
                opt = parsed["echartsOption"]
            if isinstance(parsed.get("chartJsConfig"), dict):
                cjs = parsed["chartJsConfig"]
            if isinstance(parsed.get("mermaidSource"), str):
                mer = parsed["mermaidSource"]
            source = "llm"
        except Exception:
            use_llm = False

    mermaid_needs_repair = want_m and mer is not None and any(sev == "error" for sev, _msg in validate_mermaid(mer))
    if not use_llm or opt is None or cjs is None or mer is None or mermaid_needs_repair:
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
        if source == "llm":
            source = "llm+fallback"
        else:
            source = "fallback"

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
        "source": source,
        "rawLlmExcerpt": (raw_llm[:1200] + "…") if raw_llm and len(raw_llm) > 1200 else raw_llm,
    }
