"""The website never spends a server-side Anthropic key: token (granted/purchased) forges run on the Ollama
mixture with OpenRouter failover, and Anthropic is reachable only through a user's own BYOK key."""
from __future__ import annotations

import os

import pytest

import app as app_mod  # noqa: F401  (import blanks the env key at module load)
from conftest import H, login
from forge import ForgeError, _build_generators, _make_gen_factory


def test_process_holds_no_anthropic_key():
    assert os.environ.get("ANTHROPIC_API_KEY") == ""


def test_hosted_generator_path_is_refused():
    with pytest.raises(ForgeError, match="retired"):
        _build_generators(None, hosted=True, fake=False)
    with pytest.raises(ForgeError, match="retired"):
        _make_gen_factory(None, hosted=True, fake=False)


def test_no_key_no_path():
    with pytest.raises(ForgeError):
        _build_generators(None, hosted=False, fake=False)
    with pytest.raises(ForgeError):
        _make_gen_factory(None, hosted=False, fake=False)


def test_anthropic_generator_without_explicit_key_cannot_start():
    """Even if some code path constructed AnthropicGenerator with no key, it must fail rather than bill us."""
    from btsgen.generator import AnthropicGenerator
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicGenerator(model="claude-haiku-4-5")


def test_hosted_mode_post_is_gone(client):
    login(client, "nohosted@example.com")
    r = client.post("/api/forge-class", json={"mode": "hosted", "concept": "a frost mage"}, headers=H)
    assert r.status_code == 410
