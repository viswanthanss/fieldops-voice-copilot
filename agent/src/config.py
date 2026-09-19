"""
Configuration management for FieldOps Voice Copilot Agent.
Reads environment variables with validation via Pydantic Settings.
"""
from __future__ import annotations

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LiveKit Realtime Transport
    livekit_url: str = Field(default="", alias="LIVEKIT_URL")
    livekit_api_key: str = Field(default="", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(default="", alias="LIVEKIT_API_SECRET")

    # Speech-to-Text (STT)
    stt_provider: str = Field(default="deepgram", alias="STT_PROVIDER")
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Large Language Model (LLM)
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    max_response_tokens: int = Field(default=400, alias="MAX_RESPONSE_TOKENS")

    # Text-to-Speech (TTS)
    tts_provider: str = Field(default="openai", alias="TTS_PROVIDER")
    tts_voice: str = Field(default="nova", alias="TTS_VOICE")
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")

    # Embedded Moss Retrieval Runtime
    moss_project_id: str = Field(default="", alias="MOSS_PROJECT_ID")
    moss_project_key: str = Field(default="", alias="MOSS_PROJECT_KEY")
    moss_index_name: str = Field(default="fieldops-knowledge-v1", alias="MOSS_INDEX_NAME")
    moss_index_version: str = Field(default="1.0.0", alias="MOSS_INDEX_VERSION")
    moss_top_k: int = Field(default=5, alias="MOSS_TOP_K")
    moss_min_relevance_score: float = Field(default=0.65, alias="MOSS_MIN_RELEVANCE_SCORE")

    # Session State (InMemory for local development, Redis for distributed production)
    redis_url: str = Field(default="", alias="REDIS_URL")

    # Control Plane & Security
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    jwt_secret_key: str = Field(default="dev-secret-key-change-in-production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="ALGORITHM")

    # Evidence Gate & Grounding
    evidence_min_score: float = Field(default=0.65, alias="EVIDENCE_MIN_SCORE")
    evidence_min_chunks: int = Field(default=1, alias="EVIDENCE_MIN_CHUNKS")
    grounding_max_retries: int = Field(default=1, alias="GROUNDING_MAX_RETRIES")
    prompt_version: str = Field(default="v1.2.0", alias="PROMPT_VERSION")

    # OpenTelemetry Tracing
    otel_endpoint: str = Field(default="", alias="OTEL_ENDPOINT")
    otel_service_name: str = Field(default="fieldops-agent", alias="OTEL_SERVICE_NAME")


# Global singleton instance
config = AgentConfig()
