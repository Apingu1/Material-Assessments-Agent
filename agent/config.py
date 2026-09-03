from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    template_path: Path
    output_dir: Path
    database_path: Path
    default_assessment_performed_by: str
    capture_evidence: bool
    playwright_timeout_ms: int
    generate_pdf: bool

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(REPO_ROOT / ".env")
        settings = cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip(),
            template_path=_resolve_path(
                os.getenv(
                    "TEMPLATE_PATH",
                    "ES.SOP.272.F01.V02 - Material Hazard & Cleanability Screening Assessment.docx",
                )
            ),
            output_dir=_resolve_path(os.getenv("OUTPUT_DIR", "outputs")),
            database_path=_resolve_path(os.getenv("DATABASE_PATH", "data/agent.db")),
            default_assessment_performed_by=os.getenv(
                "DEFAULT_ASSESSMENT_PERFORMED_BY", ""
            ).strip(),
            capture_evidence=_as_bool(os.getenv("CAPTURE_EVIDENCE"), True),
            playwright_timeout_ms=int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000")),
            generate_pdf=_as_bool(os.getenv("GENERATE_PDF"), True),
        )
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        return settings

    def require_runtime(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Copy .env.example to .env and add the key."
            )
        if not self.template_path.exists():
            raise FileNotFoundError(f"Assessment template not found: {self.template_path}")
