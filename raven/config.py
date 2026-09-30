import copy
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SETTINGS_PATH = Path.home() / ".raven" / "settings.json"

# How many model round trips one turn may take before giving up. Lives here,
# not in assistant.py, purely so DEFAULT_SETTINGS below and the Assistant that
# reads it can't drift apart — assistant.py imports it from here and carries
# the full rationale for why this is bounded at all rather than unlimited.
DEFAULT_TOOL_ITERATIONS = 25
NOTES_PATH = Path.home() / ".raven" / "memory" / "notes.md"  # model-written, cross-session (B3)

DEFAULT_SETTINGS = {
    # Primary model + fallbacks tried in order when a free model is down/rate-limited.
    "model": {
        # Which LLMProvider subclass build_provider() constructs (llm_provider.py) --
        # "openrouter" or "nvidia" (build.nvidia.com's free-tier NIM API). Each
        # provider reads its own API key from a separate env var -- see
        # PROVIDER_API_KEY_ENV below -- so switching providers doesn't touch
        # whichever key isn't in use.
        "provider": "openrouter",
        "name": "nvidia/nemotron-3.5-lightning:free",
        "fallbacks": ["google/gemma-4-31b-it:free", "openrouter/free"],
        # V2: a SEPARATE model for analyze_image -- the main chat model above
        # isn't necessarily vision-capable, and a model that IS vision-capable
        # isn't necessarily the best (or free) choice for everything else, so
        # this is its own setting rather than reusing model.name. NOT yet
        # live-verified as of 2026-09-23 (OpenRouter's daily free-tier quota
        # was exhausted before this could be confirmed against a real call) --
        # check this is still current/free the first time vision is actually
        # used, and update here (or in settings.json) if it's moved on.
        "vision": "qwen/qwen2.5-vl-32b-instruct:free",
    },
    # Status-line segments, in display order. Available names live in statusline.SEGMENTS.
    "statusline": {"segments": ["model", "context", "tokens", "memory"]},
    # Per-turn ceilings the user can raise without editing the source.
    # tool_iterations: how many model round trips one turn may take before
    # giving up — see assistant.py's own comment for why this is bounded at
    # all rather than unlimited.
    "limits": {"tool_iterations": DEFAULT_TOOL_ITERATIONS},
    # C3: user-opt-in trust, ADDITIVE only — never removes the built-in safety
    # checks (SAFE_COMMANDS/SAFE_GIT, or the shell-metacharacter defeat
    # detection, which always applies regardless of this list). e.g.
    # {"allow_commands": ["pytest"]} lets a plain `pytest` invocation (via
    # run_command or run_tests) skip confirmation; "pytest; rm -rf ~" still
    # never does, since it contains a shell metacharacter.
    "permissions": {"allow_commands": [], "allow_git": []},
    # D1: automation the user pre-approves by putting it in this local file --
    # same trust boundary as permissions.allow_commands, so hooks never ask
    # for confirmation. tool_name -> shell command template, {arg} filled in
    # from that tool call's own arguments, e.g. {"post": {"edit_file": "black {path}"}}
    # to auto-format a file right after a successful edit. Scoped to the
    # model's own tool-calling loop only, not the manual /write, /run, etc.
    # slash commands.
    "hooks": {"pre": {}, "post": {}},
}


# Each provider's API key lives in its own env var, so switching model.provider
# in settings.json never touches a key that isn't currently in use.
PROVIDER_API_KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}


def get_api_key(provider: str = "openrouter") -> str:
    """The API key for `provider` (default "openrouter", so every pre-existing
    no-arg call site keeps working unchanged). Raises a clear, actionable
    RuntimeError -- never returns an empty/missing key silently -- for either
    an unrecognized provider name or a recognized one with no key set."""
    env_var = PROVIDER_API_KEY_ENV.get(provider)
    if env_var is None:
        raise RuntimeError(
            f"Unknown model provider: {provider!r}. Known providers: "
            f"{', '.join(sorted(PROVIDER_API_KEY_ENV))}."
        )
    key = os.environ.get(env_var)
    if not key:
        raise RuntimeError(f"Set {env_var} in your environment or .env file")
    return key


def load_settings() -> dict:
    """Defaults overlaid with ~/.raven/settings.json (merged one level deep)."""
    # Deep, not shallow: dict(v) alone only copies one level, so a NESTED list
    # (statusline.segments, model.fallbacks) would still be the same list
    # object as DEFAULT_SETTINGS's — mutating a loaded settings list in place
    # (e.g. .append()) would silently corrupt the module-wide default for the
    # rest of the process. Found by tests/test_config.py, not observed live.
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if not SETTINGS_PATH.exists():
        return settings
    try:
        overrides = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    for section, value in overrides.items():
        if isinstance(value, dict) and isinstance(settings.get(section), dict):
            settings[section].update(value)
        else:
            settings[section] = value
    return settings


def save_settings(settings: dict) -> None:
    """Persist settings to ~/.raven/settings.json."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
