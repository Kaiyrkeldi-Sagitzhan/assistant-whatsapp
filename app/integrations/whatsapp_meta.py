import logging
import re

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_recipient_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("8"):
        return f"7{digits[1:]}"
    return digits


class WhatsAppMetaClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.whatsapp_access_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.graph_version = settings.whatsapp_graph_version
        self.url = (
            f"https://graph.facebook.com/{self.graph_version}/"
            f"{self.phone_number_id}/messages"
        )

    async def send_text(self, to: str, body: str) -> None:
        # Use international format for Kazakhstan
        recipient = f"7{to}" if not to.startswith('7') else to
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp message to %s: %s", recipient, body)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
