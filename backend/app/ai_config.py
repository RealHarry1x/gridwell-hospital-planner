"""Private server configuration. This object must never be serialized to JSON."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gemini-3.8-flash"  # Stable in Google's official model list, checked 2026-10-31.


def stable_text_model(model: str) -> bool:
    """Use a fixed Gemini text model ID, never a URL or a rolling/preview alias."""
    return bool(re.fullmatch(r"gemini-[a-z0-9][a-z0-9._-]{0,95}", model)) and not any(
        part in model.split("-")
        for part in ("preview", "exp", "experimental", "latest", "live", "tts", "image", "embedding")
    )


@dataclass(frozen=True)
class AssistantConfig:
    api_key: str = field(default="", repr=False)
    model: str = DEFAULT_MODEL
    key_source: str = "provided"
    model_source: str = "provided"
    env_path: str = field(default="", repr=False)
    env_file_status: str = "not_checked"

    @classmethod
    def from_environment(cls, env_file: Path | None = None):
        # Explicit root path: also works when uvicorn's cwd is backend/. Only
        # these two settings are read. No parent-file search, interpolation,
        # environment mutation, or printing of the parsed file.
        path = env_file or PROJECT_ROOT / ".env"
        try:
            exists = path.is_file()
            values = dotenv_values(path, interpolate=False)
            file_status = "present" if exists else "missing"
        except (OSError, UnicodeError):
            values = {}
            file_status = "unreadable"
        key = os.environ.get("GEMINI_API_KEY", values.get("GEMINI_API_KEY") or "").strip()
        model = os.environ.get("GEMINI_MODEL", values.get("GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        key_source = "environment" if "GEMINI_API_KEY" in os.environ else ".env" if "GEMINI_API_KEY" in values else "missing"
        model_source = "environment" if "GEMINI_MODEL" in os.environ else ".env" if values.get("GEMINI_MODEL") else "default"
        return cls(api_key=key, model=model, key_source=key_source,
                   model_source=model_source, env_path=str(path.resolve()), env_file_status=file_status)

    def public_status(self):
        configured = bool(self.api_key) and stable_text_model(self.model)
        return {
            "configured": configured,
            "status": "gemini_configured_unverified" if configured else "sample",
            "notice": "Gemini is configured; the mode on each reply confirms whether it succeeded."
                      if configured else "Local sample mode is available without a Gemini key.",
        }
