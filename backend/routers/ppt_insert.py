import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.db import get_user_uploaded_file, record_event, update_uploaded_file_result
from backend.deps import require_user
from backend.models import (
    InsertImageRequest,
    InsertImageResponse,
    ListPageImagesRequest,
    ListPageImagesResponse,
    PptPagePicture,
    RecommendPlacementRequest,
    RecommendPlacementResponse,
    RemoveImageRequest,
    RemoveImageResponse,
    RemoveLastImageRequest,
    RemoveLastImageResponse,
    StageImageRequest,
    StageImageResponse,
    UpdateImagePlacementRequest,
    UpdateImagePlacementResponse,
)
from backend.services.ppt_insert import (
    download_image_bytes,
    insert_image_into_pptx,
    is_pptx_filename,
    list_page_pictures,
    load_pages_detail,
    page_detail,
    read_picture_bytes,
    read_staged_image,
    recommend_placement_for_page,
    refresh_page_preview,
    remove_last_picture_from_pptx,
    remove_picture_by_index,
    save_staged_image,
    update_picture_placement,
)


router = APIRouter()
logger = logging.getLogger(__name__)


def _load_file_row(file_id: int, user_id: int) -> dict:
    row = get_user_uploaded_file(file_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    return row


def _ensure_pptx(row: dict) -> None:
    filename = str(row.get("original_filename") or "")
    if not is_pptx_filename(filename):
        raise HTTPException(status_code=400, detail="仅支持 .pptx 文件插入配图")


def _persist_page_preview(file_id: int, row: dict, pages_detail: list, page: int) -> dict:
    detail = page_detail(pages_detail, page)
    update_uploaded_file_result(
        file_id,
        parse_status=str(row.get("parse_status") or "success"),
        pages=int(row.get("pages") or 0),
        error_message=str(row.get("error_message") or ""),
        extracted_text=str(row.get("extracted_text") or ""),
        pages_detail=json.dumps(pages_detail, ensure_ascii=False),
    )
    return detail


def _mark_page_preview_pending(file_id: int, row: dict, page: int) -> None:
    """配图变更后立即标记预览失效，避免前端误用旧 PNG。"""
    pages_detail = load_pages_detail(str(row.get("pages_detail", "[]") or "[]"))
    detail = page_detail(pages_detail, page)
    if detail is None:
        return
    detail["preview_url"] = ""
    detail["thumbnail_url"] = ""
    detail["preview_updated_at"] = 0
    update_uploaded_file_result(
        file_id,
        parse_status=str(row.get("parse_status") or "success"),
        pages=int(row.get("pages") or 0),
        error_message=str(row.get("error_message") or ""),
        extracted_text=str(row.get("extracted_text") or ""),
        pages_detail=json.dumps(pages_detail, ensure_ascii=False),
    )


def _background_refresh_page_preview(file_id: int, user_id: int, page: int) -> None:
    try:
        row = get_user_uploaded_file(file_id, user_id)
        if not row:
            return
        pptx_path = Path(str(row.get("file_path") or ""))
        if not pptx_path.is_file():
            return
        pages_detail = load_pages_detail(str(row.get("pages_detail", "[]") or "[]"))
        pages_detail = refresh_page_preview(
            original_filename=str(row.get("original_filename") or "document.pptx"),
            pptx_path=pptx_path,
            pages_detail=pages_detail,
            page=page,
        )
        _persist_page_preview(file_id, row, pages_detail, page)
    except Exception as exc:
        logger.warning("background page preview refresh failed: %s", exc)


@router.post("/ppt/recommend-placement", response_model=RecommendPlacementResponse)
async def recommend_placement(
    body: RecommendPlacementRequest,
    user: dict = Depends(require_user),
) -> RecommendPlacementResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pages_detail = load_pages_detail(str(row.get("pages_detail", "[]") or "[]"))
    try:
        recommended, occupied, detail = recommend_placement_for_page(
            pages_detail,
            page=body.page,
            aspect_ratio=body.aspect_ratio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RecommendPlacementResponse(
        recommended=recommended,
        occupied_blocks=occupied,
        preview_url=str(detail.get("preview_url") or ""),
        page_width=float(detail["page_width"]) if detail.get("page_width") else None,
        page_height=float(detail["page_height"]) if detail.get("page_height") else None,
    )


@router.post("/ppt/list-page-images", response_model=ListPageImagesResponse)
async def list_page_images(
    body: ListPageImagesRequest,
    user: dict = Depends(require_user),
) -> ListPageImagesResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")
    try:
        pictures, page_width, page_height = list_page_pictures(pptx_path=pptx_path, page=body.page)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ListPageImagesResponse(
        pictures=[PptPagePicture(**item) for item in pictures],
        page_width=float(page_width),
        page_height=float(page_height),
    )


@router.get("/ppt/shape-image")
async def get_shape_image(
    file_id: int = Query(..., ge=1),
    page: int = Query(..., ge=1),
    shape_index: int = Query(..., ge=0),
    user: dict = Depends(require_user),
) -> Response:
    row = _load_file_row(file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")
    try:
        content, media_type = read_picture_bytes(
            pptx_path=pptx_path,
            page=page,
            shape_index=shape_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type=media_type)


@router.post("/ppt/insert-image", response_model=InsertImageResponse)
async def insert_image(
    body: InsertImageRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_user),
) -> InsertImageResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")

    try:
        image_bytes = await download_image_bytes(body.image_url)
        picture_info = await asyncio.to_thread(
            insert_image_into_pptx,
            pptx_path=pptx_path,
            page=body.page,
            image_bytes=image_bytes,
            placement=body.placement.model_dump(),
        )
        _mark_page_preview_pending(body.file_id, row, body.page)
        background_tasks.add_task(_background_refresh_page_preview, body.file_id, int(user["id"]), body.page)
        record_event(int(user["id"]), "ppt_insert")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"insert image failed: {exc}") from exc

    return InsertImageResponse(
        ok=True,
        page=body.page,
        preview_url="",
        download_url=f"/api/files/{body.file_id}/download",
        picture=PptPagePicture(**picture_info),
        message="配图已写入 PPT 文件，点击幻灯片中的图片可继续调整",
    )


@router.post("/ppt/update-image-placement", response_model=UpdateImagePlacementResponse)
async def update_image_placement(
    body: UpdateImagePlacementRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_user),
) -> UpdateImagePlacementResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")

    try:
        update_picture_placement(
            pptx_path=pptx_path,
            page=body.page,
            shape_index=body.shape_index,
            placement=body.placement.model_dump(),
        )
        _mark_page_preview_pending(body.file_id, row, body.page)
        background_tasks.add_task(_background_refresh_page_preview, body.file_id, int(user["id"]), body.page)
        record_event(int(user["id"]), "ppt_update_image")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"update image failed: {exc}") from exc

    return UpdateImagePlacementResponse(
        ok=True,
        page=body.page,
        preview_url="",
        message=f"第 {body.page} 页配图位置已更新",
    )


@router.post("/ppt/remove-image", response_model=RemoveImageResponse)
async def remove_image(
    body: RemoveImageRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_user),
) -> RemoveImageResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")

    try:
        removed = remove_picture_by_index(
            pptx_path=pptx_path,
            page=body.page,
            shape_index=body.shape_index,
        )
        if not removed:
            return RemoveImageResponse(
                ok=True,
                page=body.page,
                removed=False,
                message=f"第 {body.page} 页未找到指定配图",
            )
        _mark_page_preview_pending(body.file_id, row, body.page)
        background_tasks.add_task(_background_refresh_page_preview, body.file_id, int(user["id"]), body.page)
        record_event(int(user["id"]), "ppt_remove_image")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"remove image failed: {exc}") from exc

    return RemoveImageResponse(
        ok=True,
        page=body.page,
        removed=True,
        preview_url="",
        message=f"第 {body.page} 页配图已删除",
    )


@router.post("/ppt/remove-last-image", response_model=RemoveLastImageResponse)
async def remove_last_image(
    body: RemoveLastImageRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_user),
) -> RemoveLastImageResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    pptx_path = Path(str(row.get("file_path") or ""))
    if not pptx_path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")

    try:
        removed = remove_last_picture_from_pptx(pptx_path=pptx_path, page=body.page)
        if not removed:
            return RemoveLastImageResponse(
                ok=True,
                page=body.page,
                removed=False,
                message=f"第 {body.page} 页未找到可撤销的配图",
            )
        _mark_page_preview_pending(body.file_id, row, body.page)
        background_tasks.add_task(_background_refresh_page_preview, body.file_id, int(user["id"]), body.page)
        record_event(int(user["id"]), "ppt_remove_image")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"remove image failed: {exc}") from exc

    return RemoveLastImageResponse(
        ok=True,
        page=body.page,
        removed=True,
        preview_url="",
        message=f"第 {body.page} 页最后一张配图已删除",
    )


@router.post("/ppt/stage-image", response_model=StageImageResponse)
async def stage_image(
    body: StageImageRequest,
    user: dict = Depends(require_user),
) -> StageImageResponse:
    row = _load_file_row(body.file_id, int(user["id"]))
    _ensure_pptx(row)
    try:
        image_url = save_staged_image(int(user["id"]), body.image_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StageImageResponse(image_url=image_url)


@router.get("/ppt/staged/{token}")
async def get_staged_image(token: str, user: dict = Depends(require_user)) -> Response:
    prefix = f"{int(user['id'])}_"
    if not token.startswith(prefix):
        raise HTTPException(status_code=404, detail="staged image not found")
    try:
        content = read_staged_image(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=content, media_type="image/png")
