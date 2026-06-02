import os
from dotenv import load_dotenv


load_dotenv()


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

APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip()
APP_PORT = int(os.getenv("APP_PORT", "8000"))
PREVIEW_DIR = os.getenv("PREVIEW_DIR", "backend/generated/previews").strip()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123").strip()
TEST_USERNAME = os.getenv("TEST_USERNAME", "tester").strip()
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "tester123").strip()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "backend/uploads").strip()

