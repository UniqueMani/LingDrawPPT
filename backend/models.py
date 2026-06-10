from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SlideType(str, Enum):
    cover = "cover"
    section_divider = "section-divider"
    content = "content"
    unknown = "unknown"


class Mode(str, Enum):
    auto = "auto"
    mock = "mock"
    deepseek = "deepseek"


class SlideRequest(BaseModel):
    topic: str = Field(..., description="幻灯片主题/标题/场景描述")
    body: Optional[str] = Field(None, description="正文内容（可包含要点或描述）")
    data_description: Optional[str] = Field(
        None, description="可选：与图表相关的简易数据/数值描述"
    )
    slide_type: SlideType = Field(SlideType.content, description="幻灯片类型，用于插图策略判断")
    mode: Mode = Field(Mode.auto, description="推理模式：auto/mock/deepseek")


class ChartResponse(BaseModel):
    intent: str
    chartType: str
    echartsOption: Dict[str, Any]
    reason: str
    extracted: Dict[str, Any] = Field(default_factory=dict)


class IllustrationResponse(BaseModel):
    needIllus: bool
    keywords: List[str] = Field(default_factory=list)
    prompt: str = ""
    reason: str = ""


class AnalyzeResponse(BaseModel):
    semantic: Dict[str, Any] = Field(default_factory=dict)
    chart: ChartResponse


class IllustrationStrategyResponse(BaseModel):
    illustration: IllustrationResponse


class ExtractTextResponse(BaseModel):
    filename: str
    text: str
    title: str = ""
    pages: int = 0
    pages_detail: List[Dict[str, Any]] = Field(default_factory=list)
    file_id: int = 0


class FileRecordDTO(BaseModel):
    id: int
    user_id: int
    original_filename: str
    mime_type: str = ""
    file_size: int = 0
    pages: int = 0
    parse_status: str = "processing"
    error_message: str = ""
    created_at: str
    updated_at: str


class FileDetailDTO(FileRecordDTO):
    extracted_text: str = ""
    pages_detail: List[Dict[str, Any]] = Field(default_factory=list)


class OCRRegionRequest(BaseModel):
    preview_url: str
    x: float = Field(..., ge=0, le=1)
    y: float = Field(..., ge=0, le=1)
    width: float = Field(..., gt=0, le=1)
    height: float = Field(..., gt=0, le=1)


class OCRRegionResponse(BaseModel):
    text: str = ""
    source: str = "ocr"


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    organization: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateMeRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    organization: Optional[str] = None
    old_password: Optional[str] = None
    new_password: Optional[str] = None


class UserDTO(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool = True
    full_name: str = ""
    email: str = ""
    organization: str = ""
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserDTO


class UpdateMeResponse(BaseModel):
    user: UserDTO
    token: Optional[str] = None


class UsageStatsResponse(BaseModel):
    events: Dict[str, int] = Field(default_factory=dict)
    detail: List[Dict[str, Any]] = Field(default_factory=list)


class RecordEventRequest(BaseModel):
    event_type: str = Field(..., description="事件类型：upload / analyze / generate / adopt")


class AdminUserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    organization: Optional[str] = None


class AdminUserStatusRequest(BaseModel):
    is_active: bool


class AdminResetPasswordRequest(BaseModel):
    password: str


class AdminUserDTO(UserDTO):
    disabled_at: Optional[str] = None


class UploadedFileDTO(BaseModel):
    id: int
    user_id: int
    username: str
    original_filename: str
    mime_type: str = ""
    file_size: int = 0
    pages: int = 0
    parse_status: str
    error_message: str = ""
    created_at: str
    deleted_at: Optional[str] = None


class UsageLogDTO(BaseModel):
    id: int
    user_id: int
    username: str
    event_type: str
    created_at: str


class AdminAuditLogDTO(BaseModel):
    id: int
    admin_user_id: int
    admin_username: str
    action_type: str
    target_type: str
    target_id: str
    detail: str = ""
    created_at: str


class AdminOverviewDTO(BaseModel):
    total_users: int = 0
    active_users: int = 0
    total_files: int = 0
    failed_files: int = 0
    recent_events: int = 0
    event_counts: Dict[str, int] = Field(default_factory=dict)
    recent_failed_files: List[UploadedFileDTO] = Field(default_factory=list)
    recent_audit_logs: List[AdminAuditLogDTO] = Field(default_factory=list)


class PaginatedResponse(BaseModel):
    items: List[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class ChartCodeValidationIssue(BaseModel):
    target: str
    severity: str
    message: str


class VizLabChartCodeRequest(BaseModel):
    slide: SlideRequest
    targets: List[str] = Field(
        default_factory=lambda: ["echarts", "chartjs", "mermaid"],
    )
    instructions: Optional[str] = None


class VizLabChartCodeResponse(BaseModel):
    echartsOption: Optional[Dict[str, Any]] = None
    chartJsConfig: Optional[Dict[str, Any]] = None
    mermaidSource: Optional[str] = None
    validationIssues: List[ChartCodeValidationIssue] = Field(default_factory=list)
    generatedTargets: List[str] = Field(default_factory=list)
    source: str = "fallback"
    llmAttempted: bool = False
    llmSucceeded: bool = False
    fallbackReason: str = ""
    rawLlmExcerpt: Optional[str] = None


class VizLabIntentResponse(BaseModel):
    semantic: Dict[str, Any] = Field(default_factory=dict)


class VizLabIllustrationRequest(BaseModel):
    slide: SlideRequest
    image_model: str = "flux"
    style_ref_url: Optional[str] = None
    lora_hint: Optional[str] = None
    extra_style_words: Optional[str] = None


class VizLabIllustrationResponse(BaseModel):
    needIllus: bool
    keywords: List[str] = Field(default_factory=list)
    prompt: str = ""
    reason: str = ""
    experiment: Dict[str, Any] = Field(default_factory=dict)


class DocumentStyleProfile(BaseModel):
    domain: str = ""
    style_tokens: List[str] = Field(default_factory=list)
    style_prompt_zh: str = ""
    color_palette: List[str] = Field(default_factory=list)
    negative_style: str = ""
    color_theme: List[str] = Field(default_factory=list)
    visual_density: str = ""
    illustration_style: str = ""
    illustration_level: str = ""
    shape_language: str = ""
    icon_style: str = ""
    layout_style: str = ""
    render_style: str = ""


class SharedEntity(BaseModel):
    id: str
    name: str
    visual_anchor: str
    color_hint: str = ""
    pages: List[int] = Field(default_factory=list)
    frequency: int = 0
    entity_type: str = ""
    importance: float = 0.0
    relations: List[str] = Field(default_factory=list)


class SlideVisualPlan(BaseModel):
    page: int
    topic: str = ""
    slide_role: str = ""
    visual_focus: str = ""
    entity_ids: List[str] = Field(default_factory=list)
    topic_type: str = ""
    content_intent: str = ""
    visual_type: str = ""
    page_role: str = ""
    visual_primitives: List[str] = Field(default_factory=list)
    focus: str = ""
    layout: str = ""
    related_pages: List[int] = Field(default_factory=list)
    global_constraints: str = ""
    page_constraints: str = ""
    primitive_keys: List[str] = Field(default_factory=list)


class DocumentPageInput(BaseModel):
    page: int
    topic: str = ""
    body: str = ""


class AnalyzeDocumentRequest(BaseModel):
    doc_title: str = ""
    pages: List[DocumentPageInput] = Field(default_factory=list)


class AnalyzeDocumentResponse(BaseModel):
    style: DocumentStyleProfile
    entities: List[SharedEntity] = Field(default_factory=list)
    slide_plans: List[SlideVisualPlan] = Field(default_factory=list)
    summary: str = ""
    source: str = "rules"


class DocumentConsistencyPayload(BaseModel):
    style: DocumentStyleProfile
    entities: List[SharedEntity] = Field(default_factory=list)
    slide_plans: List[SlideVisualPlan] = Field(default_factory=list)


class FluxGenerateImageRequest(BaseModel):
    selected_text: str = Field("", description="框选或写入的正文，用于构建出图 prompt")
    topic: Optional[str] = Field(None, description="页面标题，selected_text 为空时作为备选")
    prompt: str = Field("", description="直接指定 prompt（通常留空，由 selected_text 构建）")
    generation_mode: str = Field("standard", description="生成模式：standard 通用模式最多 3 次；fast 极速模式只生成 1 次")
    slide_page: int = Field(1, description="当前幻灯片页码，用于多图协同")
    slide_type: str = Field("content", description="幻灯片类型：cover/section-divider/content，影响评分权重")
    use_doc_style: bool = Field(True, description="启用文档级统一风格约束")
    use_entity_sync: bool = Field(True, description="启用共享实体库跨页一致")
    doc_consistency: Optional[DocumentConsistencyPayload] = Field(
        None, description="文档级风格与实体库（由 /document/analyze-consistency 生成）"
    )
    input_image_url: Optional[str] = Field(None, description="已弃用：万相文生图不支持参考图编辑")
    preview_path: Optional[str] = Field(
        None, description="当前页预览路径，用于评估与页面一致性，如 /previews/xxx.png"
    )
    use_page_preview: bool = Field(False, description="已弃用")
    aspect_ratio: str = Field("16:9", description="输出宽高比：16:9、4:3、1:1、9:16、21:9")
    model: str = Field(
        "wan2.6-t2i",
        description="万相模型，如 wan2.6-t2i、wan2.5-t2i-preview、wan2.2-t2i-flash",
    )
    enable_translation: bool = Field(False, description="保留字段，万相无需翻译")
    prompt_upsampling: bool = Field(False, description="保留字段，请使用 prompt_extend")
    prompt_extend: bool = Field(True, description="开启提示词智能改写")
    extra_style_words: Optional[str] = Field(None, description="追加风格描述")
    safety_tolerance: Optional[int] = Field(None, description="保留字段，万相不使用")


class ImageQualityDimensionScore(BaseModel):
    key: str
    label: str
    score: float
    maxScore: float = 100.0
    deducted: float = 0.0
    weight: float
    detail: str
    deductionReason: str = ""


class ImageQualityEvaluation(BaseModel):
    passed: bool
    totalScore: float
    passThreshold: float
    dimensions: List[ImageQualityDimensionScore] = Field(default_factory=list)
    feedback: str = ""


class ImageJudgeFix(BaseModel):
    issueArea: str
    severity: str
    problem: str
    constraint: str
    preserve: List[str] = Field(default_factory=list)
    priority: int = 1


class ImageJudgeFeedback(BaseModel):
    feedbackConfidence: float
    cannotModify: List[str] = Field(default_factory=list)
    fixes: List[ImageJudgeFix] = Field(default_factory=list)
    lowScoreDimensions: Dict[str, float] = Field(default_factory=dict)
    discarded: bool = False
    source: str = "rules"


class ImageGenAttemptLog(BaseModel):
    attempt: int
    promptUsed: str
    resultImageUrl: str
    evaluation: ImageQualityEvaluation
    judgeFeedback: Optional[ImageJudgeFeedback] = None


class FluxGenerateImageResponse(BaseModel):
    taskId: str
    resultImageUrl: str
    originImageUrl: Optional[str] = None
    promptUsed: str
    mode: str = "generate"
    attempts: int = 1
    regenerated: bool = False
    selectedAttempt: int = 1
    evaluation: Optional[ImageQualityEvaluation] = None
    attemptsLog: List[ImageGenAttemptLog] = Field(default_factory=list)
