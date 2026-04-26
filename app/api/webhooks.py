import logging
from typing import Union

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.schemas.webhook import GenericInboundPayload
from app.workers.jobs import process_calendar_inbound, process_email_inbound, process_whatsapp_inbound

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_whatsapp(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    logger.info(f"WhatsApp verification request: mode={hub_mode}, token={hub_verify_token}, challenge={hub_challenge}")
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp verification successful")
        return hub_challenge
    logger.error(f"WhatsApp verification failed: mode={hub_mode}, expected_token={settings.whatsapp_verify_token}, received_token={hub_verify_token}")
    raise HTTPException(status_code=403, detail="Invalid verify token")


@router.post("/whatsapp")
def inbound_whatsapp(webhook_payload: dict) -> dict[str, str]:
    logger.info("Received WhatsApp webhook: %s", webhook_payload)
    # Parse Meta Cloud API webhook format
    try:
        changes = webhook_payload.get("entry", [{}])[0].get("changes", [{}])[0]
        message_data = changes.get("value", {})
        messages = message_data.get("messages", [])
        statuses = message_data.get("statuses", [])

        # Handle status updates (delivery confirmations, etc.)
        if statuses and not messages:
            logger.info("Received status update webhook - no messages to process")
            return {"status": "status_update_only"}

        if not messages:
            logger.info("No messages in webhook payload")
            return {"status": "no_messages"}

        msg = messages[0]
        external_message_id = msg.get("id", "")
        external_phone = msg.get("from", "")

        text = ""
        if "text" in msg:
            text = msg["text"].get("body", "")
        elif "interactive" in msg:
            text = msg["interactive"].get("button_reply", {}).get("title", "")

        if not text:
            logger.info("No text in message")
            return {"status": "no_text"}

        logger.info("Processing WhatsApp message from %s: %s", external_phone, text)
        process_whatsapp_inbound.delay(
            external_message_id=external_message_id,
            text=text,
            phone=external_phone,
            metadata=message_data,
        )
        return {"status": "accepted"}
    except (IndexError, KeyError) as e:
        logger.error("Error parsing WhatsApp webhook: %s", e)
        return {"status": "error", "detail": str(e)}


@router.post("/email")
def inbound_email(
    payload: GenericInboundPayload,
    x_inbound_secret: Union[str, None] = Header(default=None),
) -> dict[str, str]:
    if x_inbound_secret != settings.email_inbound_secret:
        raise HTTPException(status_code=403, detail="Invalid inbound secret")

    process_email_inbound.delay(payload.model_dump())
    return {"status": "accepted"}


@router.post("/test/whatsapp")
def test_whatsapp_message(text: str) -> dict[str, str]:
    """Test endpoint to manually trigger WhatsApp message processing"""
    logger.info("Test WhatsApp message: %s", text)

    # Use test recipient from config
    test_phone = settings.whatsapp_test_recipient
    if not test_phone:
        raise HTTPException(status_code=400, detail="No test recipient configured")

    process_whatsapp_inbound.delay(
        external_message_id=f"test-{text[:10]}",
        text=text,
        phone=test_phone,
        metadata={"test": True},
    )
    return {"status": "test_message_queued", "phone": test_phone}


@router.post("/calendar")
def inbound_calendar(payload: GenericInboundPayload) -> dict[str, str]:
    process_calendar_inbound.delay(payload.model_dump())
    return {"status": "accepted"}
