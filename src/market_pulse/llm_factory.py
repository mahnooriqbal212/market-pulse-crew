"""Build the CrewAI LLM for each agent role, with retry on rate-limit errors.

Usage (from another module):
    from market_pulse.config import load_config
    from market_pulse.llm_factory import get_llm

    config = load_config()
    researcher_llm = get_llm("researcher", config)

Why our own retry?
    CrewAI 1.x already retries rate-limit errors, but only 3 times with very
    short waits (about 1s and 2s). Free tiers (Groq, OpenRouter, ...) usually
    need 10-60 seconds before the per-minute limit resets. So we wrap every
    LLM call with our own retry that uses LLM_MAX_RETRIES and
    LLM_RETRY_BASE_DELAY from .env (the wait doubles each time: 10, 20, 40...).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any, TypeVar

from crewai import LLM
from crewai.llms.base_llm import BaseLLM

from market_pulse.config import AppConfig, ConfigError, LLMSettings, load_config

logger = logging.getLogger(__name__)

T = TypeVar("T")

# CrewAI has its own short retry. While OUR retry is running we switch CrewAI's
# off, so the two don't stack up and waste free-tier requests. This flag is
# internal to CrewAI, so if a future version removes it we simply skip this
# (both retries then run, which still works, it just sends a few extra requests).
try:
    from crewai.llms.retry import _active_llm_rate_limit_retry as _crewai_retry_flag
except ImportError:  # pragma: no cover - depends on the installed CrewAI version
    _crewai_retry_flag = None

# Words that providers use in rate-limit error messages / class names.
_RATE_LIMIT_MARKERS: tuple[str, ...] = (
    "rate limit",
    "rate_limit",
    "ratelimit",  # e.g. the class name "RateLimitError"
    "too many requests",
    "resource exhausted",  # Google / Gemini
    "resource_exhausted",
)


# ---------------------------------------------------------------------------
# Detecting rate-limit errors
# ---------------------------------------------------------------------------


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield the error and every error it was raised from (wrapped errors)."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_rate_limit_error(error: BaseException) -> bool:
    """Return True if the error means 'too many requests, slow down'.

    Checks the HTTP status code (429) and the error's name and message,
    including any error it was wrapped around.
    """
    for err in _error_chain(error):
        if getattr(err, "status_code", None) == 429:
            return True
        if getattr(getattr(err, "response", None), "status_code", None) == 429:
            return True
        text = f"{type(err).__name__} {err}".lower()
        if any(marker in text for marker in _RATE_LIMIT_MARKERS):
            return True
    return False


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------


def retry_delay(attempt: int, base_delay: float) -> float:
    """Seconds to wait before retry number `attempt` (1, 2, 3...).

    The wait doubles each time: base, base*2, base*4, ...
    """
    return base_delay * (2 ** (attempt - 1))


def _log_retry(label: str, error: BaseException, attempt: int, max_retries: int, delay: float) -> None:
    # Only the error TYPE is logged, never the full message: some providers
    # echo part of the API key in their error text.
    logger.warning(
        "%s: rate limit hit (%s). Waiting %.0fs, then retry %d of %d...",
        label,
        type(error).__name__,
        delay,
        attempt,
        max_retries,
    )


def _crewai_retry_off() -> contextvars.Token[bool] | None:
    return _crewai_retry_flag.set(True) if _crewai_retry_flag is not None else None


def _crewai_retry_restore(token: contextvars.Token[bool] | None) -> None:
    if token is not None and _crewai_retry_flag is not None:
        _crewai_retry_flag.reset(token)


def call_with_retry(
    operation: Callable[[], T],
    *,
    max_retries: int,
    base_delay: float,
    label: str = "LLM",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `operation()`. If it fails with a rate-limit error, wait and try again.

    Any other error (wrong API key, bad model name, ...) is raised immediately,
    because retrying would not help. `sleep` can be replaced in tests so they
    don't really wait.
    """
    attempt = 0
    while True:
        token = _crewai_retry_off()
        try:
            return operation()
        except Exception as error:
            if attempt >= max_retries or not is_rate_limit_error(error):
                raise
            attempt += 1
            delay = retry_delay(attempt, base_delay)
            _log_retry(label, error, attempt, max_retries, delay)
        finally:
            _crewai_retry_restore(token)
        sleep(delay)


async def acall_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    base_delay: float,
    label: str = "LLM",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Async version of `call_with_retry` (CrewAI uses it for async runs)."""
    attempt = 0
    while True:
        token = _crewai_retry_off()
        try:
            return await operation()
        except Exception as error:
            if attempt >= max_retries or not is_rate_limit_error(error):
                raise
            attempt += 1
            delay = retry_delay(attempt, base_delay)
            _log_retry(label, error, attempt, max_retries, delay)
        finally:
            _crewai_retry_restore(token)
        await sleep(delay)


def _add_retry(llm: BaseLLM, label: str, max_retries: int, base_delay: float) -> None:
    """Wrap this LLM object's `call` and `acall` methods with our retry.

    CrewAI's agents always talk to the model through these two methods, so
    wrapping them protects every request the agent makes.
    """
    original_call = llm.call
    original_acall = llm.acall

    @functools.wraps(original_call)
    def call(*args: Any, **kwargs: Any) -> Any:
        return call_with_retry(
            lambda: original_call(*args, **kwargs),
            max_retries=max_retries,
            base_delay=base_delay,
            label=label,
        )

    @functools.wraps(original_acall)
    async def acall(*args: Any, **kwargs: Any) -> Any:
        return await acall_with_retry(
            lambda: original_acall(*args, **kwargs),
            max_retries=max_retries,
            base_delay=base_delay,
            label=label,
        )

    # LLM objects are pydantic models, which block setting unknown attributes
    # the normal way (llm.call = ...). object.__setattr__ goes around that.
    object.__setattr__(llm, "call", call)
    object.__setattr__(llm, "acall", acall)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _llm_kwargs(settings: LLMSettings) -> dict[str, Any]:
    """Turn our settings into arguments for crewai.LLM(...).

    Optional values are only passed when set, so the provider's own defaults
    are used otherwise.
    """
    kwargs: dict[str, Any] = {"model": settings.model, "api_key": settings.api_key}
    if settings.base_url is not None:
        kwargs["base_url"] = settings.base_url
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    if settings.max_tokens is not None:
        kwargs["max_tokens"] = settings.max_tokens
    return kwargs


def get_llm(role: str, config: AppConfig | None = None) -> BaseLLM:
    """Return a ready-to-use CrewAI LLM for one agent role.

    Args:
        role: "researcher", "analyst" or "writer".
        config: Settings from load_config(). If not given, .env is loaded here.

    Raises:
        ConfigError: unknown role, or the model's provider needs an extra
            package that is not installed.
    """
    config = config or load_config()
    settings = config.llm(role)  # raises ConfigError for an unknown role

    try:
        llm = LLM(**_llm_kwargs(settings))
    except ImportError as exc:
        # e.g. gemini/... models need: pip install "crewai[google-genai]"
        raise ConfigError(
            f"The model for '{role}' ({settings.model}) needs a package that is not installed. "
            f"Details: {exc}"
        ) from None

    _add_retry(
        llm,
        label=f"{role} ({settings.model})",
        max_retries=config.llm_max_retries,
        base_delay=config.llm_retry_base_delay,
    )
    return llm
