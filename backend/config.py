import os
from pathlib import Path

from dotenv import load_dotenv

# 固定从仓库根目录加载 .env（避免工作目录不同或 --reload 未监视 .env 导致读不到）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=True)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

# 默认走 Mock，避免没有 API Key 时演示失败
MOCK_MODE = _env_bool("MOCK_MODE", True)
if not DEEPSEEK_API_KEY:
    MOCK_MODE = True

USE_DEEPSEEK = not MOCK_MODE

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()

# 阿里云百炼 · 万相文生图 V2（DashScope）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
# 北京地域默认；新加坡用 https://dashscope-intl.aliyuncs.com
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com"
).strip()
WAN_T2I_MODEL = os.getenv("WAN_T2I_MODEL", "wan2.6-t2i").strip()
WAN_T2I_POLL_INTERVAL_SEC = float(os.getenv("WAN_T2I_POLL_INTERVAL_SEC", "3"))
WAN_T2I_MAX_WAIT_SEC = float(os.getenv("WAN_T2I_MAX_WAIT_SEC", "300"))

# 配图质量评估（Generate → Evaluate → Regenerate）
IMAGE_EVAL_PASS_SCORE = float(os.getenv("IMAGE_EVAL_PASS_SCORE", "72"))
IMAGE_GEN_MAX_ATTEMPTS = int(os.getenv("IMAGE_GEN_MAX_ATTEMPTS", "3"))
IMAGE_EVAL_USE_VL = _env_bool("IMAGE_EVAL_USE_VL", True)
IMAGE_EVAL_VL_MODEL = os.getenv("IMAGE_EVAL_VL_MODEL", "qwen-vl-plus").strip()

# 配图增量裁判（低分维度 → 结构化约束 → 下一轮 Prompt）
IMAGE_JUDGE_USE_VL = _env_bool("IMAGE_JUDGE_USE_VL", True)
IMAGE_JUDGE_LOW_THRESHOLD = float(os.getenv("IMAGE_JUDGE_LOW_THRESHOLD", "70"))
IMAGE_JUDGE_CONFIDENCE_GATE = float(os.getenv("IMAGE_JUDGE_CONFIDENCE_GATE", "0.6"))
IMAGE_JUDGE_MAX_FEEDBACK = int(os.getenv("IMAGE_JUDGE_MAX_FEEDBACK", "3"))
IMAGE_JUDGE_MAX_FIX_TOKENS = int(os.getenv("IMAGE_JUDGE_MAX_FIX_TOKENS", "20"))

APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip()
APP_PORT = int(os.getenv("APP_PORT", "8000"))
PREVIEW_DIR = os.getenv("PREVIEW_DIR", "backend/generated/previews").strip()
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "backend/generated/uploads").strip()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123").strip()
TEST_USERNAME = os.getenv("TEST_USERNAME", "tester").strip()
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "tester123").strip()

