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
