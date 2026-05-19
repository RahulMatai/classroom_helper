# app/core/llm.py
# ════════════════════════════════════════════════
# LLM Provider Abstraction
#
# WHY THIS FILE EXISTS:
# Every agent needs to call an LLM. Instead of
# each agent importing Groq directly, they all
# use this abstraction layer.

# HOW IT WORKS:
# LLMProvider is the base interface.
# GroqProvider implements it for Groq.
# get_llm() returns the right provider based
# on LLM_PROVIDER in .env

 #---------IMPORTANT----------------------
# Never import groq directly in agent files.
# Always use: from app.core.llm import get_llm
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from groq import Groq
from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

# ── Base Interface ────────────────────────────────
class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Every provider MUST implement complete().
    This guarantees all agents work the same way
    regardless of which provider is active.
    
    """
    @abstractmethod
    def complete(
        self,
        messages:List[Dict[str,str]],
        model: str,
        System:Optional[str] = None,
        temprature: float= 0.7,
        max_tokens: int = 1000,
        
    ) -> str:
        pass
    
# ── Groq Provider ─────────────────────────────────
class GroqProvider(LLMProvider):
    #groq implementation
    def __init__(self):
        """
        Initialise Groq client with API key.
        Called once when app starts.
        """
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        log.info("groq_provider_initialised")
        
    def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        try:
            # Build full message list
            # System prompt always goes first
            full_messages = []
            if system:
                full_messages.append({
                    "role": "system",
                    "content": system
                })
            full_messages.extend(messages)
            log.debug("groq_request",
                      model=model,
                      message_count=len(full_messages),
                      temperature=temperature)
            response = self.client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Extract response text
            result = response.choices[0].message.content

            log.debug("groq_response",
                      model=model,
                      response_length=len(result),
                      tokens_used=response.usage.total_tokens)

            return result

        except Exception as e:
            log.error("groq_request_failed",
                      model=model,
                      error=str(e),
                      exc_info=True)
            raise
        
# ── Agent-Specific Helpers ────────────────────────
# Pre-configured LLM callers for each agent.
# Each agent gets the right model automatically.
# Agents never need to specify model themselves.

class AgentLLM:
    """
    Convenience wrapper that gives each agent
    its own pre-configured LLM caller.

    Usage in any agent:
        from app.core.llm import AgentLLM
        llm = AgentLLM()

        # Teacher agent
        response = llm.teacher(messages, system)

        # Router agent
        intent = llm.router(messages, system)
    """

    def __init__(self):
        self.provider = GroqProvider()

    def _call(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        return self.provider.complete(
            messages=messages,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def router(self, messages, system=None) -> str:
        """Fast classification — uses small model."""
        return self._call(
            settings.MODEL_ROUTER,
            messages, system,
            temperature=0.1,  # low temp = consistent classification
            max_tokens=100    # intent labels are short
        )

    def safety(self, messages, system=None) -> str:
        """Fast filtering — uses small model."""
        return self._call(
            settings.MODEL_SAFETY,
            messages, system,
            temperature=0.1,
            max_tokens=200
        )

    def teacher(self, messages, system=None) -> str:
        """Complex reasoning — uses large model."""
        return self._call(
            settings.MODEL_TEACHER,
            messages, system,
            temperature=0.7,
            max_tokens=1000
        )

    def student(self, messages, system=None) -> str:
        """Understanding submissions — uses large model."""
        return self._call(
            settings.MODEL_STUDENT,
            messages, system,
            temperature=0.7,
            max_tokens=1000
        )

    def summariser(self, messages, system=None) -> str:
        """Long context summaries — uses mixtral."""
        return self._call(
            settings.MODEL_SUMMARISER,
            messages, system,
            temperature=0.5,
            max_tokens=2000
        )

    def reminder(self, messages, system=None) -> str:
        """Simple nudge generation — uses light model."""
        return self._call(
            settings.MODEL_REMINDER,
            messages, system,
            temperature=0.8,  # slightly creative for variety
            max_tokens=300
        )

    def parent(self, messages, system=None) -> str:
        """Weekly digest generation — uses mixtral."""
        return self._call(
            settings.MODEL_PARENT,
            messages, system,
            temperature=0.6,
            max_tokens=1500
        )


# ── Factory Function ──────────────────────────────
def get_llm() -> AgentLLM:
    """
    Returns configured LLM instance.

    Usage in any agent file:
        from app.core.llm import get_llm
        llm = get_llm()
        response = llm.teacher(messages, system_prompt)

    Future provider swap:
        Change LLM_PROVIDER in .env
        Add new provider class above
        Add condition here
        Zero changes needed in agent files
    """
    log.debug("llm_provider_loaded",
              provider=settings.LLM_PROVIDER)
    return AgentLLM()