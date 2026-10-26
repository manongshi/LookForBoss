import os
import sys
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
FROZEN = bool(getattr(sys, "frozen", False))
if os.environ.get("FINDBOSS_DATA_DIR"):
    DATA_DIR = Path(os.environ["FINDBOSS_DATA_DIR"]).expanduser().resolve()
elif FROZEN:
    DATA_DIR = Path.home() / "Library" / "Application Support" / "FindBoss"
else:
    DATA_DIR = BACKEND_DIR.parent / "runtime"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(DATA_DIR if FROZEN else BACKEND_DIR) / ".env",
        env_file_encoding="utf-8", extra="ignore",
    )
    database_file: str = "findboss.sqlite3"
    minimax_api_key: SecretStr = SecretStr("")
    minimax_model: str = "MiniMax-M3"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-flash"
    interview_provider: str = "minimax"
    minimax_speech_api_key: SecretStr = SecretStr("")
    minimax_speech_voice_id: str = ""
    minimax_speech_model: str = "speech-2.8-hd"
    interview_runtime_dir: str = ""
    interview_python: str = ""
    browser_channel: str = "chrome"
    browser_executable: str = ""
    browser_profile: str = ""
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:8000", "http://127.0.0.1:8000",
        ]
    )

    @property
    def database_path(self) -> Path:
        path = Path(self.database_file).expanduser()
        return (DATA_DIR / path).resolve() if not path.is_absolute() else path

    @property
    def database_name(self) -> str:
        return self.database_path.name

    @property
    def static_path(self) -> Path:
        return BACKEND_DIR / "static"

    @property
    def bundled_browser_path(self) -> Path | None:
        if not FROZEN:
            return None
        return (
            Path(sys.executable).resolve().parents[1] / "Resources" / "browser"
            / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing"
        )

    @property
    def profile_path(self) -> Path:
        if not self.browser_profile:
            return DATA_DIR / "browser-profile"
        path = Path(self.browser_profile).expanduser()
        return (BACKEND_DIR / path).resolve() if not path.is_absolute() else path

settings = Settings()
