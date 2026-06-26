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
        if digits.startswith("7777"):
            digits = "78777" + digits[4:]
        elif digits.startswith("777"):
            digits = "7877" + digits[3:]
        elif digits.startswith("77"):
            digits = "787" + digits[2:]

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
        logger.info("Sending WhatsApp message to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.debug("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.debug("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp send failed for %s: %s", recipient, response.text)
            response.raise_for_status()

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str,
        components: list[dict],
    ) -> None:
        """Send a WhatsApp template message.

        Args:
            to: Recipient phone number
            template_name: Name of the template registered in Meta
            language_code: Language code (e.g., 'ru', 'en')
            components: List of component dictionaries with 'type' and 'parameters'
        """
        recipient = _normalize_recipient_phone(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code,
                },
                "components": components,
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp template message to %s: %s", recipient, template_name)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()

    async def send_welcome_template(self, to: str, language_code: str = "ru") -> None:
        """Send the welcome template message to a new user.

        Args:
            to: Recipient phone number
            language_code: Language code (default: 'ru')
        """
        recipient = _normalize_recipient_phone(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": "task_bot_welcome_static",
                "language": {
                    "code": language_code,
                },
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp welcome template to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp welcome template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
        logger.info("task_bot_welcome_static sended")

    async def send_agenda_select_template(self, to: str, language_code: str = "ru") -> None:
        """Send the agenda selection template with quick reply buttons.

        Args:
            to: Recipient phone number
            language_code: Language code (default: 'ru')
        """
        recipient = _normalize_recipient_phone(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": "task_bot_agenda_select",
                "language": {
                    "code": language_code,
                },
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp agenda select template to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp agenda select template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
        logger.info("task_bot_agenda_select sended")

    async def send_tasks_day_template(self, to: str, tasks_list: str, language_code: str = "ru") -> None:
        """Send the daily tasks template with formatted task list.

        Args:
            to: Recipient phone number
            tasks_list: Formatted string of tasks to include in template
            language_code: Language code (default: 'ru')
        """
        recipient = _normalize_recipient_phone(to)
        # Replace newlines with separator for WhatsApp template (no newlines allowed)
        tasks_list_clean = tasks_list.replace("\n", " | ")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": "task_bot_tasks_day",
                "language": {
                    "code": language_code,
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": tasks_list_clean,
                            }
                        ],
                    }
                ],
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp tasks day template to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp tasks day template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
        logger.info("task_bot_tasks_day sended")

    async def send_tasks_week_template(self, to: str, tasks_list: str, language_code: str = "ru") -> None:
        """Send the weekly tasks template with formatted task list.

        Args:
            to: Recipient phone number
            tasks_list: Formatted string of tasks to include in template
            language_code: Language code (default: 'ru')
        """
        recipient = _normalize_recipient_phone(to)
        # Replace newlines with separator for WhatsApp template (no newlines allowed)
        tasks_list_clean = tasks_list.replace("\n", " | ")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": "task_bot_tasks_week",
                "language": {
                    "code": language_code,
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": tasks_list_clean,
                            }
                        ],
                    }
                ],
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp tasks week template to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp tasks week template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
        logger.info("task_bot_tasks_week sended")

    async def send_task_created_template(
        self,
        to: str,
        task_title: str,
        due_date: str,
        language_code: str = "ru",
    ) -> None:
        """Send the task created confirmation template.

        Args:
            to: Recipient phone number
            task_title: The title of the created task
            due_date: The due date string (e.g., "11.11")
            language_code: Language code (default: 'ru')
        """
        recipient = _normalize_recipient_phone(to)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": "task_bot_task_created",
                "language": {
                    "code": language_code,
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": task_title,
                            },
                            {
                                "type": "text",
                                "text": due_date,
                            },
                        ],
                    }
                ],
            },
        }
        headers = {"Authorization": f"Bearer {self.access_token}"}
        logger.info("Sending WhatsApp task created template to %s", recipient)
        logger.info("Using phone_number_id: %s", self.phone_number_id)
        logger.info("WhatsApp API request payload: %s", payload)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.url, headers=headers, json=payload)
            logger.info("WhatsApp API response status: %s", response.status_code)
            logger.info("WhatsApp API response: %s", response.text)
            if response.status_code >= 400:
                logger.error("WhatsApp task created template send failed for %s: %s", recipient, response.text)
            response.raise_for_status()
        logger.info("task_bot_task_created sended")
