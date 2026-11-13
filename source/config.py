import os
from pathlib import Path
from typing import List, Optional

try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class AppSettings(BaseSettings):
        APP_NAME: str = "ReconcileAI"
        VERSION: str = "2.0.0"
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DEFAULT_VISION_MODEL: str = "gemini-3.1-flash-lite"
        SUPPORTED_MODELS: List[str] = ["gemini-3.1-flash-lite", "gemini-3.8-flash"]
        GEMINI_TIMEOUT_MS: int = Field(default=60_000, gt=0)
        MAX_UPLOAD_SIZE_MB: int = 25
        CONFIDENCE_THRESHOLD: float = Field(default=0.85, ge=0, le=1)
        BATCH_WORKERS: int = Field(default=2, ge=1, le=8)
        MAX_BATCH_DOCUMENTS: int = Field(default=50, ge=1, le=100)
        VLM_API_KEY: Optional[str] = None
        VLM_INPUT_USD_PER_M_TOKEN: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
        VLM_OUTPUT_USD_PER_M_TOKEN: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
        OPENROUTER_API_KEY: Optional[str] = None
        VLM_MODEL: str = "qwen/qwen3.8-27b"
        VLM_BASE_URL: str = "https://api.groq.com/openai/v1"
        GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
        GEMINI_JUDGE_ENABLED: bool = False
        GEMINI_JUDGE_MODEL: str = "gemini-3.1-flash-lite"
        GEMINI_FREE_TIER: bool = True
        GEMINI_MIN_INTERVAL_SECONDS: float = Field(default=15.0, ge=0)
        GEMINI_MAX_RETRIES: int = Field(default=5, ge=0, le=8)
        GEMINI_API_KEY: Optional[str] = None
        DATA_DIR: Path = Path("data")
        DATABASE_PATH: Path = Path("data/reconcile_ai.db")
        MAX_PAGES: int = 10
        MAX_ESTIMATED_COST_USD: float = 20.0
        GEMINI_INPUT_USD_PER_M_TOKEN: float = 0.25
        GEMINI_OUTPUT_USD_PER_M_TOKEN: float = 1.50
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    settings = AppSettings()
except ImportError:

    class StandaloneSettings:
        APP_NAME: str = "ReconcileAI"
        VERSION: str = "2.0.0"
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DEFAULT_VISION_MODEL: str = "gemini-3.1-flash-lite"
        SUPPORTED_MODELS: List[str] = ["gemini-3.1-flash-lite", "gemini-3.8-flash"]
        GEMINI_TIMEOUT_MS: int = int(os.getenv("GEMINI_TIMEOUT_MS", "60000"))
        MAX_UPLOAD_SIZE_MB: int = 25
        CONFIDENCE_THRESHOLD: float = 0.85
        BATCH_WORKERS: int = int(os.getenv("BATCH_WORKERS", "2"))
        MAX_BATCH_DOCUMENTS: int = int(os.getenv("MAX_BATCH_DOCUMENTS", "50"))
        VLM_API_KEY: Optional[str] = os.getenv("VLM_API_KEY")
        VLM_INPUT_USD_PER_M_TOKEN = (
            float(os.environ["VLM_INPUT_USD_PER_M_TOKEN"])
            if "VLM_INPUT_USD_PER_M_TOKEN" in os.environ
            else None
        )
        VLM_OUTPUT_USD_PER_M_TOKEN = (
            float(os.environ["VLM_OUTPUT_USD_PER_M_TOKEN"])
            if "VLM_OUTPUT_USD_PER_M_TOKEN" in os.environ
            else None
        )
        OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        VLM_MODEL: str = os.getenv("VLM_MODEL", "qwen/qwen3.8-27b")
        VLM_BASE_URL: str = os.getenv("VLM_BASE_URL", "https://api.groq.com/openai/v1")
        GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
        GEMINI_JUDGE_ENABLED: bool = False
        GEMINI_JUDGE_MODEL: str = "gemini-3.1-flash-lite"
        GEMINI_FREE_TIER: bool = True
        GEMINI_MIN_INTERVAL_SECONDS: float = 15.0
        GEMINI_MAX_RETRIES: int = 5
        GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
        DATA_DIR: Path = Path(os.getenv("DATA_DIR", "data"))
        DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", "data/reconcile_ai.db"))
        MAX_PAGES: int = 10
        MAX_ESTIMATED_COST_USD: float = 20.0
        GEMINI_INPUT_USD_PER_M_TOKEN: float = 0.25
        GEMINI_OUTPUT_USD_PER_M_TOKEN: float = 1.50

    settings = StandaloneSettings()
