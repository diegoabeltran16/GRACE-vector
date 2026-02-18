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
    """Verify that _finalize_session produces schema_version 2.

    Observations must NOT appear in cleartext metadata; they are
    appended to entry_text under the __OBSERVATIONS__ marker so
    the pipeline encrypts them together with the rest of the entry.
    """

    def test_finalize_includes_schema_and_encrypted_observations(self):
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

        # --- Privacy: observations must NOT be in cleartext metadata ---
        assert "observations" not in meta, \
            "observations must not appear in cleartext metadata"
        assert meta.get("observations_encrypted") is True
        assert meta.get("observations_count") == 3

        # --- Observations must be inside entry_text (will be encrypted) ---
        entry = captured["entry_text"]
        assert "__OBSERVATIONS__" in entry
        # Parse the serialised observations from the entry text
        marker_pos = entry.index("__OBSERVATIONS__")
        obs_json = entry[marker_pos + len("__OBSERVATIONS__"):].strip()
        obs_list = json.loads(obs_json)
        obs_by_dim = {o["dim"]: o for o in obs_list}
        assert obs_by_dim["G"]["omitted"] is False
        assert obs_by_dim["G"]["note"] == "Felt great"
        assert obs_by_dim["R"]["omitted"] is True
        assert obs_by_dim["A"]["balance_pole"] == "yin"

        # Human-readable part should also include non-omitted observations
        assert "Felt great" in entry
        assert "I was balanced" in entry

        # cleanup
        bot_module._end_session(user_id)


class TestTruncateForDiscord:
    """Verify Discord message truncation helper."""

    def test_short_message_unchanged(self):
        msg = "Hello world"
        assert bot_module._truncate_for_discord(msg) == msg

    def test_exact_limit_unchanged(self):
        msg = "x" * bot_module.DISCORD_MSG_LIMIT
        assert bot_module._truncate_for_discord(msg) == msg

    def test_long_message_truncated(self):
        msg = "a" * (bot_module.DISCORD_MSG_LIMIT + 500)
        result = bot_module._truncate_for_discord(msg)
        assert len(result) <= bot_module.DISCORD_MSG_LIMIT
        assert result.endswith("… (truncado)")

    def test_custom_limit(self):
        msg = "a" * 100
        result = bot_module._truncate_for_discord(msg, limit=50)
        assert len(result) <= 50
        assert result.endswith("… (truncado)")


class TestFinalizeSessionErrorHandling:
    """Verify _finalize_session sends error messages on failure and always cleans up."""

    def test_finalize_reports_error_and_cleans_session(self):
        asyncio.get_event_loop().run_until_complete(self._run_error_test())

    async def _run_error_test(self):
        user_id = 77777
        session = bot_module._start_session(user_id)
        session["step_index"] = len(bot_module.SESSION_STEPS)
        session["answers"] = {"G": "G4", "R": "R2", "A": "A3", "C": "C5", "E": "E1"}
        session["bits"] = {"G": 1, "R": 0, "A": 0, "C": 1, "E": 0}
        session["observations"] = {}
        session["note"] = "Test"

        async def failing_process_entry(*args, **kwargs):
            raise RuntimeError("Simulated pipeline failure")

        channel = AsyncMock()

        with patch.object(bot_module, "process_entry", side_effect=failing_process_entry):
            await bot_module._finalize_session(channel, user_id)

        # Session must be cleaned up even on error
        assert bot_module._current_session(user_id) is None

        # An error message should have been sent to the channel
        sent_messages = [str(call.args[0]) for call in channel.send.call_args_list]
        assert any("Error" in msg or "error" in msg.lower() for msg in sent_messages), \
            f"Expected error message in: {sent_messages}"


class TestProcessEntryUsesTempFiles:
    """Verify process_entry writes temp files instead of passing args directly."""

    def test_uses_from_file_flag(self):
        asyncio.get_event_loop().run_until_complete(self._run_tempfile_test())

    async def _run_tempfile_test(self):
        captured_cmd = {}

        # Mock create_subprocess_exec to capture the command
        async def mock_subprocess(*args, **kwargs):
            captured_cmd["args"] = list(args)
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"OK output", b""))
            mock_proc.returncode = 0
            return mock_proc

        # Mock script.exists() to return True
        with patch.object(bot_module.Path, "exists", return_value=True):
            with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
                metadata = {
                    "schema_version": 2,
                    "source": "test",
                    "observations_encrypted": True,
                    "observations_count": 1,
                }
                result = await bot_module.process_entry(
                    "Test entry text",
                    metadata=metadata,
                    allow_commit=False,
                )

        args = captured_cmd.get("args", [])
        # Should use --from-file, NOT --entry
        assert "--from-file" in args, f"Expected --from-file in {args}"
        assert "--entry" not in args, f"Did not expect --entry in {args}"
        # Should use --metadata with a file path (not raw JSON)
        if "--metadata" in args:
            meta_idx = args.index("--metadata")
            meta_val = args[meta_idx + 1]
            # The value should be a file path, not raw JSON
            assert not meta_val.startswith("{"), \
                f"Expected file path for --metadata, got JSON: {meta_val[:80]}"
        assert "Entry processed successfully." in result
