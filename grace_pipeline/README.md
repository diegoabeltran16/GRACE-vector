# GRACE Pipeline Automation

This folder contains the tooling that encrypts personal journal entries and records them transparently in the repository while keeping the contents private.

## Components
- `encrypt_and_commit.py` – CLI utility that collects a plaintext entry, encrypts it with AES-256-GCM (via the Rust module), appends the ciphertext to `data/registros/registro.jsonl`, and optionally performs git commits/pushes.
- `encryption/` – Holds local-only secrets plus the Rust bindings. See `encryption/README.md` for secure key-management practices.

## Prerequisites
1. Install the Rust-based extension into the Python virtual environment:
   ```powershell
   cd C:\Users\Ohana\Documents\Repositorios\GRACE-vector\grace_pipeline\encryption\encryption_rust
   C:\Users\Ohana\Documents\Repositorios\GRACE-vector\venv\Scripts\python.exe -m maturin develop --release
   ```
2. Set the AES key via the `GRACE_ENCRYPTION_KEY` environment variable (recommended) or store it in `grace_pipeline/encryption/private_key.pem`. Never track the key in git.

## Usage
Run the CLI from the repository root (virtualenv activated):
```powershell
C:\Users\Ohana\Documents\Repositorios\GRACE-vector\venv\Scripts\python.exe grace_pipeline\encrypt_and_commit.py --entry "Mensaje confidencial"
```

### Common Options
- `--dry-run` – Show the encrypted record without writing or committing.
- `--metadata '{"mood":"calm"}'` – Attach additional JSON metadata.
- `--tags foco energia` – Add simple tag list.
- `--no-commit` – Skip the git commit step (still stages the file).
- `--push` – Push to the remote once the commit succeeds.
- `--commit-message "GRACE entry"` – Custom git message.

### Example: Encrypting from a file
```powershell
C:\Users\Ohana\Documents\Repositorios\GRACE-vector\venv\Scripts\python.exe grace_pipeline\encrypt_and_commit.py --from-file notes.txt --tags diario proyectos
```

### Decrypting Entries
Use the Rust module directly when you need to inspect an entry:
```python
from encryption_rust import decrypt
ciphertext = "..."
nonce = "..."
key = "..."  # same base64 string used for encryption
decrypted = decrypt(ciphertext, key, nonce)
```
Remember that the key must remain secret; never paste it into version-controlled files.

## Git Safety
The script aborts if it detects the key file is tracked by git. Ensure `.gitignore` contains the paths listed in the root configuration and verify with:
```powershell
git status
```

Keeping these guardrails in place ensures the GRACE entries remain private while the repository history shows consistent activity.

For deployment-specific bot safeguards (wake‑word and commit authorization), see the deploy README: [deploy/README.md](deploy/README.md).
