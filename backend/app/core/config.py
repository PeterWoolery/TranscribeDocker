from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    app_name: str = Field(default="TranscribeDocker", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")

    database_url: str = Field(alias="DATABASE_URL")
    celery_broker_url: str = Field(alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(alias="CELERY_RESULT_BACKEND")

    artifact_root: str = Field(default="/data/artifacts", alias="ARTIFACT_ROOT")
    upload_tmp_root: str = Field(default="/data/uploads_tmp", alias="UPLOAD_TMP_ROOT")

    max_upload_bytes: int = Field(default=2_147_483_648, alias="MAX_UPLOAD_BYTES")
    job_retention_days: int = Field(default=30, alias="JOB_RETENTION_DAYS")
    base_url: str = Field(default="http://localhost:8080", alias="BASE_URL")

    default_engine_mode: str = Field(default="auto_fallback", alias="DEFAULT_ENGINE_MODE")
    default_compute_device: str = Field(default="cpu", alias="DEFAULT_COMPUTE_DEVICE")
    whisper_cpp_model_dir: str = Field(default="/data/whisper_models", alias="WHISPER_CPP_MODEL_DIR")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_transcribe_model: str = Field(default="gpt-4o-transcribe", alias="OPENAI_TRANSCRIBE_MODEL")
    openai_translate_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_TRANSLATE_MODEL")
    hf_token: str | None = Field(default=None, alias="HF_TOKEN")


settings = Settings()
