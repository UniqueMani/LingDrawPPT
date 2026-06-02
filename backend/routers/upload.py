from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

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
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("上传文件为空")
        result = extract_text_from_document(filename, raw)
        text = str(result.get("text", "")).strip()
        if not text:
            raise ValueError("未提取到可用文本，请检查文件内容")
        return ExtractTextResponse(
            filename=filename,
            text=text,
            title=str(result.get("title", "") or ""),
            pages=int(result.get("pages", 0) or 0),
            pages_detail=list(result.get("pages_detail", []) or []),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"extract text failed: {e}")
