from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Tuple

try:
    from . import encrypt_and_commit as pipeline  # type: ignore
except ImportError:  # pragma: no cover - fallback when running as script
    import encrypt_and_commit as pipeline  # type: ignore

DEFAULT_BRANCH = os.environ.get(
    "GRACE_SYNC_BRANCH",
    os.environ.get("GRACE_DEFAULT_BRANCH", "prepare-to-collaborate"),
)


def sync_repository(
    repo_root: Path,
    branch: str | None = None,
    env_overrides: dict[str, str] | None = None,
) -> Tuple[bool, str]:
    """Run a git pull --ff-only on the target branch and return (success, output)."""
    branch_name = branch or DEFAULT_BRANCH
    git_env, cleanup = pipeline._prepare_git_env()
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    if git_env:
        env.update(git_env)
    try:
        cmd = ["git", "pull", "--ff-only", "origin", branch_name]
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
        )
        ok = proc.returncode == 0
        fragments = [frag.strip() for frag in (proc.stdout, proc.stderr) if frag and frag.strip()]
        output = "\n".join(fragments).strip()
        if not output:
            output = "git pull completed." if ok else "git pull failed without output."
        return ok, output
    finally:
        if cleanup:
            cleanup()
