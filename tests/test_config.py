"""raven/config.py — settings.json loading/saving."""
import json

import pytest

from raven import config


def test_defaults_when_no_file(settings_path):
    assert not settings_path.exists()
    settings = config.load_settings()
    assert settings == config.DEFAULT_SETTINGS
    # must be a copy: mutating the result should not corrupt the module default
    settings["statusline"]["segments"].append("x")
    assert "x" not in config.DEFAULT_SETTINGS["statusline"]["segments"]


def test_override_merges_one_level_deep(settings_path):
    settings_path.write_text(json.dumps({"statusline": {"segments": ["model", "cpu"]}}))
    settings = config.load_settings()
    assert settings["statusline"]["segments"] == ["model", "cpu"]
    assert settings["model"] == config.DEFAULT_SETTINGS["model"]  # untouched section survives


def test_malformed_json_falls_back_to_defaults(settings_path):
    settings_path.write_text("{not valid json")
    assert config.load_settings() == config.DEFAULT_SETTINGS


def test_save_then_load_round_trips(settings_path):
    config.save_settings({"statusline": {"segments": ["tokens"]}})
    assert config.load_settings()["statusline"]["segments"] == ["tokens"]


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "does" / "not" / "exist" / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", nested)
    config.save_settings({"model": {"name": "x", "fallbacks": []}})
    assert nested.exists()


# ---------------------------------------------------------------------------
# model.provider + get_api_key(provider): multi-provider support (NVIDIA)
# ---------------------------------------------------------------------------

def test_default_model_provider_is_openrouter(settings_path):
    assert config.load_settings()["model"]["provider"] == "openrouter"


def test_model_provider_override_merges_like_any_other_model_field(settings_path):
    settings_path.write_text(json.dumps({"model": {"provider": "nvidia", "name": "meta/llama-3.1-8b-instruct"}}))
    settings = config.load_settings()
    assert settings["model"]["provider"] == "nvidia"
    assert settings["model"]["name"] == "meta/llama-3.1-8b-instruct"
    assert settings["model"]["fallbacks"] == config.DEFAULT_SETTINGS["model"]["fallbacks"]  # untouched


def test_get_api_key_reads_the_right_env_var_per_provider(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-key")
    assert config.get_api_key() == "or-key"  # default, unchanged for every pre-existing call site
    assert config.get_api_key("openrouter") == "or-key"
    assert config.get_api_key("nvidia") == "nv-key"


def test_get_api_key_missing_env_var_raises_a_clear_message(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        config.get_api_key("nvidia")


def test_get_api_key_unknown_provider_raises_a_clear_message():
    with pytest.raises(RuntimeError, match="Unknown model provider"):
        config.get_api_key("openai")


# ---------------------------------------------------------------------------
# permissions (C3): user-configurable, additive trust
# ---------------------------------------------------------------------------

def test_default_permissions_are_empty(settings_path):
    assert config.load_settings()["permissions"] == {"allow_commands": [], "allow_git": []}


def test_permissions_override_merges_like_any_other_section(settings_path):
    settings_path.write_text(json.dumps({"permissions": {"allow_commands": ["pytest"]}}))
    settings = config.load_settings()
    assert settings["permissions"]["allow_commands"] == ["pytest"]


# ---------------------------------------------------------------------------
# hooks (D1): user-configured pre/post automation
# ---------------------------------------------------------------------------

def test_default_hooks_are_empty(settings_path):
    assert config.load_settings()["hooks"] == {"pre": {}, "post": {}}


def test_hooks_override_merges_like_any_other_section(settings_path):
    settings_path.write_text(json.dumps({"hooks": {"post": {"edit_file": "black {path}"}}}))
    settings = config.load_settings()
    assert settings["hooks"]["post"]["edit_file"] == "black {path}"
