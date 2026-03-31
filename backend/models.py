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


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    organization: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserDTO(BaseModel):
    id: int
    username: str
    is_admin: bool
    full_name: str = ""
    email: str = ""
    organization: str = ""
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserDTO
