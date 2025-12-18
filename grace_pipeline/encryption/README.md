# GRACE Encryption Secrets

This directory stores local materials required to encrypt personal entries. Keep these notes in mind:

- The symmetric key **must remain secret**. Prefer supplying it via the environment variable `GRACE_ENCRYPTION_KEY`. Set it in PowerShell with:
  ```powershell
  $key = Get-Content grace_pipeline\encryption\private_key.pem -Raw
  setx GRACE_ENCRYPTION_KEY $key
  ```
  After setting it, restart your terminal so the new value is available.
- If you rely on the key file located at `grace_pipeline/encryption/private_key.pem`, ensure it never becomes tracked by git. The automation script checks this and aborts when the file is staged or committed.
- Rotate the key by deleting the current file (or clearing the environment variable) and running the pipeline again. Back up any historic key material securely before rotating, otherwise old entries cannot be decrypted.
- Store backups in an encrypted password manager or hardware token—*never* upload them to the repository or any shared drive.

Following these steps keeps the GRACE vector journal encrypted end to end while maintaining local usability.
