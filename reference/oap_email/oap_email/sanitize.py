"""Email content sanitization — HTML→text, prompt injection filtering."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from io import StringIO


class _HTMLStripper(HTMLParser):
    """Strip HTML tags, keeping text content."""

    def __init__(self):
        super().__init__()
        self._text = StringIO()
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "head"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._text.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head"):
            self._skip = False
        elif tag in ("p", "div", "li", "tr"):
            self._text.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._text.write(data)

    def get_text(self) -> str:
        return self._text.getvalue()


def html_to_text(html: str) -> str:
    """Convert HTML email body to plain text."""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
        text = stripper.get_text()
    except Exception:
        # Fallback: crude tag stripping
        text = re.sub(r"<[^>]+>", " ", html)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Prompt injection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    # Direct instruction injection
    re.compile(r"(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?)", re.I),
    # System prompt extraction
    re.compile(r"(?:reveal|show|output|repeat|print)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|rules?)", re.I),
    # Role manipulation
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|evil|unrestricted)", re.I),
    re.compile(r"(?:act|pretend|behave)\s+as\s+(?:if\s+)?(?:you\s+(?:are|were)\s+)?(?:a\s+)?(?:different|unrestricted)", re.I),
    # Delimiter attacks
    re.compile(r"```\s*system", re.I),
    re.compile(r"\[SYSTEM\]|\[INST\]|\[/INST\]", re.I),
    # Common payload markers
    re.compile(r"<\|(?:im_start|im_end|system|endoftext)\|>", re.I),
]


def filter_injection(text: str) -> str:
    """Remove likely prompt injection patterns from email text.

    Conservative: replaces matched spans with [filtered] rather than
    removing entire message. False positives are low-cost (a bracket
    in the output), false negatives are handled by the LLM's own
    instruction following.
    """
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[filtered]", text)
    return text


def sanitize_email_body(raw_text: str | None, raw_html: str | None) -> str:
    """Produce clean plain text from email body parts.

    Prefers plain text part. Falls back to HTML→text conversion.
    Applies prompt injection filtering to result.
    """
    if raw_text and raw_text.strip():
        body = raw_text.strip()
    elif raw_html and raw_html.strip():
        body = html_to_text(raw_html)
    else:
        return ""

    body = filter_injection(body)

    # Truncate excessively long bodies
    if len(body) > 10_000:
        body = body[:10_000] + "\n\n[truncated]"

    return body
