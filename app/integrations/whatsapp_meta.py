import logging
import re

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_recipient_phone(phone: str) -> str:
    """Normalize phone number to international format.
    
    Handles various formats:
    - 77769707106 -> 787769707106 (Kazakh format to test recipient)
    - 877769707106 -> 787769707106 (8-prefix to 7-prefix)
    - +777769707106 -> 787769707106 (with plus)
    """
    digits = re.sub(r"\D", "", phone)
    
    # Convert 8-prefix to 7-prefix (Russian/Kazakh format)
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    
    # Convert Kazakh mobile format to test recipient format
    # 777xxxxxxx -> 7877xxxxxxx (add 8 after 777)
    if len(digits) >= 10:
        if digits.startswith('7777'):
            digits = '78777' + digits[4:]
        elif digits.startswith('777'):
            digits = '7877' + digits[3:]
        elif digits.startswith('77'):
            digits = '787' + digits[2:]
    
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
        # Normalize phone number to international format
        recipient = _normalize_recipient_phone(to)
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
