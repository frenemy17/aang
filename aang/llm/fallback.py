import time
import logging
from typing import List, Dict, Any, Optional, Callable
from .base import LLMProvider
from .types import Message, LLMResponse

logger = logging.getLogger("ion.llm.fallback")

class FallbackProvider(LLMProvider):
    """Wraps a primary provider with one or more backup providers.
    
    If the active provider experiences persistent rate limits (429), timeouts,
    or service errors, it automatically falls over to the next configured provider.
    """
    def __init__(self, providers: List[LLMProvider], on_failover: Optional[Callable[[str, str], None]] = None):
        if not providers:
            raise ValueError("At least one provider must be specified for FallbackProvider.")
        self.providers = providers
        self.current_index = 0
        self.on_failover = on_failover
        active = self.providers[0]
        super().__init__(active.model, active.api_key, active.base_url)

    @property
    def active_provider(self) -> LLMProvider:
        return self.providers[self.current_index]

    @property
    def model_name(self) -> str:
        return self.active_provider.model

    def switch_to_provider(self, index: int):
        if 0 <= index < len(self.providers):
            self.current_index = index
            active = self.active_provider
            self.model = active.model
            self.api_key = active.api_key
            self.base_url = active.base_url

    def generate(self, messages: List[Message], tools: List[Dict[str, Any]] = None) -> LLMResponse:
        attempts = 0
        max_attempts = len(self.providers)
        last_exception = None

        while attempts < max_attempts:
            provider = self.active_provider
            try:
                return provider.generate(messages, tools)
            except Exception as e:
                import re
                err_str = str(e)
                last_exception = e
                logger.warning(f"FallbackProvider: {type(provider).__name__} ({provider.model}) raised: {e}")
                
                is_exhausted = any(k in err_str.lower() for k in ["402", "insufficient credits", "never purchased credits"])
                # Check for failover triggers (Rate limit 429, Credit exhaustion 402, Overloaded 503/529, or Quotas)
                is_failover_worthy = is_exhausted or any(k in err_str.lower() for k in [
                    "429", "rate limit", "rate_limit", "overloaded", "503", "529", "capacity", "quota exceeded"
                ])

                if is_failover_worthy and len(self.providers) > 1:
                    prev_name = f"{type(provider).__name__} ({provider.model})"
                    if is_exhausted:
                        # Permanently remove exhausted provider to prevent future loops
                        self.providers.pop(self.current_index)
                        if self.current_index >= len(self.providers):
                            self.current_index = 0
                    else:
                        self.current_index = (self.current_index + 1) % len(self.providers)
                        
                    next_provider = self.active_provider
                    next_name = f"{type(next_provider).__name__} ({next_provider.model})"
                    
                    if self.on_failover:
                        self.on_failover(prev_name, next_name)
                    
                    # Update active properties
                    self.model = next_provider.model
                    self.api_key = next_provider.api_key
                    self.base_url = next_provider.base_url
                    attempts += 1
                    time.sleep(0.5)
                    continue

                # If no alternative providers exist, check for rate limit with cool-down instruction
                retry_match = re.search(r'try again in ([\d\.]+)s', err_str, re.IGNORECASE)
                if ("429" in err_str or "rate_limit" in err_str or "rate limit" in err_str) and retry_match:
                    try:
                        wait_sec = min(15.0, float(retry_match.group(1)) + 1.0)
                        logger.info(f"Rate limited on {provider.model}; cooling down for {wait_sec:.1f}s before retry...")
                        time.sleep(wait_sec)
                        attempts += 1
                        continue
                    except Exception:
                        pass

                # If no recovery was possible on this provider and no alternatives exist, raise
                raise e


        raise last_exception or Exception("All fallback LLM providers failed.")
