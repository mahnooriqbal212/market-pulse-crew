"""Load and validate all settings from the environment (normally your .env file).

Nothing about models or tools is hardcoded: every value comes from here.

Quick check from the project root:
    python src/market_pulse/config.py
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import load_dotenv

# The three agent roles. Each one can have its own model, or use the DEFAULT.
ROLES: tuple[str, ...] = ("researcher", "analyst", "writer")

# Supported web search providers (the tools themselves are built in tools.py).
SEARCH_PROVIDERS: tuple[str, ...] = ("duckduckgo", "serper")

# Project root = two folders above this file (src/market_pulse/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    """Raised when a setting in .env is missing or invalid."""


# ---------------------------------------------------------------------------
# Settings objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMSettings:
    """Model settings for one agent role."""

    role: str
    model: str  # LiteLLM style: "provider/model-name"
    api_key: str = field(repr=False)  # repr=False -> never shown when printed
    base_url: str | None
    temperature: float | None  # None -> use the provider's default
    max_tokens: int | None  # None -> use the provider's default
    source: str  # "DEFAULT" or "override" (where the model came from)

    @property
    def provider(self) -> str:
        """The part of the model string before the first '/' (e.g. 'groq')."""
        return _provider_of(self.model)


@dataclass(frozen=True)
class SearchSettings:
    """Web search settings."""

    provider: str  # "duckduckgo" or "serper"
    serper_api_key: str | None = field(repr=False)
    fallback_to_duckduckgo: bool  # if Serper fails (e.g. no credits) use DuckDuckGo
    max_results: int


@dataclass(frozen=True)
class AppConfig:
    """All settings for the app, in one place."""

    llms: dict[str, LLMSettings]
    search: SearchSettings
    agent_max_rpm: int  # max LLM requests per minute, per agent
    agent_max_iter: int  # max thinking/tool steps per agent
    llm_max_retries: int  # retries when the provider says "rate limit"
    llm_retry_base_delay: float  # seconds to wait before the first retry

    def llm(self, role: str) -> LLMSettings:
        """Return the model settings for a role ('researcher', 'analyst', 'writer')."""
        if role not in self.llms:
            raise ConfigError(f"Unknown role '{role}'. Valid roles: {', '.join(ROLES)}.")
        return self.llms[role]

    def summary(self) -> list[str]:
        """Human-readable summary lines. API keys are NEVER included."""
        lines = ["LLM settings:"]
        for role in ROLES:
            s = self.llms[role]
            lines.append(
                f"  {role:<10} model={s.model}  key=set  "
                f"base_url={s.base_url or 'none'}  from={s.source}"
            )
        first = self.llms[ROLES[0]]
        lines.append(
            f"  temperature={first.temperature if first.temperature is not None else 'provider default'}"
            f"  max_tokens={first.max_tokens or 'provider default'}"
        )
        lines.append("Search settings:")
        lines.append(
            f"  provider={self.search.provider}  "
            f"serper_key={'set' if self.search.serper_api_key else 'not set'}  "
            f"fallback_to_duckduckgo={self.search.fallback_to_duckduckgo}  "
            f"max_results={self.search.max_results}"
        )
        lines.append("Agent / rate-limit settings:")
        lines.append(
            f"  max_rpm={self.agent_max_rpm}  max_iter={self.agent_max_iter}  "
            f"max_retries={self.llm_max_retries}  retry_base_delay={self.llm_retry_base_delay}s"
        )
        return lines


# ---------------------------------------------------------------------------
# Small helpers for reading and checking values
# ---------------------------------------------------------------------------


def _get(env: Mapping[str, str], name: str) -> str | None:
    """Read a variable. Empty or whitespace-only values count as 'not set'."""
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _provider_of(model: str) -> str:
    return model.split("/", 1)[0].strip().lower()


def _check_model(name: str, value: str) -> None:
    provider, _, model_name = value.partition("/")
    if not provider.strip() or not model_name.strip():
        raise ConfigError(
            f"{name}='{value}' is not valid. Use the format 'provider/model-name', "
            f"for example: groq/llama-3.3-70b-versatile"
        )


def _check_api_key(name: str, value: str) -> None:
    placeholders = ("your-", "your_", "<", "changeme", "xxx")
    if value.lower().startswith(placeholders):
        raise ConfigError(f"{name} still has the example placeholder value. Put your real key in .env.")


def _check_base_url(name: str, value: str) -> None:
    if not value.startswith(("http://", "https://")):
        raise ConfigError(f"{name} must start with http:// or https:// (got '{value}').")


def _parse_int(env: Mapping[str, str], name: str, default: int | None, minimum: int = 1) -> int | None:
    raw = _get(env, name)
    if raw is None:
        return default
    try:
        number = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number (got '{raw}').") from None
    if number < minimum:
        raise ConfigError(f"{name} must be {minimum} or more (got {number}).")
    return number


def _parse_float(
    env: Mapping[str, str], name: str, default: float | None, minimum: float, maximum: float
) -> float | None:
    raw = _get(env, name)
    if raw is None:
        return default
    try:
        number = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number (got '{raw}').") from None
    if not minimum <= number <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum} (got {number}).")
    return number


def _parse_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _get(env, name)
    if raw is None:
        return default
    if raw.lower() in ("true", "1", "yes", "on"):
        return True
    if raw.lower() in ("false", "0", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false (got '{raw}').")


# ---------------------------------------------------------------------------
# Building the settings
# ---------------------------------------------------------------------------


def _load_default_llm(
    env: Mapping[str, str], temperature: float | None, max_tokens: int | None
) -> LLMSettings:
    """Read the DEFAULT_LLM_* values. Model and API key are required."""
    model = _get(env, "DEFAULT_LLM_MODEL")
    if model is None:
        raise ConfigError(
            "DEFAULT_LLM_MODEL is missing in .env. "
            "Example: DEFAULT_LLM_MODEL=groq/llama-3.3-70b-versatile"
        )
    _check_model("DEFAULT_LLM_MODEL", model)

    api_key = _get(env, "DEFAULT_LLM_API_KEY")
    if api_key is None:
        raise ConfigError("DEFAULT_LLM_API_KEY is missing in .env.")
    _check_api_key("DEFAULT_LLM_API_KEY", api_key)

    base_url = _get(env, "DEFAULT_LLM_BASE_URL")
    if base_url is not None:
        _check_base_url("DEFAULT_LLM_BASE_URL", base_url)

    return LLMSettings(
        role="default",
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        source="DEFAULT",
    )


def _load_role_llm(env: Mapping[str, str], role: str, default: LLMSettings) -> LLMSettings:
    """Read <ROLE>_LLM_* overrides, falling back to the DEFAULT values.

    Fallback rule (each value separately):
      - MODEL missing     -> use DEFAULT_LLM_MODEL
      - API_KEY missing   -> use DEFAULT_LLM_API_KEY, but only if the provider is
                             the same as the default one (a Groq key will not work
                             on OpenRouter, so we stop with a clear error instead)
      - BASE_URL missing  -> use DEFAULT_LLM_BASE_URL, only if same provider
    """
    prefix = role.upper()
    model = _get(env, f"{prefix}_LLM_MODEL")
    api_key = _get(env, f"{prefix}_LLM_API_KEY")
    base_url = _get(env, f"{prefix}_LLM_BASE_URL")

    # No override at all -> exact copy of DEFAULT.
    if model is None and api_key is None and base_url is None:
        return replace(default, role=role)

    if model is not None:
        _check_model(f"{prefix}_LLM_MODEL", model)
    final_model = model or default.model
    provider = _provider_of(final_model)
    same_provider = provider == default.provider

    if api_key is None:
        if not same_provider:
            raise ConfigError(
                f"{prefix}_LLM_MODEL uses provider '{provider}', but DEFAULT_LLM_MODEL uses "
                f"'{default.provider}'. Please set {prefix}_LLM_API_KEY in .env for this provider."
            )
        api_key = default.api_key
    else:
        _check_api_key(f"{prefix}_LLM_API_KEY", api_key)

    if base_url is not None:
        _check_base_url(f"{prefix}_LLM_BASE_URL", base_url)
    elif same_provider:
        base_url = default.base_url

    return replace(
        default,
        role=role,
        model=final_model,
        api_key=api_key,
        base_url=base_url,
        source="override",
    )


def _load_search(env: Mapping[str, str]) -> SearchSettings:
    """Read SEARCH_* and SERPER_API_KEY values."""
    provider = (_get(env, "SEARCH_PROVIDER") or "duckduckgo").lower()
    if provider not in SEARCH_PROVIDERS:
        raise ConfigError(
            f"SEARCH_PROVIDER='{provider}' is not supported. Choose one of: {', '.join(SEARCH_PROVIDERS)}."
        )

    serper_key = _get(env, "SERPER_API_KEY")
    if serper_key is not None:
        _check_api_key("SERPER_API_KEY", serper_key)
    if provider == "serper" and serper_key is None:
        raise ConfigError("SEARCH_PROVIDER=serper but SERPER_API_KEY is missing in .env.")

    return SearchSettings(
        provider=provider,
        serper_api_key=serper_key,
        fallback_to_duckduckgo=_parse_bool(env, "SEARCH_FALLBACK_TO_DUCKDUCKGO", True),
        max_results=_parse_int(env, "SEARCH_MAX_RESULTS", 5) or 5,
    )


def load_config(env: Mapping[str, str] | None = None, env_file: str | Path | None = None) -> AppConfig:
    """Read .env, validate everything, and return an AppConfig.

    Args:
        env: Optional dictionary of variables to use instead of the real
            environment (handy for tests). If given, .env is NOT read.
        env_file: Optional path to a .env file. Default: <project root>/.env

    Raises:
        ConfigError: with a friendly message if something is missing or wrong.
    """
    if env is None:
        # override=False -> real environment variables win over the .env file.
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
        env = os.environ

    temperature = _parse_float(env, "LLM_TEMPERATURE", None, minimum=0.0, maximum=2.0)
    max_tokens = _parse_int(env, "LLM_MAX_TOKENS", None)

    default = _load_default_llm(env, temperature, max_tokens)
    llms = {role: _load_role_llm(env, role, default) for role in ROLES}

    return AppConfig(
        llms=llms,
        search=_load_search(env),
        agent_max_rpm=_parse_int(env, "AGENT_MAX_RPM", 10) or 10,
        agent_max_iter=_parse_int(env, "AGENT_MAX_ITER", 8) or 8,
        llm_max_retries=_parse_int(env, "LLM_MAX_RETRIES", 3, minimum=0) or 0,
        llm_retry_base_delay=_parse_float(env, "LLM_RETRY_BASE_DELAY", 10.0, minimum=0.0, maximum=300.0)
        or 0.0,
    )


if __name__ == "__main__":
    # Lets you check your .env quickly: python src/market_pulse/config.py
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Config problem: {exc}")
        raise SystemExit(1) from None
    print("\n".join(config.summary()))
    print("\nConfig OK.")
