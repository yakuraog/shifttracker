from typing import Optional


def validate_message(message) -> tuple[bool, Optional[str]]:
    """Returns (is_valid, rejection_reason).

    Accepts any object with .forward_from, .forward_from_chat, .photo, .document attributes.
    """
    if message.forward_from or message.forward_from_chat:
        return False, "forwarded_message"
    if not message.photo:
        if message.document:
            return False, "document_not_photo"
        return False, "no_photo"
    return True, None
