import os
import re
import sys
import json
import time
import asyncio
import secrets
import subprocess
from pathlib import Path

import discord
from discord.ext import commands

try:  # Local execution fallback
    from . import git_sync  # type: ignore
except ImportError:  # pragma: no cover
    import git_sync  # type: ignore


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
WAKE_KEYWORD = os.environ.get("GRACE_WAKE_KEYWORD", "hola bot").strip() or "hola bot"
WAKE_TIMEOUT_SECONDS = int(os.environ.get("GRACE_WAKE_TIMEOUT", "900"))  # default 15 min
COMMIT_CODE_PREFIX = os.environ.get("GRACE_COMMIT_CODE_PREFIX", "GRACE").strip() or "GRACE"
REQUIRE_PASSPHRASE = os.environ.get("GRACE_REQUIRE_PASSPHRASE", "1") != "0"

# Session management for guided check-ins
DIM_ORDER = ["G", "R", "A", "C", "E"]
SESSION_STEPS = DIM_ORDER + ["NOTE"]
SESSIONS: dict[int, dict] = {}
AWAKE_USERS: dict[int, float] = {}
WAKE_KEYWORD_NORMALIZED = None

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


def _normalize_wake_text(value: str) -> str:
    lowered = value.strip().lower()
    collapsed = " ".join(lowered.split())
    sanitized = re.sub(r"[!¡¿?.,;:()\[\]\-_*`'\"]", "", collapsed)
    return sanitized


WAKE_KEYWORD_NORMALIZED = _normalize_wake_text(WAKE_KEYWORD)


def _wake_word_triggered(message_text: str) -> bool:
    normalized = _normalize_wake_text(message_text)
    if not normalized:
        return False
    return normalized == WAKE_KEYWORD_NORMALIZED or WAKE_KEYWORD_NORMALIZED in normalized


def _passphrase_required() -> bool:
    return ALLOW_PUSH and REQUIRE_PASSPHRASE


def _start_session(user_id: int) -> dict:
    session = {
        "step_index": 0,
        "answers": {},
        "bits": {},
        "note": "",
        "last_options": None,
        "pending_collapse_dim": None,
        "awaiting_commit_code": False,
        "commit_code": None,
        "commit_authorized": False,
        "awaiting_passphrase": False,
        "deploy_passphrase": None,
        "prompts_started": False,
        "sync_attempted": False,
        "sync_success": None,
        "sync_output": None,
    }
    SESSIONS[user_id] = session
    return session


def _end_session(user_id: int):
    SESSIONS.pop(user_id, None)


def _current_session(user_id: int) -> dict | None:
    return SESSIONS.get(user_id)


def _activate_user(user_id: int) -> None:
    expires = time.monotonic() + WAKE_TIMEOUT_SECONDS
    AWAKE_USERS[user_id] = expires


def _is_user_awake(user_id: int) -> bool:
    expires = AWAKE_USERS.get(user_id)
    if not expires:
        return False
    if time.monotonic() > expires:
        AWAKE_USERS.pop(user_id, None)
        return False
    return True


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


def _ensure_owner_awake(ctx: commands.Context) -> bool:
    if not is_owner(ctx.author):
        raise commands.CheckFailure("Solo la persona propietaria puede usar este bot.")
    if not _is_user_awake(ctx.author.id):
        raise commands.CheckFailure(
            f"Bot inactivo. Envía '{WAKE_KEYWORD}' por DM para activarlo durante unos minutos."
        )
    _activate_user(ctx.author.id)
    return True


@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user} (owner={OWNER_ID}, token_source={_token_source()})")


@bot.command(name="status")
@commands.check(_ensure_owner_awake)
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
@commands.check(_ensure_owner_awake)
async def checkin(ctx: commands.Context):
    """Owner-only guided GRACE check-in (prefer DM for privacy)."""
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.reply("Por privacidad, te escribo por DM para el check-in.")
        dm = await ctx.author.create_dm()
        await _begin_checkin_conversation(dm, ctx.author.id)
        return

    await _begin_checkin_conversation(ctx.channel, ctx.author.id)


async def process_entry(
    entry_text: str,
    metadata: dict | None = None,
    allow_commit: bool = False,
    deploy_passphrase: str | None = None,
) -> str:
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
    commit_allowed = allow_commit and ALLOW_PUSH
    if commit_allowed:
        cmd.append("--push")
    else:
        cmd.append("--no-commit")

    env = os.environ.copy()
    if allow_commit and deploy_passphrase:
        env["GRACE_DEPLOY_KEY_PASSPHRASE"] = deploy_passphrase

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
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
        if allow_commit and not ALLOW_PUSH:
            reply += "\nCommit/push no habilitado en este host (GRACE_ALLOW_PUSH!=1)."
        return reply
    except Exception as exc:
        return f"Failed to run pipeline: {exc}"


async def _prompt_step(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        await channel.send(
            "No hay una sesión activa. Escribe cualquier mensaje para iniciar un nuevo check-in."
        )
        return

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

    deploy_passphrase = session.pop("deploy_passphrase", None)
    if not session.get("commit_authorized"):
        deploy_passphrase = None

    reply = await process_entry(
        entry_text,
        metadata=metadata,
        allow_commit=session.get("commit_authorized", False),
        deploy_passphrase=deploy_passphrase,
    )
    await channel.send(reply)
    _end_session(user_id)


def _generate_commit_code() -> str:
    return f"{COMMIT_CODE_PREFIX}-{secrets.token_hex(3).upper()}"


async def _begin_checkin_conversation(channel: discord.abc.Messageable, user_id: int):
    _start_session(user_id)
    await channel.send(
        "Iniciamos un check-in guiado GRACE. Responde con número o código y usa 'cancel' para salir.\n"
        "Antes de las preguntas necesito una clave temporal para sincronizar el repositorio y permitir commit/push."
    )
    await _prompt_commit_code(channel, user_id)


async def _prompt_commit_code(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        return
    code = _generate_commit_code()
    session["commit_code"] = code
    session["awaiting_commit_code"] = True
    session["commit_authorized"] = False
    await channel.send(
        "Para autorizar commit y push, responde con la clave mostrada a continuación.\n"
        f"`{code}`\n"
        "Si prefieres guardar sin commit/push, responde `skip`."
    )


async def _start_prompts(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        return
    if not session.get("prompts_started"):
        session["prompts_started"] = True
    await _prompt_step(channel, user_id)


async def _sync_repo_before_prompts(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session:
        return
    if session.get("sync_attempted"):
        await _start_prompts(channel, user_id)
        return
    await channel.send("Sincronizando repositorio con origin antes de continuar...")
    passphrase = session.get("deploy_passphrase")

    def _pull():
        env = {}
        if passphrase:
            env["GRACE_DEPLOY_KEY_PASSPHRASE"] = passphrase
        return git_sync.sync_repository(REPO_ROOT, env_overrides=env)

    loop = asyncio.get_running_loop()
    success, output = await loop.run_in_executor(None, _pull)
    session["sync_attempted"] = True
    session["sync_success"] = success
    session["sync_output"] = output
    status = "✅ Pull completado" if success else "❌ Pull con errores"
    await channel.send(f"{status}:\n```\n{output}\n```")
    if not success:
        session["commit_authorized"] = False
        session["deploy_passphrase"] = None
        await channel.send(
            "Continuaré sin commit/push hasta que sincronices manualmente el repositorio en el servidor."
        )
    await _start_prompts(channel, user_id)


async def _after_authorization(channel: discord.abc.Messageable, user_id: int):
    session = _current_session(user_id)
    if not session or session.get("prompts_started"):
        return
    if session.get("commit_authorized"):
        await _sync_repo_before_prompts(channel, user_id)
    else:
        await _start_prompts(channel, user_id)


async def _handle_session_message(message: discord.Message):
    user_id = message.author.id
    session = _current_session(user_id)
    content = message.content.strip()
    _activate_user(user_id)

    if session and session.get("awaiting_commit_code"):
        if content.lower() == "skip":
            session["commit_authorized"] = False
            session["awaiting_commit_code"] = False
            await message.channel.send("Continuaré sin commit/push para esta sesión.")
            await _after_authorization(message.channel, user_id)
            return
        if session.get("commit_code") and content.strip().upper() == session["commit_code"].upper():
            session["commit_authorized"] = True
            session["awaiting_commit_code"] = False
            if _passphrase_required():
                session["awaiting_passphrase"] = True
                await message.channel.send(
                    "Clave aceptada. Envía la frase de paso del deploy key o escribe 'skip' para guardar sin push."
                )
                return
            await _after_authorization(message.channel, user_id)
            return
        await message.channel.send("Clave incorrecta. Copia el código exacto o escribe 'skip'.")
        return

    if session and session.get("awaiting_passphrase"):
        if content.lower() == "skip":
            session["deploy_passphrase"] = None
            session["commit_authorized"] = False
            session["awaiting_passphrase"] = False
            await message.channel.send("Se guardará sin commit/push en esta sesión.")
            await _after_authorization(message.channel, user_id)
            return
        session["deploy_passphrase"] = content
        session["awaiting_passphrase"] = False
        await _after_authorization(message.channel, user_id)
        return

    if not session:
        await _begin_checkin_conversation(message.channel, user_id)
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
        session["note"] = "" if content.lower() == "skip" else content
        session["step_index"] = len(SESSION_STEPS)
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
@commands.check(_ensure_owner_awake)
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

    normalized = message.content.strip().lower()
    if _wake_word_triggered(message.content):
        _activate_user(message.author.id)
        await message.channel.send(
            "Bot activado. Dispones de algunos minutos para enviar comandos o completar el check-in."
        )
        return

    if not _is_user_awake(message.author.id):
        await message.channel.send(
            f"El bot está dormido. Envía '{WAKE_KEYWORD}' para activarlo temporalmente."
        )
        return

    # Avoid double-handling of commands starting with !
    if message.content.strip().startswith(bot.command_prefix):
        return

    await _handle_session_message(message)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        try:
            await ctx.reply(str(error))
        except Exception:
            pass
        return
    raise error


if __name__ == "__main__":
    try:
        print(f"Starting bot (owner={OWNER_ID}, token_source={_token_source()}, len={len(str(BOT_TOKEN))}, dots={str(BOT_TOKEN).count('.')})")
    except Exception:
        pass
    bot.run(BOT_TOKEN)
