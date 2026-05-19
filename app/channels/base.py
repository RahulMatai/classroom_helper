# app/channels/base.py
# ════════════════════════════════════════════════
# Canonical Message Envelope
#
# WHY THIS FILE EXISTS:
# Telegram, WhatsApp and Web all send messages
# in completely different formats.
# This defines ONE standard format that
# all channel adapters convert to.
# Agents only ever see this standard format.
# ════════════════════════════════════════════════

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class MessageType(Enum):
    TEXT    = "text"
    FILE    = "file"
    VOICE   = "voice"
    IMAGE   = "image"
    COMMAND = "command"


@dataclass
class Attachment:
    file_id:   str
    file_type: str
    file_url:  Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    
@dataclass
class CanonicalMessage:
    """
    Standard message format for all channels.
    Every adapter converts to this.
    Agents only ever work with this.
    """
    message_id:   str
    channel:      str
    sender_id:    str
    text:         str
    message_type: MessageType       = MessageType.TEXT
    tenant_id:    Optional[str]     = None
    user_id:      Optional[str]     = None
    attachments:  List[Attachment]  = field(default_factory=list)
    timestamp:    datetime          = field(default_factory=datetime.utcnow)
    raw_payload:  Optional[dict]    = None

    def is_command(self) -> bool:
        return self.text.startswith("/")

    def get_command(self) -> Optional[str]:
        if self.is_command():
            return self.text.split()[0][1:].lower()
        return None

    def has_attachments(self) -> bool:
        return len(self.attachments) > 0

@dataclass
class OutboundMessage:
    """
    Standard outbound format.
    Agent creates this, adapter sends it.
    """
    recipient_id: str
    channel:      str
    text:         str
    parse_mode:   str            = "plain"
    reply_to:     Optional[str]  = None
    buttons:      Optional[list] = None