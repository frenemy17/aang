import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    provider: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    groq_api_keys: Optional[str] = None
    base_url: Optional[str] = None
    
    # limits
    max_iterations: int = 15
    command_timeout: int = 30
    
    model_config = SettingsConfigDict(
        env_prefix="ION_", 
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def groq_key_list(self) -> list[str]:
        keys = []
        raw_sources = [
            os.getenv("GROQ_API_KEYS"),
            self.groq_api_keys,
            os.getenv("GROQ_API_KEY"),
            self.groq_api_key,
        ]
        for src in raw_sources:
            if not src:
                continue
            for item in src.replace("\n", ",").replace(" ", ",").split(","):
                k = item.strip()
                if k and k not in keys:
                    keys.append(k)
        return keys

    @property
    def effective_api_key(self) -> Optional[str]:
        return (
            self.api_key or 
            self.openrouter_api_key or 
            os.getenv("AANG_API_KEY") or
            os.getenv("OPENROUTER_API_KEY") or 
            os.getenv("ION_API_KEY") or 
            self.groq_api_key or 
            os.getenv("GROQ_API_KEY")
        )

settings = Settings()
