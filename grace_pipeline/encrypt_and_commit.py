#!/usr/bin/env python3
"""Encrypt plaintext entries, append them to the journal, and record the change in git."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import subprocess
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from encryption_rust import encrypt, generate_key
except ImportError as exc:  # pragma: no cover
    raise SystemExit("encryption_rust module is not available. Run maturin develop first.") from exc

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "encryption" / "encryption_config.json"


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def resolve_path(repo_root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def is_valid_key(value: str) -> bool:
    try:
        decoded = base64.b64decode(value, validate=True)
    except binascii.Error:
        return False
    return len(decoded) == 32


def get_env_key(env_var: str | None) -> str | None:
    if not env_var:
        return None
    value = os.getenv(env_var)
    if not value:
        return None
    candidate = value.strip()
    if not is_valid_key(candidate):
        raise ValueError(
            f"Environment variable {env_var} does not contain a valid base64-encoded 256-bit key."
        )
    return candidate


def check_git_untracked(repo_root: Path, key_path: Path) -> None:
    try:
        rel_path = key_path.relative_to(repo_root)
    except ValueError:
        return
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(rel_path)],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return
    if result.returncode == 0:
        raise RuntimeError(
            f"Key file {rel_path} is tracked by git. Remove it from version control to protect the secret."
        )


def ensure_secret_key(key_path: Path, env_var: str | None, repo_root: Path) -> str:
    env_value = get_env_key(env_var)
    if env_value:
        return env_value
    if key_path.is_file():
        value = key_path.read_text(encoding="utf-8").strip()
        if value and is_valid_key(value):
            check_git_untracked(repo_root, key_path)
            return value
        if value:
            print("Existing key was invalid; generating a replacement.", file=sys.stderr)
    key_value = generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key_value + "\n", encoding="utf-8")
    try:
        os.chmod(key_path, 0o600)
    except PermissionError:
        pass
    check_git_untracked(repo_root, key_path)
    return key_value


def load_plaintext(args: argparse.Namespace) -> str:
    if args.entry:
        return args.entry.strip()
    if args.from_file:
        content = Path(args.from_file).read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError("Source file is empty; nothing to encrypt.")
        return content
    if not sys.stdin.isatty():
        content = sys.stdin.read().strip()
        if content:
            return content
    print("Enter your entry. Submit an empty line to finish:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    plaintext = "\n".join(lines).strip()
    if not plaintext:
        raise ValueError("No plaintext provided.")
    return plaintext


def load_metadata(args: argparse.Namespace, defaults: Dict[str, Any]) -> Dict[str, Any]:
    metadata = deepcopy(defaults)
    if args.metadata:
        candidate = Path(args.metadata)
        if candidate.is_file():
            with candidate.open("r", encoding="utf-8") as handle:
                supplied = json.load(handle)
        else:
            supplied = json.loads(args.metadata)
        if not isinstance(supplied, dict):
            raise ValueError("Metadata must be a JSON object.")
        metadata.update(supplied)
    if args.tags:
        metadata["tags"] = args.tags
    if args.label:
        metadata["label"] = args.label
    return metadata


def append_entry(file_path: Path, record: Dict[str, Any], dry_run: bool) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    if dry_run:
        print(line)
        return
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def append_plaintext_entry(
    file_path: Path,
    entry_id: str,
    timestamp: str,
    plaintext: str,
    metadata: Dict[str, Any],
    dry_run: bool,
) -> None:
    """Store a human-readable entry locally (never added to git)."""
    record = {
        "schema_version": 1,
        "entry_id": entry_id,
        "timestamp": timestamp,
        "text": plaintext,
        "metadata": metadata,
    }
    append_entry(file_path, record, dry_run)


def run_git(
    repo_root: Path,
    data_path: Path,
    message: str,
    commit: bool,
    push: bool,
    push_remote: str | None = None,
    push_branch: str | None = None,
) -> None:
    relative = str(data_path.relative_to(repo_root))
    subprocess.run(["git", "add", relative], cwd=repo_root, check=True)
    if not commit:
        return
    commit_proc = subprocess.run(["git", "commit", "-m", message], cwd=repo_root)
    if commit_proc.returncode != 0:
        raise RuntimeError("git commit failed")
    if push:
        cmd = ["git", "push"]
        if push_remote:
            cmd.append(push_remote)
        if push_branch:
            cmd.append(push_branch)
        push_proc = subprocess.run(cmd, cwd=repo_root)
        if push_proc.returncode != 0:
            raise RuntimeError("git push failed")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Encrypt and store personal entries.")
    parser.add_argument("--entry", "-e", help="Plaintext entry to encrypt.")
    parser.add_argument("--from-file", type=str, help="Path to a file with the plaintext entry.")
    parser.add_argument("--metadata", help="Metadata as JSON string or path to JSON file.")
    parser.add_argument("--label", help="Override metadata label for this entry.")
    parser.add_argument("--tags", nargs="*", help="Optional tags for this entry.")
    parser.add_argument("--key-path", help="Override key path from config.")
    parser.add_argument(
        "--key-env-var",
        help="Environment variable containing the base64-encoded symmetric key.",
    )
    parser.add_argument(
        "--plaintext-path",
        help="Optional human-readable journal path; keeps a local copy outside git.",
    )
    parser.add_argument("--no-commit", action="store_true", help="Skip git commit step.")
    parser.add_argument("--push", action="store_true", help="Push to remote after committing.")
    parser.add_argument("--push-remote", help="Remote name to push to (e.g., 'origin').")
    parser.add_argument("--push-branch", help="Branch name to push (e.g., 'prepare-to-collaborate').")
    parser.add_argument("--commit-message", help="Custom commit message.")
    parser.add_argument("--entry-id", help="Explicit entry identifier.")
    parser.add_argument("--dry-run", action="store_true", help="Show the output without writing or committing.")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = load_config()
    repo_root = resolve_path(SCRIPT_DIR.parent, config.get("git_repo_root", "."))
    data_path = resolve_path(repo_root, config["data_path"])
    plaintext_cfg = args.plaintext_path or config.get("plaintext_path")
    plaintext_path = resolve_path(repo_root, plaintext_cfg) if plaintext_cfg else None
    key_path = resolve_path(repo_root, args.key_path or config["key_path"])
    metadata_defaults = config.get("default_metadata") or {}
    if not isinstance(metadata_defaults, dict):
        raise ValueError("default_metadata must be an object in the config file.")

    plaintext = load_plaintext(args)
    env_var_name = args.key_env_var or config.get("key_env_var")
    try:
        key_value = ensure_secret_key(key_path, env_var_name, repo_root)
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error
    ciphertext, nonce = encrypt(plaintext, key_value, None)

    entry_id = args.entry_id or uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = load_metadata(args, metadata_defaults)

    record = {
        "schema_version": 1,
        "entry_id": entry_id,
        "timestamp": timestamp,
        "ciphertext": ciphertext,
        "nonce": nonce,
        "key_label": config.get("key_label", "primary"),
        "metadata": metadata,
    }

    append_entry(data_path, record, args.dry_run)

    if plaintext_path:
        append_plaintext_entry(plaintext_path, entry_id, timestamp, plaintext, metadata, args.dry_run)

    if args.dry_run:
        print("Dry run complete; skipping git operations.")
        return

    commit_message = args.commit_message or f"Encrypted entry {timestamp}"
    # Allow environment-defined push targets
    env_push_remote = os.getenv("GRACE_GIT_REMOTE")
    env_push_branch = os.getenv("GRACE_GIT_BRANCH")
    push_remote = args.push_remote or env_push_remote
    push_branch = args.push_branch or env_push_branch

    try:
        run_git(
            repo_root,
            data_path,
            commit_message,
            not args.no_commit,
            args.push,
            push_remote=push_remote,
            push_branch=push_branch,
        )
    except (subprocess.CalledProcessError, RuntimeError) as error:
        raise SystemExit(f"Git operation failed: {error}") from error

    print(f"Entry {entry_id} stored and encrypted.")


if __name__ == "__main__":
    main()
