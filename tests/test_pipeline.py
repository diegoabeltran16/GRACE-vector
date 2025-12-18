import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from encryption_rust import decrypt, generate_key


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE = PROJECT_ROOT / "grace_pipeline" / "encrypt_and_commit.py"


def setup_temp_repo(tmp_path: Path, *, config_key_env: str | None) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    grace_dir = repo_root / "grace_pipeline" / "encryption"
    grace_dir.mkdir(parents=True)

    encrypted_dir = repo_root / "data_encr"
    encrypted_dir.mkdir(parents=True)
    encrypted_path = encrypted_dir / "registro_encr.jsonl"
    encrypted_path.write_text("", encoding="utf-8")

    plaintext_dir = repo_root / "data" / "registros"
    plaintext_dir.mkdir(parents=True)
    plaintext_path = plaintext_dir / "registro.jsonl"
    plaintext_path.write_text("", encoding="utf-8")

    config: dict[str, object] = {
        "key_path": "grace_pipeline/encryption/private_key.pem",
        "data_path": "data_encr/registro_encr.jsonl",
        "plaintext_path": "data/registros/registro.jsonl",
        "git_repo_root": ".",
        "key_label": "primary",
        "default_metadata": {"source": "test-suite"},
    }
    if config_key_env:
        config["key_env_var"] = config_key_env

    config_path = grace_dir / "encryption_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    script_dest = repo_root / "grace_pipeline" / "encrypt_and_commit.py"
    shutil.copyfile(SCRIPT_SOURCE, script_dest)

    subprocess.run(["git", "init"], cwd=repo_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return repo_root, encrypted_path, plaintext_path, script_dest


@pytest.mark.skipif(not SCRIPT_SOURCE.exists(), reason="Encryption pipeline script missing")
def test_encrypt_and_decrypt_roundtrip(tmp_path: Path) -> None:
    env_key_name = "GRACE_ENCRYPTION_KEY_TEST"
    repo_root, encrypted_path, plaintext_path, script_path = setup_temp_repo(tmp_path, config_key_env=env_key_name)

    key_b64 = generate_key()
    env = os.environ.copy()
    env[env_key_name] = key_b64

    cmd = [
        sys.executable,
        str(script_path),
        "--entry",
        "Mensaje secreto",
        "--key-env-var",
        env_key_name,
        "--no-commit",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    encrypted_content = [line for line in encrypted_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(encrypted_content) == 1

    record = json.loads(encrypted_content[0])
    assert record["schema_version"] == 1
    assert record["key_label"] == "primary"
    assert record["metadata"]["source"] == "test-suite"

    plaintext = decrypt(record["ciphertext"], key_b64, record["nonce"])
    assert plaintext == "Mensaje secreto"

    plaintext_content = [line for line in plaintext_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(plaintext_content) == 1

    plaintext_record = json.loads(plaintext_content[0])
    assert plaintext_record["text"] == "Mensaje secreto"
    assert plaintext_record["entry_id"] == record["entry_id"]


def test_key_file_generated_and_not_tracked(tmp_path: Path) -> None:
    repo_root, encrypted_path, plaintext_path, script_path = setup_temp_repo(tmp_path, config_key_env=None)

    cmd = [
        sys.executable,
        str(script_path),
        "--entry",
        "Primera entrada",
        "--dry-run",
        "--no-commit",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    key_path = repo_root / "grace_pipeline" / "encryption" / "private_key.pem"
    key_value = key_path.read_text(encoding="utf-8").strip()
    assert len(key_value) > 0
    decoded = base64.b64decode(key_value)
    assert len(decoded) == 32

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "grace_pipeline/encryption/private_key.pem"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0, "Key file should remain untracked by git"

    assert encrypted_path.read_text(encoding="utf-8").strip() == ""
    assert plaintext_path.read_text(encoding="utf-8").strip() == ""