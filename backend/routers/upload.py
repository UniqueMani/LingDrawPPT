import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.config import UPLOAD_DIR
from backend.db import (
    create_uploaded_file,
    get_user_uploaded_file,
    list_user_uploaded_files,
    record_event,
    soft_delete_uploaded_file,
    update_uploaded_file,
    update_uploaded_file_result,
)
from backend.deps import require_user
from backend.models import ExtractTextResponse, FileDetailDTO, FileRecordDTO
from backend.services.doc_extract import extract_text_from_document


router = APIRouter()


def _file_record(row: dict) -> FileRecordDTO:
    return FileRecordDTO(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        original_filename=str(row["original_filename"]),
        mime_type=str(row.get("mime_type", "") or ""),
        file_size=int(row.get("file_size", 0) or 0),
        pages=int(row.get("pages", 0) or 0),
        parse_status=str(row.get("parse_status", "processing") or "processing"),
        error_message=str(row.get("error_message", "") or ""),
        created_at=str(row["created_at"]),
        updated_at=str(row.get("updated_at") or row["created_at"]),
    )


@router.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
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
            int(user["id"]),
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
        pages = int(result.get("pages", 0) or 0)
        pages_detail = list(result.get("pages_detail", []) or [])
        update_uploaded_file_result(
            file_id,
            parse_status="success",
            pages=pages,
            extracted_text=text,
            pages_detail=json.dumps(pages_detail, ensure_ascii=False),
        )
        record_event(int(user["id"]), "upload")
        return ExtractTextResponse(
            filename=filename,
            text=text,
            title=str(result.get("title", "") or ""),
            pages=pages,
            pages_detail=pages_detail,
            file_id=file_id or 0,
        )
    except ValueError as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=500, detail=f"extract text failed: {e}")


@router.get("/files", response_model=list[FileRecordDTO])
async def list_files(user: dict = Depends(require_user)) -> list[FileRecordDTO]:
    return [_file_record(row) for row in list_user_uploaded_files(int(user["id"]))]


@router.get("/files/{file_id}", response_model=FileDetailDTO)
async def get_file_detail(file_id: int, user: dict = Depends(require_user)) -> FileDetailDTO:
    row = get_user_uploaded_file(file_id, int(user["id"]))
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        pages_detail = json.loads(str(row.get("pages_detail", "[]") or "[]"))
    except json.JSONDecodeError:
        pages_detail = []
    record = _file_record(row)
    return FileDetailDTO(
        id=record.id,
        user_id=record.user_id,
        original_filename=record.original_filename,
        mime_type=record.mime_type,
        file_size=record.file_size,
        pages=record.pages,
        parse_status=record.parse_status,
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
        extracted_text=str(row.get("extracted_text", "") or ""),
        pages_detail=pages_detail if isinstance(pages_detail, list) else [],
    )


@router.get("/files/{file_id}/download")
async def download_file(file_id: int, user: dict = Depends(require_user)) -> FileResponse:
    row = get_user_uploaded_file(file_id, int(user["id"]))
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    path = Path(str(row.get("file_path", "")))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="stored file missing")
    media_type = str(row.get("mime_type", "") or "application/octet-stream")
    return FileResponse(path, filename=str(row["original_filename"]), media_type=media_type)


@router.delete("/files/{file_id}")
async def delete_file(file_id: int, user: dict = Depends(require_user)) -> dict:
    row = get_user_uploaded_file(file_id, int(user["id"]))
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    file_path = str(row.get("file_path", ""))
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    deleted = soft_delete_uploaded_file(file_id)
    return {"ok": deleted, "deleted_id": file_id}
