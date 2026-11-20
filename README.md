# Market Pulse Crew

A multi-agent market research and competitor intelligence system built with [CrewAI](https://docs.crewai.com/).

You give it a company or an industry. You can also add a list of competitors and a focus (for example, "pricing"). Three AI agents then research the web, compare the competitors, and write an executive-ready briefing in Markdown.

The project is **model-agnostic**. Each agent can use any model that [LiteLLM](https://docs.litellm.ai/docs/providers) or an OpenAI-compatible API supports, and it's designed around **free tiers** (Groq, Google AI Studio, Hugging Face, OpenRouter, Cerebras, …). No model name is hardcoded: everything comes from your `.env` file.

> **Project status: work in progress.** Configuration and the LLM factory are finished. The agents, tasks, crew, command-line runner and Streamlit UI are **not built yet**. See the [Roadmap](#roadmap).

---

## How it works

Three agents run one after another (a *sequential* crew). Each agent passes its output to the next.

```
 Input: company / industry, competitors (optional), focus (optional)
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────┐
  │ 1. Market Researcher                                     │
  │    Searches the web and scrapes pages for current facts  │
  └──────────────────────────────────────────────────────────┘
                               │ research notes + sources
                               ▼
  ┌──────────────────────────────────────────────────────────┐
  │ 2. Competitor Analyst                                    │
  │    Compares the competitors using the researcher's notes │
  └──────────────────────────────────────────────────────────┘
                               │ comparison + insights
                               ▼
  ┌──────────────────────────────────────────────────────────┐
  │ 3. Report Writer                                         │
  │    Writes the final Markdown briefing                    │
  └──────────────────────────────────────────────────────────┘
                               │
                               ▼
         reports/<company>_<timestamp>.md
```

The final report will contain:

- Executive summary
- Key findings
- Competitor comparison table
- Opportunities and risks
- Recommendations
- Sources

---

## Features

| Feature | Status |
|---|---|
| One central settings loader with friendly error messages (`config.py`) | ✅ Done |
| A different model for each agent, or one default model for all | ✅ Done |
| API keys are never printed or logged | ✅ Done |
| Retry with exponential backoff on rate-limit errors (`llm_factory.py`) | ✅ Done |
| Free, keyless web search with DuckDuckGo | 🕒 Planned (Step 3) |
| Optional Serper (Google) search, with automatic fallback to DuckDuckGo | 🕒 Planned (Step 3) |
| Web page scraping | 🕒 Planned (Step 3) |
| The three agents and their tasks | 🕒 Planned (Steps 4–5) |
| `run_market_pulse()`, one function that runs everything and returns the report | 🕒 Planned (Step 6) |
| Saving reports to `reports/` | 🕒 Planned (Step 6) |
| Command-line runner | 🕒 Planned (Step 7) |
| Automated tests (pytest) | 🕒 Planned (Step 8) |
| Streamlit web UI | 🕒 Later (after the core is finished) |

---

## Project structure

Files marked *(planned)* don't exist yet.

```
market-pulse-crew/
├── src/
│   └── market_pulse/
│       ├── __init__.py
│       ├── config.py         ✅ Loads and checks all settings from .env
│       ├── llm_factory.py    ✅ Builds each agent's LLM, with rate-limit retry
│       ├── tools.py          (planned) Search tool + website scraper
│       ├── agents.py         (planned) Researcher, Analyst, Writer
│       ├── tasks.py          (planned) One task per agent
│       ├── crew.py           (planned) Puts agents + tasks together
│       ├── runner.py         (planned) run_market_pulse(): the main entry point
│       └── utils.py          (planned) Small helpers (e.g. saving reports)
├── scripts/
│   └── run_cli.py            (planned) Run a report from the terminal
├── tests/                    (planned) pytest tests
├── reports/                  Generated reports go here (git-ignored)
├── app.py                    (planned) Streamlit UI, empty for now
├── .env.example              Template for your settings
├── requirements.txt
├── LICENSE
└── README.md
```

**Design rules**

- **All settings go through `config.py`.** It's the only file that reads `.env`. The other modules receive settings from it.
- **The UI is kept separate from the core logic.** The future Streamlit app will only call `run_market_pulse()` and display the Markdown it returns.
- **No package install is needed.** Scripts outside `src/` add `src/` to Python's import path themselves.

---

## Requirements

- Python 3.13 (other recent 3.x versions will probably work, but haven't been tested)
- At least one free API key from a model provider, for example:
  - [Groq](https://console.groq.com/keys)
  - [Google AI Studio](https://aistudio.google.com/apikey) (Gemini)
  - [Hugging Face](https://huggingface.co/settings/tokens)
  - [OpenRouter](https://openrouter.ai/keys)
- A [Serper](https://serper.dev) key, **only** if you want Google search results. DuckDuckGo needs no key.

---

## Installation

```powershell
# 1. Get the code
git clone <repo-url>
cd market-pulse-crew

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/Scripts/activate       # Windows Git Bash
# source .venv/bin/activate           # macOS / Linux

# 3. Install the packages
pip install -r requirements.txt

# 4. Create your settings file
copy .env.example .env                # macOS / Linux: cp .env.example .env
```

Then open `.env` and put in your real API keys (see [Configuration](#configuration)).

`requirements.txt` installs CrewAI with two extras:

- `crewai[litellm]` adds support for providers that CrewAI doesn't talk to directly, such as `groq/...` models.
- `crewai[google-genai]` adds support for `gemini/...` models through Google's own SDK.

---

## Configuration

All settings live in `.env`. It's git-ignored, so **never commit it**. `.env.example` lists every setting with a short comment.

### Model string format

Models use LiteLLM's `provider/model-name` format:

| Provider | Example `MODEL` value | `BASE_URL` |
|---|---|---|
| Groq | `groq/llama-3.3-70b-versatile` | not needed |
| Google AI Studio | `gemini/gemini-2.5-flash` | not needed |
| OpenRouter | `openrouter/meta-llama/llama-3.3-70b-instruct:free` | not needed |
| Cerebras | `cerebras/llama-3.3-70b` | not needed |
| **Any OpenAI-compatible API** | `openai/<model-name>` | **required** |

With the `openai/` prefix you can reach many providers through their OpenAI-compatible URL. For example:

- Groq: `https://api.groq.com/openai/v1`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/`
- Hugging Face: `https://router.huggingface.co/v1`

> ⚠️ If you use `openai/...` **without** a `BASE_URL`, the request goes to OpenAI's own paid API and fails.

### Default model and per-agent models

- `DEFAULT_LLM_MODEL` and `DEFAULT_LLM_API_KEY` are **required**. `DEFAULT_LLM_BASE_URL` is optional.
- Each agent can override them with its own `RESEARCHER_LLM_*`, `ANALYST_LLM_*` and `WRITER_LLM_*` values. Leave them empty to use the default.

When an override is left empty, the default is used, with one safety rule. The API key and base URL are copied from the default **only if the agent's provider prefix** (the text before the first `/`) **is the same as the default's**. If the providers differ and you didn't set the agent's own key, the app stops and tells you which key is missing.

> 💡 **Tip:** if all your models use the `openai/` prefix, the app sees them as the *same* provider. So always set each agent's own `API_KEY` and `BASE_URL`, otherwise it will quietly use the default ones.

### Example: a different free model for each agent

You can define each key **once** and reuse it with `${NAME}`:

```ini
# Your keys and model names (any names you like)
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...
HF_API_KEY=hf_...

# Default model (Groq, through its OpenAI-compatible URL)
DEFAULT_LLM_MODEL=openai/llama-3.3-70b-versatile
DEFAULT_LLM_API_KEY=${GROQ_API_KEY}
DEFAULT_LLM_BASE_URL=https://api.groq.com/openai/v1

# Market Researcher -> Gemini
RESEARCHER_LLM_MODEL=openai/gemini-3.5-flash-lite
RESEARCHER_LLM_API_KEY=${GEMINI_API_KEY}
RESEARCHER_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# Competitor Analyst -> DeepSeek on Hugging Face
ANALYST_LLM_MODEL=openai/deepseek-ai/DeepSeek-V4.1-Flash-1017
ANALYST_LLM_API_KEY=${HF_API_KEY}
ANALYST_LLM_BASE_URL=https://router.huggingface.co/v1

# Report Writer -> Kimi on Hugging Face
WRITER_LLM_MODEL=openai/moonshotai/Kimi-K3
WRITER_LLM_API_KEY=${HF_API_KEY}
WRITER_LLM_BASE_URL=https://router.huggingface.co/v1
```

> ⚠️ Write `${GROQ_API_KEY}` with `${ }`. A plain `GROQ_API_KEY` is read as the literal text "GROQ_API_KEY", not as your key. Also, define a variable **above** the lines that use it.

### Other settings

| Setting | Default | What it does |
|---|---|---|
| `LLM_TEMPERATURE` | provider default | 0.0 = focused/factual, higher = more creative (0.0–2.0) |
| `LLM_MAX_TOKENS` | provider default | Max length of each model answer |
| `AGENT_MAX_RPM` | `10` | Max LLM requests per minute, per agent |
| `AGENT_MAX_ITER` | `8` | Max thinking/tool steps per agent |
| `LLM_MAX_RETRIES` | `3` | Retries after a rate-limit error |
| `LLM_RETRY_BASE_DELAY` | `10` | Seconds before the first retry. The wait doubles each time (10 → 20 → 40 …) |
| `SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo` (free, no key) or `serper` (Google results) |
| `SERPER_API_KEY` | – | Only needed for `SEARCH_PROVIDER=serper` |
| `SEARCH_FALLBACK_TO_DUCKDUCKGO` | `true` | If Serper fails (e.g. no credits left), use DuckDuckGo instead |
| `SEARCH_MAX_RESULTS` | `5` | Search results per query |
| `CREWAI_DISABLE_TELEMETRY`, `OTEL_SDK_DISABLED` | `true` | Turn off CrewAI's usage telemetry |

> The search settings are already read and checked. The search tools that use them come in Step 3.

### Check your settings

```powershell
python src/market_pulse/config.py
```

This prints a summary of every agent's model, base URL and the other settings. API keys are shown only as `key=set`, never the key itself. If something is missing or wrong, you get a clear message telling you what to fix.

---

## Usage

### Available now

Check your configuration:

```powershell
python src/market_pulse/config.py
```

Build an agent's LLM in your own Python code (run it from the project root with `src` on the import path):

```python
from market_pulse.config import load_config
from market_pulse.llm_factory import get_llm

config = load_config()
researcher_llm = get_llm("researcher", config)   # or "analyst", "writer"
```

### Coming later

> 🕒 **Not implemented yet.** The commands below show the planned usage.

From the terminal (Step 7):

```powershell
python scripts/run_cli.py
```

From Python (Step 6):

```python
from market_pulse.runner import run_market_pulse

report_markdown = run_market_pulse(
    company="Notion",
    competitors=["Coda", "Obsidian"],   # optional
    focus="pricing",                    # optional
)
```

Each report will also be saved as `reports/<company>_<timestamp>.md`.

With the Streamlit UI (after the core is finished):

```powershell
streamlit run app.py
```

---

## Free-tier protection

Free model tiers have strict limits on requests per minute. The project protects you in several ways:

- **Rate-limit retry with exponential backoff.** When a provider answers "too many requests" (HTTP 429), the call waits and tries again: 10s, then 20s, then 40s, using `LLM_RETRY_BASE_DELAY` and `LLM_MAX_RETRIES`. Other errors, like a wrong API key, fail immediately, because retrying wouldn't help.
- **Request limits per agent** (`AGENT_MAX_RPM`) and **step limits** (`AGENT_MAX_ITER`) keep each run short and cheap. *(These are applied once the agents exist, in Step 4.)*
- **Agent memory is turned off.** CrewAI's memory feature needs a paid OpenAI embeddings key. *(Step 4.)*
- **Free search by default.** DuckDuckGo needs no key. Serper is optional. *(Step 3.)*

---

## Testing

> 🕒 **Planned (Step 8).** The tests for `config.py` and `llm_factory.py` aren't written yet.

```powershell
pip install -r requirements-dev.txt   # installs pytest (file not created yet)
pytest
```

The tests won't need real API keys. `load_config(env={...})` accepts settings directly, and the retry functions accept a fake `sleep`, so tests run instantly.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `DEFAULT_LLM_MODEL is missing in .env` | Create `.env` from `.env.example` and fill it in. |
| `... is not valid. Use the format 'provider/model-name'` | The model needs a provider prefix, e.g. `groq/...` or `openai/...`. If you wrote a variable name, wrap it: `${GEMINI_MODEL}`. |
| `... uses provider 'x', but DEFAULT_LLM_MODEL uses 'y'` | That agent uses a different provider, so give it its own `<ROLE>_LLM_API_KEY`. |
| `... needs a package that is not installed` | Run `pip install -r requirements.txt` again. |
| Authentication error (401) at runtime | Check the key. If you use `openai/...`, make sure that agent's `BASE_URL` is set. |
| Many "rate limit hit" warnings | Lower `AGENT_MAX_RPM`, raise `LLM_RETRY_BASE_DELAY`, or use a different free model. |

---

## Roadmap

1. ✅ Project structure, `config.py`, `.env.example`
2. ✅ `llm_factory.py`: one LLM per agent, plus rate-limit retry
3. 🕒 `tools.py`: DuckDuckGo / Serper search (with fallback) + website scraper
4. 🕒 `agents.py`: Market Researcher, Competitor Analyst, Report Writer
5. 🕒 `tasks.py`: one task per agent
6. 🕒 `crew.py`, `runner.py`, `utils.py`: `run_market_pulse()` and report saving
7. 🕒 `scripts/run_cli.py`: run from the terminal
8. 🕒 `tests/`: pytest tests for config and the LLM factory
9. 🕒 Streamlit UI in `app.py`

---

## Tech stack

- [CrewAI](https://docs.crewai.com/) and crewai-tools: agents, tasks and crews
- [LiteLLM](https://docs.litellm.ai/): one interface for many model providers
- [python-dotenv](https://pypi.org/project/python-dotenv/): loads `.env`
- [Streamlit](https://streamlit.io/): web UI *(planned)*
- [ddgs](https://pypi.org/project/ddgs/): DuckDuckGo search *(planned, Step 3)*

## License

[MIT](LICENSE)
