from typing import Any, Dict, List

from backend.models import SlideRequest
from backend.services.preprocessor import preprocess_text


def _dedup_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        x2 = x.strip()
        if not x2 or x2 in seen:
            continue
        seen.add(x2)
        out.append(x2)
    return out


def _intent_keywords(intent: str) -> List[str]:
    return {
        "trend": ["增长曲线", "折线图", "发展趋势", "未来规划"],
        "comparison": ["对比图", "评估", "排行榜", "差异", "分组对比"],
        "proportion": ["市场份额", "占比", "饼图结构", "比例关系"],
        "process": ["流程", "阶段", "步骤", "推进"],
        "hierarchy": ["层级结构", "组织架构", "树状图", "关联"],
        "relation": ["流向", "转化", "桑基", "路径", "迁移"],
    }.get(intent, ["信息可视化", "抽象图形"])


def generate_illustration_strategy(req: SlideRequest, intent: str) -> Dict[str, Any]:
    """
    插图策略：是否需要插图 + 检索关键词 +（可选）生成 Prompt。
    这里优先做“可演示”的稳定输出，因此使用规则而非强依赖生成模型。
    """
    pre = preprocess_text(req.topic, req.body, req.data_description)
    base_keywords = pre.get("keywords", []) or []

    # 封面/分隔页通常更需要图像
    slide_type = req.slide_type.value if hasattr(req.slide_type, "value") else str(req.slide_type)
    need = slide_type in {"cover", "section-divider"}

    # 内容页：如果语义是趋势/流程/层级，图像也有帮助
    if slide_type == "content" and intent in {"trend", "process", "hierarchy", "relation"}:
        need = True

    intent_kw = _intent_keywords(intent)

    keywords = _dedup_keep_order(
        [
            req.topic.strip() or "infographic",
            *base_keywords[:4],
            *intent_kw[:5],
            "flat vector",
            "modern infographic",
            "no text",
            "soft gradient",
        ]
    )

    keywords = keywords[:12]

    prompt = (
        "为PPT制作一张“抽象信息可视化插图”，"
        f"主题是: {req.topic or 'LingDraw PPT'}，"
        f"风格: 扁平化矢量、现代信息图、柔和渐变、无文字、对比清晰。"
        f"需要体现: {', '.join(intent_kw[:3])}。"
        "画面元素尽量与图表概念一致（折线/对比/占比/流程/层级），"
        "避免出现真实人物照片、具体商标和可读文字。"
    )

    reason = f"根据 slide_type='{slide_type}' 与 intent='{intent}' 的可视化需求，输出检索关键词与通用生成 Prompt。"

    return {
        "needIllus": need,
        "keywords": keywords,
        "prompt": prompt,
        "reason": reason,
    }

