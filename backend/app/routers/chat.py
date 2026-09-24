"""
POST /chat — shipment-aware demo chatbot.

Reuses existing risk assessment and alerts. Does not train models or write alerts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import chat as chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=schemas.ChatResponse)
def post_chat(body: schemas.ChatRequest, db: Session = Depends(get_db)):
    result = chat_service.answer(db, body.message.strip(), body.shipment_id)
    if result.get("missing_shipment"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment {body.shipment_id} not found",
        )
    return schemas.ChatResponse(
        reply=result["reply"],
        shipment_id=result.get("shipment_id"),
        source=result.get("source", "fallback"),
    )
