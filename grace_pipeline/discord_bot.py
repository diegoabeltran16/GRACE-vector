import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path

import discord
from discord.ext import commands


# Configuration
REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRO_PATH = REPO_ROOT / "data" / "registros" / "registro.jsonl"
ENCRYPTED_PATH = REPO_ROOT / "data_encr" / "registro_encr.jsonl"
GRACE_STATES_PATH = REPO_ROOT / "config" / "estados_grace.json"
TOKEN_ENV_VAR = "GRACE_DISCORD_TOKEN"
TOKEN_FILE_ENV_VAR = "GRACE_DISCORD_TOKEN_FILE"
DEFAULT_TOKEN_FILE = REPO_ROOT / "config" / "secrets" / "grace_bot_token.txt"

BOT_TOKEN = os.environ.get(TOKEN_ENV_VAR)
OWNER_ID = os.environ.get("GRACE_OWNER_ID")  # should be numeric string
ALLOW_PUSH = os.environ.get("GRACE_ALLOW_PUSH") == "1"

# Session management for guided check-ins
DIM_ORDER = ["G", "R", "A", "C", "E"]
SESSION_STEPS = DIM_ORDER + ["NOTE"]
SESSIONS: dict[int, dict] = {}

# Emojis per dimension for friendlier prompts
DIM_EMOJI = {
    "G": "⚧️",
    "R": "🤝",
    "A": "🧠",
    "C": "💪",
    "E": "🌌",
}

# Short descriptions to remind the user what each dimension means
DIM_DESCRIPTIONS = {
    "G": "Género: cómo sientes tu identidad/expresión hoy",
    "R": "Relaciones: calidad de tus vínculos hoy",
    "A": "Aprendizaje cognitivo: claridad mental",
    "C": "Cuerpo: energía, tensión o desconexión",
    "E": "Experiencia personal: tono emocional/narrativo"
}

def _load_token_from_file() -> str | None:
    candidates = []
    if token_file_env := os.environ.get(TOKEN_FILE_ENV_VAR):
        candidates.append(Path(token_file_env))
    candidates.append(DEFAULT_TOKEN_FILE)

    for path in candidates:
        try:
            if path.exists():
                # utf-8-sig strips BOM if present
                token = path.read_text(encoding="utf-8-sig").strip()
                # remove accidental quotes
                if token.startswith("\"") and token.endswith("\""):
                    token = token[1:-1]
                if token.startswith("'") and token.endswith("'"):
                    token = token[1:-1]
                if token:
                    return token
        except Exception:
            continue
    return None

if not BOT_TOKEN:
    BOT_TOKEN = _load_token_from_file()

if not BOT_TOKEN:
    raise RuntimeError(
        "Set GRACE_DISCORD_TOKEN or provide a token file via GRACE_DISCORD_TOKEN_FILE "
        f"or {DEFAULT_TOKEN_FILE}"
    )

def _token_source() -> str:
    if os.environ.get(TOKEN_ENV_VAR):
        return f"env:{TOKEN_ENV_VAR}"
    if os.environ.get(TOKEN_FILE_ENV_VAR):
        return f"file:{os.environ.get(TOKEN_FILE_ENV_VAR)}"
    return f"file:{DEFAULT_TOKEN_FILE}"
if not OWNER_ID:
    raise RuntimeError("Environment variable GRACE_OWNER_ID is required (numeric Discord user ID).")


def _load_grace_states() -> dict:
    try:
        with GRACE_STATES_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


GRACE_STATES = _load_grace_states()


intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


def repo_last_commit_short():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return None


def _line_count(path: Path):
    try:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return None


def _start_session(user_id: int) -> dict:
    session = {
        "step_index": 0,
        "answers": {},
        "bits": {},
        "note": "",
        "last_options": None,
        "pending_collapse_dim": None,
    }
    SESSIONS[user_id] = session
    return session


def _end_session(user_id: int):
    SESSIONS.pop(user_id, None)


def _current_session(user_id: int) -> dict | None:
    return SESSIONS.get(user_id)


def _dimension_options(dim: str):
    states = GRACE_STATES.get(dim, {})
    # Stable order by code
    return [(code, states[code]) for code in sorted(states.keys())]


def _format_prompt(dim: str) -> str:
    options = _dimension_options(dim)
    if not options:
        return "No hay opciones configuradas para esta dimensión."
    emoji = DIM_EMOJI.get(dim, "•")
    lines = [
        f"{emoji} **{dim}** — {DIM_DESCRIPTIONS.get(dim, '')}".strip(),
        "Elige con número o código:",
    ]
    for idx, (code, label) in enumerate(options, start=1):
        lines.append(f"{idx}. **{code}** — {label}")
    return "\n".join(lines)


def _record_label(dim: str, code: str) -> str:
    return GRACE_STATES.get(dim, {}).get(code, "")


def _code_index(code: str) -> int | None:
    try:
        return int(code[1]) if len(code) > 1 and code[1].isdigit() else None
    except Exception:
        return None


def _bit_for_code(code: str) -> int | None:
    idx = _code_index(code)
    if idx is None:
        return None
    if idx == 3:
        return None  # handled via collapse prompt
    return 1 if idx > 3 else 0


def _collapse_prompt(dim: str) -> str:
    emoji = DIM_EMOJI.get(dim, "•")
    return (
        f"{emoji} Tu dimensión **{dim}** está en estado Neutral.\n"
        "¿Cómo la sientes ahora?\n"
        "0) Yin — Receptiv@ / reflexiv@ / tranquil@\n"
        "1) Yang — Activ@ / expresiv@ / enérgic@\n"
        "Responde 0 o 1:"
    )


def is_owner(user):
    try:
        return str(user.id) == str(OWNER_ID)
    except Exception:
        return False


@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user} (owner={OWNER_ID}, token_source={_token_source()})")


@bot.command(name="status")
@commands.check(lambda ctx: is_owner(ctx.author))
async def status(ctx: commands.Context):
    """Owner-only: return last commit and record count."""
    commit = repo_last_commit_short() or "unknown"
    plaintext_count = _line_count(REGISTRO_PATH)
    encrypted_count = _line_count(ENCRYPTED_PATH)

    plaintext_text = "unknown" if plaintext_count is None else str(plaintext_count)
    encrypted_text = "unknown" if encrypted_count is None else str(encrypted_count)

    await ctx.reply(
        f"Last commit: {commit}\nPlaintext records: {plaintext_text}\nEncrypted records: {encrypted_text}"
    )


@bot.command(name="checkin")
@commands.check(lambda ctx: is_owner(ctx.author))
async def checkin(ctx: commands.Context):
    """Owner-only guided GRACE check-in (prefer DM for privacy)."""
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.reply("Por privacidad, te escribo por DM para el check-in.")
        dm = await ctx.author.create_dm()
        _start_session(ctx.author.id)
        await dm.send(
            "Iniciamos un check-in guiado GRACE. Responde con número o código. "
            "Usa 'cancel' para salir."
        )
        await _prompt_step(dm, ctx.author.id)
        return

    _start_session(ctx.author.id)
    await ctx.reply(
        "Iniciamos un check-in guiado GRACE. Responde con número o código. Usa 'cancel' para salir."
    )
    await _prompt_step(ctx.channel, ctx.author.id)


async def process_entry(entry_text: str, metadata: dict | None = None) -> str:
    entry_text = entry_text.strip()
    if not entry_text:
        return "Empty message; please send the text you want to save."

    script = REPO_ROOT / "grace_pipeline" / "encrypt_and_commit.py"
    if not script.exists():
        return "Pipeline script not found on host."

    cmd = [sys.executable, str(script), "--entry", entry_text]
    if metadata:
        try:
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            cmd.extend(["--metadata", metadata_json])
        except Exception:
            return "Could not serialize metadata; please try again."
    # If push is not explicitly allowed on this host, prevent committing/pushing
    if not ALLOW_PUSH:
        cmd.append("--no-commit")
    else:
        cmd.append("--push")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode(errors="ignore").strip()
        err = stderr.decode(errors="ignore").strip()
        if proc.returncode == 0:
            reply = "Entry processed successfully."
            if out:
                reply += f"\n{out}"
        else:
            reply = "Error while processing entry."
            if err:
                reply += f"\n{err}"
            elif out:
                reply += f"\n{out}"
        return reply
    except Exception as exc:
        return f"Failed to run pipeline: {exc}"


async def _prompt_step(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        session = _start_session(user_id)

    step = SESSION_STEPS[session["step_index"]]
    if step == "NOTE":
        await channel.send("📝 Nota opcional (puedes escribir cualquier cosa o enviar 'skip'):")
        return

    prompt_text = _format_prompt(step)
    session["last_options"] = _dimension_options(step)
    await channel.send(prompt_text)


async def _finalize_session(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        return
    answers = session.get("answers", {})
    bits = session.get("bits", {})
    note = session.get("note", "")

    # Build human-readable entry text
    lines = ["✨ **Check-in GRACE (Discord bot)**"]
    for dim in DIM_ORDER:
        code = answers.get(dim, "")
        label = _record_label(dim, code)
        bit = bits.get(dim)
        bit_label = "Yin (0)" if bit == 0 else "Yang (1)" if bit == 1 else ""
        suffix = f" ({bit_label})" if bit_label else ""
        emoji = DIM_EMOJI.get(dim, "•")
        lines.append(f"- {emoji} **{dim}**: {code} — {label}{suffix}")
    lines.append(f"- **Nota**: {note if note else '(sin nota)'}")
    entry_text = "\n".join(lines)

    metadata = {
        "source": "discord_bot",
        "grace": answers,
        "bits": bits,
        "note_present": bool(note.strip()),
    }

    reply = await process_entry(entry_text, metadata=metadata)
    await channel.send(reply)
    _end_session(user_id)


async def _handle_session_message(message: discord.Message):
    user_id = message.author.id
    session = _current_session(user_id)
    content = message.content.strip()

    if not session:
        session = _start_session(user_id)
        await message.channel.send(
            "Iniciamos un check-in guiado GRACE. Responde con número o código. Escribe 'cancel' para salir."
        )
        await _prompt_step(message.channel, user_id)
        return

    # If we are waiting for a neutral collapse decision
    if session.get("pending_collapse_dim"):
        dim = session["pending_collapse_dim"]
        if content in {"0", "1"}:
            session["bits"][dim] = int(content)
            session["pending_collapse_dim"] = None
            session["step_index"] += 1
            if session["step_index"] >= len(SESSION_STEPS):
                await _finalize_session(message.channel, user_id)
            else:
                await _prompt_step(message.channel, user_id)
            return
        await message.channel.send("Selecciona 0 o 1 para colapsar el estado Neutral.")
        return

    step = SESSION_STEPS[session["step_index"]]

    # Cancellation
    if content.lower() in {"cancel", "stop", "salir"}:
        _end_session(user_id)
        await message.channel.send("Sesión cancelada. Escribe cualquier cosa para iniciar de nuevo.")
        return

    if step == "NOTE":
        if content.lower() == "skip":
            session["note"] = ""
        else:
            session["note"] = content
        await _finalize_session(message.channel, user_id)
        return

    # Handle dimension selection
    options = session.get("last_options") or _dimension_options(step)
    selected_code = None

    if content.isdigit():
        idx = int(content)
        if 1 <= idx <= len(options):
            selected_code = options[idx - 1][0]
    else:
        # accept code directly
        if any(content.upper() == code for code, _ in options):
            selected_code = content.upper()

    if not selected_code:
        await message.channel.send("Respuesta no válida. Usa un número de la lista o el código exacto.")
        await _prompt_step(message.channel, user_id)
        return

    session["answers"][step] = selected_code
    bit = _bit_for_code(selected_code)
    if bit is None:
        session["pending_collapse_dim"] = step
        await message.channel.send(_collapse_prompt(step))
        return

    session["bits"][step] = bit
    session["step_index"] += 1

    if session["step_index"] >= len(SESSION_STEPS):
        await _finalize_session(message.channel, user_id)
    else:
        await _prompt_step(message.channel, user_id)


@bot.command(name="grace")
@commands.check(lambda ctx: is_owner(ctx.author))
async def grace(ctx: commands.Context, *, entry: str | None = None):
    """Owner-only command to log an entry from any channel."""
    if not entry:
        await ctx.reply("Please provide the entry text, e.g. `!grace hoy fue un buen dia`." )
        return
    reply = await process_entry(entry)
    await ctx.reply(reply)


@bot.event
async def on_message(message: discord.Message):
    # let commands run
    await bot.process_commands(message)

    # ignore bots
    if message.author.bot:
        return

    # only accept DMs from the owner for guided flow
    if not isinstance(message.channel, discord.DMChannel):
        return
    if not is_owner(message.author):
        return

    # Avoid double-handling of commands starting with !
    if message.content.strip().startswith(bot.command_prefix):
        return

    await _handle_session_message(message)


if __name__ == "__main__":
    try:
        print(f"Starting bot (owner={OWNER_ID}, token_source={_token_source()}, len={len(str(BOT_TOKEN))}, dots={str(BOT_TOKEN).count('.')})")
    except Exception:
        pass
    bot.run(BOT_TOKEN)
