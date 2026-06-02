import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.config import UPLOAD_DIR
from backend.db import get_conn
from backend.deps import require_user
from backend.models import ExtractTextResponse, FileDetailDTO, FileRecordDTO
from backend.services.doc_extract import extract_text_from_document


router = APIRouter()


def _ensure_user_upload_dir(user_id: int) -> Path:
    p = Path(UPLOAD_DIR) / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _row_to_dto(row: dict) -> FileRecordDTO:
    return FileRecordDTO(
        id=int(row["id"]),
        filename=str(row["filename"]),
        original_filename=str(row["original_filename"]),
        file_size=int(row.get("file_size", 0) or 0),
        pages=int(row.get("pages", 0) or 0),
        parse_status=str(row.get("parse_status", "pending") or "pending"),
        parse_error=str(row.get("parse_error", "") or ""),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
) -> ExtractTextResponse:
    user_id = int(user["id"])
    original_filename = file.filename or "uploaded-file"
    raw = await file.read()

    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        result = extract_text_from_document(original_filename, raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"extract text failed: {e}")

    text = str(result.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="未提取到可用文本，请检查文件内容")

    pages = int(result.get("pages", 0) or 0)
    pages_detail = list(result.get("pages_detail", []) or [])

    # ---- 保存原始文件到磁盘 ----
    upload_dir = _ensure_user_upload_dir(user_id)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    safe_filename = f"{original_filename}"
    file_path = upload_dir / safe_filename
    # 避免同名覆盖：加时间戳
    if file_path.exists():
        stem, ext = os.path.splitext(safe_filename)
        file_path = upload_dir / f"{stem}_{int(now.timestamp())}{ext}"

    with open(file_path, "wb") as f:
        f.write(raw)

    # ---- 写入数据库文件记录 ----
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO files
                (user_id, filename, original_filename, file_path, file_size,
                 pages, parse_status, parse_error, preview_dir,
                 pages_data, extracted_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'success', '', '',
                    ?, ?, ?, ?)
            """,
            (
                user_id,
                file_path.name,
                original_filename,
                str(file_path.resolve()),
                len(raw),
                pages,
                json.dumps(pages_detail, ensure_ascii=False),
                text,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
        file_id = int(cur.lastrowid or 0)

    resp = ExtractTextResponse(
        filename=original_filename,
        text=text,
        title=str(result.get("title", "") or ""),
        pages=pages,
        pages_detail=pages_detail,
        file_id=file_id,
    )
    return resp


@router.get("/files", response_model=list[FileRecordDTO])
async def list_files(user: dict = Depends(require_user)) -> list[FileRecordDTO]:
    """获取当前用户的文件列表"""
    user_id = int(user["id"])
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, original_filename, file_path, file_size,
                   pages, parse_status, parse_error, preview_dir,
                   created_at, updated_at
            FROM files
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_row_to_dto(dict(r)) for r in rows]


@router.get("/files/{file_id}", response_model=FileDetailDTO)
async def get_file_detail(
    file_id: int,
    user: dict = Depends(require_user),
) -> FileDetailDTO:
    """获取单个文件的详细信息，含 pages_data 用于恢复"""
    user_id = int(user["id"])
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在或无权访问")
    r = dict(row)
    pages_data_raw = str(r.get("pages_data", "[]") or "[]")
    try:
        pages_data = json.loads(pages_data_raw)
    except json.JSONDecodeError:
        pages_data = []
    return FileDetailDTO(
        id=int(r["id"]),
        filename=str(r["filename"]),
        original_filename=str(r["original_filename"]),
        file_size=int(r.get("file_size", 0) or 0),
        pages=int(r.get("pages", 0) or 0),
        parse_status=str(r.get("parse_status", "pending") or "pending"),
        parse_error=str(r.get("parse_error", "") or ""),
        created_at=str(r["created_at"]),
        updated_at=str(r["updated_at"]),
        pages_data=pages_data,
        extracted_text=str(r.get("extracted_text", "") or ""),
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    user: dict = Depends(require_user),
) -> dict:
    """删除文件记录及磁盘上的原始文件"""
    user_id = int(user["id"])
    with get_conn() as conn:
        row = conn.execute(
            "SELECT file_path FROM files WHERE id = ? AND user_id = ?",
            (file_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文件不存在或无权访问")
        file_path = str(row["file_path"])

        # 删除磁盘文件
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception:
            pass

        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
    return {"ok": True, "deleted_id": file_id}
