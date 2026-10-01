import os
import time
import logging
import re
from typing import List, Union, Optional, Dict, Any
from .openai import OpenAICompatibleProvider
from .types import Message, LLMResponse
from ion.config.settings import settings

logger = logging.getLogger("ion.llm.groq")

class GroqProvider(OpenAICompatibleProvider):
    """Groq Provider with automatic multi-key rotation and rate-limit mitigation.
    
    Distributes requests round-robin across a pool of API keys to multiply effective TPM quota,
    and immediately rotates to the next available key when a 429 rate limit is encountered.
    """
    def __init__(self, model: str, api_key: Union[str, List[str]] = None, base_url: str = None):
        self.base_url = base_url or "https://api.groq.com/openai/v1"
        self.model = model
        
        # Collect and deduplicate all available Groq keys
        self.api_keys: List[str] = self._resolve_keys(api_key)
        if not self.api_keys:
            raise ValueError("No Groq API key found. Set GROQ_API_KEY or GROQ_API_KEYS.")
            
        self.current_idx = 0
        self.key_cooldowns: Dict[str, float] = {}  # key -> expiry timestamp
        
        super().__init__(model, self.api_keys[0], self.base_url)
        logger.info(f"GroqProvider initialized for model '{model}' with {len(self.api_keys)} key(s) in rotation pool.")

    def _resolve_keys(self, input_key: Union[str, List[str], None]) -> List[str]:
        keys = []
        
        def add_key(k: str):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)

        # 1. From passed parameter
        if isinstance(input_key, list):
            for k in input_key:
                if isinstance(k, str):
                    for sub_k in k.replace("\n", ",").replace(" ", ",").split(","):
                        add_key(sub_k)
        elif isinstance(input_key, str) and input_key.strip():
            for sub_k in input_key.replace("\n", ",").replace(" ", ",").split(","):
                add_key(sub_k)

        # 2. From Settings / environment
        for k in settings.groq_key_list:
            add_key(k)

        # 3. Direct env checks as fallback
        for env_var in ["GROQ_API_KEYS", "GROQ_API_KEY"]:
            val = os.getenv(env_var, "")
            if val:
                for sub_k in val.replace("\n", ",").replace(" ", ",").split(","):
                    add_key(sub_k)
                    
        return keys

    @property
    def key_count(self) -> int:
        return len(self.api_keys)

    def _mask_key(self, key: str) -> str:
        if len(key) <= 12:
            return key
        return f"{key[:7]}...{key[-6:]}"

    def _get_next_key(self) -> str:
        now = time.time()
        n = len(self.api_keys)
        
        # 1. Look for next available key not in cooldown (round-robin)
        for i in range(n):
            idx = (self.current_idx + i) % n
            key = self.api_keys[idx]
            cooldown_until = self.key_cooldowns.get(key, 0.0)
            if now >= cooldown_until:
                self.current_idx = (idx + 1) % n
                return key
                
        # 2. If all keys are in cooldown, find the one that will be ready earliest
        earliest_key = min(self.api_keys, key=lambda k: self.key_cooldowns.get(k, 0.0))
        wait_needed = max(0.5, self.key_cooldowns[earliest_key] - now)
        logger.warning(
            f"All {n} Groq keys are currently rate-limited. "
            f"Waiting {wait_needed:.1f}s for key {self._mask_key(earliest_key)} to cool down..."
        )
        time.sleep(wait_needed)
        return earliest_key

    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        attempts = 0
        max_attempts = max(len(self.api_keys) * 2, 6)
        last_error = None
        
        while attempts < max_attempts:
            key = self._get_next_key()
            self.api_key = key
            masked = self._mask_key(key)
            
            try:
                return super().generate(messages, tools)
            except Exception as e:
                err_str = str(e)
                last_error = e
                
                # Check for rate limit (429 or rate limit message)
                if "429" in err_str or "rate limit" in err_str.lower() or "tpm" in err_str.lower():
                    # Parse requested cooldown from Groq response, e.g. "try again in 15.72s"
                    m = re.search(r'try again in ([\d\.]+)s', err_str, re.IGNORECASE)
                    wait_sec = float(m.group(1)) + 0.5 if m else 15.0
                    self.key_cooldowns[key] = time.time() + wait_sec
                    
                    next_idx = self.current_idx % len(self.api_keys)
                    next_key_masked = self._mask_key(self.api_keys[next_idx])
                    logger.warning(
                        f"GroqProvider: Key {masked} rate limited (429, cool-down {wait_sec:.1f}s). "
                        f"Rotating to next key in pool: {next_key_masked} (pool size: {len(self.api_keys)})"
                    )
                    attempts += 1
                    continue
                else:
                    # Fatal or client error, re-raise immediately
                    raise e
                    
        raise last_error or Exception(f"All {len(self.api_keys)} Groq API keys failed.")
