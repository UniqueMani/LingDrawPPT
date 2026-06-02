import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import APP_HOST, APP_PORT
from backend.config import ADMIN_PASSWORD, ADMIN_USERNAME, TEST_PASSWORD, TEST_USERNAME
from backend.db import init_db
from backend.routers.admin import router as admin_router
from backend.routers.analyze import router as analyze_router
from backend.routers.auth import router as auth_router
from backend.routers.illustration import router as illustration_router
from backend.routers.upload import router as upload_router
from backend.routers.viz_lab import router as viz_lab_router
from backend.services.auth import ensure_admin_user, ensure_normal_user


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("lingdraw-ppt-demo")


app = FastAPI(title="LingDraw PPT Demo", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api", tags=["analyze"])
app.include_router(illustration_router, prefix="/api", tags=["illustration"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(admin_router, prefix="/api", tags=["admin"])
app.include_router(viz_lab_router, prefix="/api", tags=["viz-lab"])


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        ensure_admin_user(ADMIN_USERNAME, ADMIN_PASSWORD)
    if TEST_USERNAME and TEST_PASSWORD:
        ensure_normal_user(TEST_USERNAME, TEST_PASSWORD)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting LingDraw PPT Demo at %s:%s", APP_HOST, APP_PORT)
    uvicorn.run("backend.main:app", host=APP_HOST, port=APP_PORT, reload=True)

