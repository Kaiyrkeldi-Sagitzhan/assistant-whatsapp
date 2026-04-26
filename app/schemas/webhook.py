from typing import Union

from pydantic import BaseModel


class GenericInboundPayload(BaseModel):
    external_message_id: str
    user_external_id: str
    text: str
    metadata: Union[dict, None] = None
