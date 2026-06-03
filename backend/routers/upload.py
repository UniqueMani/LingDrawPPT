from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.config import UPLOAD_DIR
from backend.db import create_uploaded_file, record_event, update_uploaded_file
from backend.deps import require_user
from backend.models import ExtractTextResponse
from backend.services.doc_extract import extract_text_from_document


router = APIRouter()


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
        update_uploaded_file(file_id, parse_status="success", pages=int(result.get("pages", 0) or 0))
        record_event(int(_["id"]), "upload")
        return ExtractTextResponse(
            filename=filename,
            text=text,
            title=str(result.get("title", "") or ""),
            pages=int(result.get("pages", 0) or 0),
            pages_detail=list(result.get("pages_detail", []) or []),
        )
    except ValueError as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if file_id is not None:
            update_uploaded_file(file_id, parse_status="failed", error_message=str(e))
        raise HTTPException(status_code=500, detail=f"extract text failed: {e}")
