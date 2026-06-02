import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.config import UPLOAD_DIR
from backend.db import (
    create_uploaded_file,
    get_uploaded_file,
    list_user_uploaded_files,
    record_event,
    soft_delete_user_uploaded_file,
    update_uploaded_file,
)
from backend.deps import require_user
from backend.models import ExtractTextResponse, FileDetailDTO, FileRecordDTO
from backend.services.doc_extract import extract_text_from_document


router = APIRouter()


def _owned_file(file_id: int, user_id: int) -> dict:
    item = get_uploaded_file(file_id)
    if not item or int(item["user_id"]) != user_id or item.get("deleted_at"):
        raise HTTPException(status_code=404, detail="文件不存在")
    return item


@router.get("/files", response_model=list[FileRecordDTO])
def list_files(user: dict = Depends(require_user)) -> list[FileRecordDTO]:
    return [FileRecordDTO(**item) for item in list_user_uploaded_files(int(user["id"]))]


@router.get("/files/{file_id}", response_model=FileDetailDTO)
def get_file_detail(file_id: int, user: dict = Depends(require_user)) -> FileDetailDTO:
    item = _owned_file(file_id, int(user["id"]))
    try:
        pages_detail = json.loads(item.get("pages_data") or "[]")
    except json.JSONDecodeError:
        pages_detail = []
    return FileDetailDTO(**item, pages_detail=pages_detail)


@router.get("/files/{file_id}/download")
def download_file(file_id: int, user: dict = Depends(require_user)) -> FileResponse:
    item = _owned_file(file_id, int(user["id"]))
    path = Path(item["file_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="原始文件不存在")
    return FileResponse(path, media_type=item.get("mime_type") or None, filename=item["original_filename"])


@router.delete("/files/{file_id}")
def delete_file(file_id: int, user: dict = Depends(require_user)) -> dict[str, bool]:
    if not soft_delete_user_uploaded_file(file_id, int(user["id"])):
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"ok": True}


@router.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text(
    file: UploadFile = File(...),
    _: dict = Depends(require_user),
) -> ExtractTextResponse:
    filename = file.filename or "uploaded-file"
    file_id: int | None = None
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("上传文件为空")
        upload_root = Path(UPLOAD_DIR)
        upload_root.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower()
        stored_filename = f"{uuid4().hex}{suffix}"
        stored_path = (upload_root / stored_filename).resolve()
        stored_path.write_bytes(raw)
        file_id = create_uploaded_file(
            int(_["id"]),
            filename,
            stored_filename,
            str(stored_path),
            file.content_type or "",
            len(raw),
        )
        result = extract_text_from_document(filename, raw)
        text = str(result.get("text", "")).strip()
        if not text:
            raise ValueError("未提取到可用文本，请检查文件内容")
        pages_detail = list(result.get("pages_detail", []) or [])
        update_uploaded_file(
            file_id,
            parse_status="success",
            pages=int(result.get("pages", 0) or 0),
            pages_data=pages_detail,
            extracted_text=text,
        )
        record_event(int(_["id"]), "upload")
        return ExtractTextResponse(
            file_id=file_id,
            filename=filename,
            text=text,
            title=str(result.get("title", "") or ""),
            pages=int(result.get("pages", 0) or 0),
            pages_detail=pages_detail,
        )
    except ValueError as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=500, detail=f"extract text failed: {e}")
