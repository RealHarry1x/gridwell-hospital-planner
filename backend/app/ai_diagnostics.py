"""Small, sanitized terminal diagnostics. Never log raw exceptions or payloads.

Use a child of uvicorn.error so INFO startup lines appear in the normal server
Terminal without enabling SDK/HTTP debug logging or attaching a second handler.
"""

from enum import Enum
import json
import logging
import os
import re
from urllib.parse import quote, quote_plus

LOGGER = logging.getLogger("uvicorn.error.gridwell_ai")
REDACTED = "[REDACTED]"
_SECRET_NAME = re.compile(r"api.?key|token|password|passwd|secret|credential|authorization|(?:^|_)key$", re.I)
_ASSIGNMENT = re.compile(
    r'''(?ix)(["']?\b(?:[a-z0-9_]*api[\s_-]?key|x-goog-api-key|authorization|proxy-authorization|'''
    r'''access[_-]?token|refresh[_-]?token|token|password|passwd|secret|client[_-]?secret|key)\b["']?\s*[=:]\s*)'''
    r'''(?:"[^"]*"|'[^']*'|[^\s,;{}\[\]&]+)'''
)


def redact(value, *known_secrets, limit=1200):
    """Redact BEFORE truncation or logging, including LogRecord arguments."""
    if not isinstance(value, (str, int, bool)):
        return "[details withheld]"
    text = str(value)
    secrets = {secret for secret in known_secrets if isinstance(secret, str) and secret}
    # Values are used only for redaction, never logged or returned. This also
    # covers credentials used by proxy/transport code, outside Gemini's key.
    secrets.update(value for name, value in os.environ.items() if value and _SECRET_NAME.search(name))
    variants = set()
    for secret in secrets:
        variants.update((secret, quote(secret, safe=""), quote_plus(secret), json.dumps(secret)[1:-1]))
    for secret in sorted(variants, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    # Do not retain URLs: they may carry signed queries or proxy credentials.
    text = re.sub(r"\b(?:https?|socks5h?|socks4)://[^\s<>\"']+", "[URL REDACTED]", text, flags=re.I)
    text = re.sub(r"\b(?:Bearer|Basic)\s+[a-z0-9+/_.=:%-]+", REDACTED, text, flags=re.I)
    text = _ASSIGNMENT.sub(lambda m: m.group(1) + REDACTED, text)
    text = re.sub(r"\bAIza[^\s'\"<>]*|\bsk-[a-z0-9_-]{12,}\b|\bAKIA[A-Z0-9]{16}\b", REDACTED, text, flags=re.I)
    text = re.sub(r"\beyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+\b", REDACTED, text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", "[EMAIL REDACTED]", text, flags=re.I)
    text = re.sub(r"\b\d{10,}\b", "[IDENTIFIER REDACTED]", text)
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def enum_name(value):
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        return None
    value = value.rsplit(".", 1)[-1]
    return value if re.fullmatch(r"[A-Za-z0-9_]{1,64}", value) else "unknown"


def http_status(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value if isinstance(value, int) and 100 <= value <= 599 else None


def error_details(exc):
    """Extract current SDK APIError fields, never repr(exc) / full details."""
    response = getattr(exc, "response", None)
    code = http_status(getattr(response, "status_code", None)) or http_status(getattr(exc, "code", None))
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        details = getattr(exc, "response_json", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    if not isinstance(error, dict):
        error = {}
    code = code or http_status(error.get("code"))
    status = enum_name(getattr(exc, "status", None)) or enum_name(error.get("status"))
    message = getattr(exc, "message", None)
    if not isinstance(message, str) or not message:
        message = error.get("message")
    if (not isinstance(message, str) or not message) and details is not None:
        message = "The provider supplied no error message; full response details are withheld."
    if not isinstance(message, str) or not message:
        args = getattr(exc, "args", ())
        message = args[0] if args and isinstance(args[0], str) else "SDK/transport failure; no safe message was provided."
    return {"http_status": code, "api_status": status, "error_type": type(exc).__name__, "message": message}


def emit(config, event, *, level=logging.INFO, **fields):
    # Only the selected scalar fields reach the LogRecord, already scrubbed.
    safe_model = config.model if re.fullmatch(r"gemini-[a-z0-9][a-z0-9._-]{0,95}", config.model) else "[invalid model]"
    values = {"event": event, "model": safe_model, **fields}
    safe = {}
    for name, value in values.items():
        if value is None:
            safe[name] = "not_reported"
        elif isinstance(value, bool) or (isinstance(value, int) and name in {"http_status", "candidate_count", "text_parts", "thoughts_tokens"}):
            safe[name] = value
        else:
            safe[name] = redact(value, config.api_key)
    LOGGER.log(level, "[Gridwell AI] %s", json.dumps(safe, ensure_ascii=True, sort_keys=True))


def configuration(config):
    from .ai_config import stable_text_model
    emit(config, "configuration", env_file=config.env_path or "project-root .env",
         env_file_status=config.env_file_status, key_source=config.key_source,
         key_present=bool(config.api_key), model_source=config.model_source,
         model_valid=stable_text_model(config.model))
    if config.key_source == "environment" and not config.api_key:
        emit(config, "configuration_hint", level=logging.WARNING,
             message="An empty server GEMINI_API_KEY overrides the .env value. Unset it or set it locally, then restart Python.")


class GeminiResponseError(Exception):
    """An HTTP-completed generation with no safe, complete text to display."""
    def __init__(self, message, *, finish_reason=None, block_reason=None, candidate_count=0, text_parts=0, thoughts_tokens=0, provider_message=None):
        super().__init__(message)
        self.diagnostic = {"message": message, "finish_reason": finish_reason,
                           "block_reason": block_reason, "candidate_count": candidate_count,
                           "text_parts": text_parts, "thoughts_tokens": thoughts_tokens,
                           "provider_message": provider_message}
