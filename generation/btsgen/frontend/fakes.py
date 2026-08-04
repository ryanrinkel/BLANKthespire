"""Offline fake stage generator — duck-types AnthropicGenerator (first_attempt / repair) so the staged
front-end runs with no API key. Each stage contract supplies its own deterministic fake_output(brief)."""
from __future__ import annotations

import json


class _StageFake:
    """Wrap a stage contract; return its deterministic fake_output as JSON text, mirroring the real
    generator surface (first_attempt -> (text, messages); repair -> same)."""
    model = "fake-offline"

    def __init__(self, contract_mod) -> None:
        self._contract = contract_mod

    def _emit(self, brief) -> str:
        return json.dumps(self._contract.fake_output(brief))

    def first_attempt(self, brief) -> tuple[str, list[dict]]:
        text = self._emit(brief)
        return text, [{"role": "user", "content": ""}, {"role": "assistant", "content": text}]

    def repair(self, messages, prev_text, errors) -> tuple[str, list[dict]]:
        # fakes are always valid; repair just re-emits
        text = self._emit_from_messages(messages)
        return text, messages + [{"role": "assistant", "content": text}]

    def _emit_from_messages(self, messages) -> str:  # pragma: no cover - fakes never need repair
        return messages[-1]["content"] if messages else "{}"
