from fastapi import APIRouter, Depends, HTTPException

from backend.deps import require_user
from backend.models import OCRRegionRequest, OCRRegionResponse
from backend.services.ocr_region import recognize_region


router = APIRouter()


@router.post("/ocr-region", response_model=OCRRegionResponse)
async def ocr_region(
    request: OCRRegionRequest,
    _: dict = Depends(require_user),
) -> OCRRegionResponse:
    try:
        text = recognize_region(
            request.preview_url,
            request.x,
            request.y,
            request.width,
            request.height,
        )
        return OCRRegionResponse(text=text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
