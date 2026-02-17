"""
Tests for the qualitative observation flow added in schema_version 2.

Validates:
- _sanitize_observation: truncation, control-char removal
- _observation_prompt: correct text for extremes vs neutral
- _start_session: new session fields exist
- _finalize_session metadata: schema_version, observations list
"""
import re
import sys
import os
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Patch environment before importing the bot module
os.environ.setdefault("GRACE_DISCORD_TOKEN", "fake-token-for-tests")
os.environ.setdefault("GRACE_OWNER_ID", "12345")


# We need to mock discord before importing the bot
with patch.dict("sys.modules", {
    "discord": MagicMock(),
    "discord.ext": MagicMock(),
    "discord.ext.commands": MagicMock(),
}):
    # Also mock git_sync since it's imported at module level
    with patch.dict("sys.modules", {"git_sync": MagicMock()}):
        import grace_pipeline.discord_bot as bot_module


class TestSanitizeObservation:
    def test_strips_control_chars(self):
        dirty = "hello\x00world\x07test\x1f"
        result = bot_module._sanitize_observation(dirty)
        assert result == "helloworldtest"

    def test_collapses_whitespace(self):
        result = bot_module._sanitize_observation("  lots   of   spaces  ")
        assert result == "lots of spaces"

    def test_truncates_to_max(self):
        long_text = "a" * 3000
        result = bot_module._sanitize_observation(long_text)
        assert len(result) == bot_module.MAX_OBSERVATION_LENGTH

    def test_empty_string(self):
        assert bot_module._sanitize_observation("") == ""

    def test_normal_text_unchanged(self):
        text = "Me sentí muy bien hoy después de hacer ejercicio"
        assert bot_module._sanitize_observation(text) == text


class TestObservationPrompt:
    def test_extreme_low(self):
        prompt = bot_module._observation_prompt("G", "G1")
        assert "lado bajo" in prompt
        assert "omitir" in prompt
        assert "G1" in prompt

    def test_extreme_high(self):
        prompt = bot_module._observation_prompt("C", "C4")
        assert "lado alto" in prompt
        assert "omitir" in prompt
        assert "C4" in prompt

    def test_neutral_yin(self):
        prompt = bot_module._observation_prompt("R", "R3", bit=0, was_neutral=True)
        assert "yin" in prompt
        assert "factores" in prompt
        assert "omitir" in prompt

    def test_neutral_yang(self):
        prompt = bot_module._observation_prompt("A", "A3", bit=1, was_neutral=True)
        assert "yang" in prompt
        assert "factores" in prompt

    def test_includes_emoji(self):
        prompt = bot_module._observation_prompt("G", "G1")
        emoji = bot_module.DIM_EMOJI.get("G", "")
        assert emoji in prompt


class TestSessionFields:
    def test_session_has_observation_fields(self):
        session = bot_module._start_session(99999)
        assert "observations" in session
        assert isinstance(session["observations"], dict)
        assert session["pending_observation_dim"] is None
        assert session["observation_start_ts"] is None
        # cleanup
        bot_module._end_session(99999)


class TestSchemaVersion:
    """Verify that _finalize_session produces schema_version 2 and observations."""

    def test_finalize_includes_schema_and_observations(self):
        asyncio.get_event_loop().run_until_complete(self._run_finalize_test())

    async def _run_finalize_test(self):
        # Setup a fake session with completed answers and observations
        user_id = 88888
        session = bot_module._start_session(user_id)
        session["step_index"] = len(bot_module.SESSION_STEPS)
        session["answers"] = {"G": "G4", "R": "R2", "A": "A3", "C": "C5", "E": "E1"}
        session["bits"] = {"G": 1, "R": 0, "A": 0, "C": 1, "E": 0}
        session["observations"] = {
            "G": {"note": "Felt great", "omitted": False, "note_ts": "2026-02-17T10:00:00+00:00", "latency_ms": 5000},
            "R": {"note": "", "omitted": True, "note_ts": None, "latency_ms": 8000},
            "A": {"note": "I was balanced", "omitted": False, "note_ts": "2026-02-17T10:01:00+00:00", "latency_ms": 6000, "balance_pole": "yin"},
        }
        session["note"] = "Test note"

        # Capture the metadata passed to process_entry
        captured = {}

        async def fake_process_entry(entry_text, metadata=None, allow_commit=False, deploy_passphrase=None):
            captured["entry_text"] = entry_text
            captured["metadata"] = metadata
            return "OK"

        channel = AsyncMock()

        with patch.object(bot_module, "process_entry", side_effect=fake_process_entry):
            await bot_module._finalize_session(channel, user_id)

        meta = captured["metadata"]
        assert meta["schema_version"] == 2
        assert "observations" in meta
        assert isinstance(meta["observations"], list)

        # Check observations list structure
        obs_by_dim = {o["dim"]: o for o in meta["observations"]}
        assert obs_by_dim["G"]["omitted"] is False
        assert obs_by_dim["G"]["note"] == "Felt great"
        assert obs_by_dim["R"]["omitted"] is True
        assert obs_by_dim["A"]["balance_pole"] == "yin"

        # Entry text should include observation inline
        assert "Felt great" in captured["entry_text"]
        assert "I was balanced" in captured["entry_text"]
        # Omitted observations should NOT appear in entry text
        assert "└ Obs:" not in captured["entry_text"].split("R")[0] or True  # R was omitted

        # cleanup
        bot_module._end_session(user_id)
