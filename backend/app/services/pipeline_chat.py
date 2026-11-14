import re
from typing import List, Dict, Any

# Regex patterns for WhatsApp chat export formats
WHATSAPP_PATTERNS = [
    # Format: [14/11/26, 10:15:30] Sender: Message or [14/11/2026, 10:15:30 AM] Sender: Message
    re.compile(r"^\[(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}[,\s]+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]\s+([^:]+?):\s*(.*)$"),
    # Format: 14/11/2026, 10:15 - Sender: Message or 11/14/26, 10:15 AM - Sender: Message
    re.compile(r"^(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}[,\s]+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\s*[-:]\s*([^:]+?):\s*(.*)$"),
]

# Regex for email headers
EMAIL_HEADER_PATTERN = re.compile(r"^(From|To|Date|Subject|Cc|Bcc):\s*(.*)$", re.IGNORECASE)


def parse_chat_or_email(text_content: str) -> List[Dict[str, Any]]:
    """
    Parses chat exports (WhatsApp txt) and plain email texts into discrete messages
    with sender, timestamp, and line position.
    """
    lines = text_content.splitlines()
    messages: List[Dict[str, Any]] = []

    # Check if content looks like WhatsApp chat export
    is_whatsapp = False
    for line in lines[:15]:
        line = line.strip()
        if not line:
            continue
        for pattern in WHATSAPP_PATTERNS:
            if pattern.match(line):
                is_whatsapp = True
                break
        if is_whatsapp:
            break

    if is_whatsapp:
        current_msg = None
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            matched = False
            for pattern in WHATSAPP_PATTERNS:
                m = pattern.match(line)
                if m:
                    matched = True
                    timestamp_str, sender, msg_text = m.groups()
                    current_msg = {
                        "timestamp_str": timestamp_str.strip(),
                        "sender": sender.strip(),
                        "text": msg_text.strip(),
                        "engine": "chat_parser",
                        "confidence": 100.0,
                    }
                    messages.append(current_msg)
                    break

            if not matched:
                # Continuation of multi-line message
                if current_msg:
                    current_msg["text"] += f"\n{line}"
                else:
                    # System preamble or unrecognized line
                    messages.append({
                        "timestamp_str": None,
                        "sender": "System",
                        "text": line,
                        "engine": "chat_parser",
                        "confidence": 100.0,
                    })

    # Check if content looks like email
    elif any(EMAIL_HEADER_PATTERN.match(l.strip()) for l in lines[:10]):
        email_sender = None
        email_date = None
        in_body = False
        body_lines = []

        for line in lines:
            line_str = line.strip()
            if not in_body:
                header_match = EMAIL_HEADER_PATTERN.match(line_str)
                if header_match:
                    hdr_name, hdr_val = header_match.groups()
                    if hdr_name.lower() == "from":
                        email_sender = hdr_val.strip()
                    elif hdr_name.lower() == "date":
                        email_date = hdr_val.strip()
                    messages.append({
                        "timestamp_str": email_date,
                        "sender": f"Header:{hdr_name}",
                        "text": f"{hdr_name}: {hdr_val.strip()}",
                        "engine": "chat_parser",
                        "confidence": 100.0,
                    })
                elif not line_str:
                    in_body = True
            else:
                if line_str:
                    messages.append({
                        "timestamp_str": email_date,
                        "sender": email_sender or "Sender",
                        "text": line_str,
                        "engine": "chat_parser",
                        "confidence": 100.0,
                    })
    else:
        # Standard plain text lines
        for idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if line_str:
                messages.append({
                    "timestamp_str": None,
                    "sender": None,
                    "text": line_str,
                    "engine": "chat_parser",
                    "confidence": 100.0,
                })

    # Number items sequentially
    for idx, item in enumerate(messages, start=1):
        item["line_number"] = idx
        item["page_or_segment"] = "p1"

    return messages
