from typing import List

from fastapi import APIRouter, Depends, HTTPException

from backend.db import record_event
from backend.deps import require_user
from backend.models import (
    AnalyzeDocumentRequest,
    AnalyzeDocumentResponse,
    DocumentStyleProfile,
    SharedEntity,
    SlideVisualPlan,
)
from backend.services.doc_consistency import analyze_document

router = APIRouter()


@router.post("/document/analyze-consistency", response_model=AnalyzeDocumentResponse)
async def analyze_document_consistency(
    body: AnalyzeDocumentRequest,
    user: dict = Depends(require_user),
) -> AnalyzeDocumentResponse:
    try:
        pages = [
            {
                "page": item.page,
                "topic": item.topic,
                "body": item.body or "",
            }
            for item in body.pages
        ]
        raw = analyze_document(pages, doc_title=body.doc_title or "")
        record_event(int(user["id"]), "analyze")

        style = DocumentStyleProfile(**raw["style"])
        entities = [SharedEntity(**e) for e in raw.get("entities") or []]
        slide_plans = [SlideVisualPlan(**p) for p in raw.get("slide_plans") or []]
        return AnalyzeDocumentResponse(
            style=style,
            entities=entities,
            slide_plans=slide_plans,
            summary=str(raw.get("summary") or ""),
            source=str(raw.get("source") or "rules"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"document analyze failed: {e}") from e
