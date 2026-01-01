#![allow(unsafe_op_in_unsafe_fn)]

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use std::convert::TryInto;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyModule;
use pyo3::Bound;
use rand::rngs::OsRng;
use rand::RngCore;

const KEY_BYTES: usize = 32;
const NONCE_BYTES: usize = 12;

fn decode_fixed<const N: usize>(label: &str, value: &str) -> PyResult<[u8; N]> {
    let decoded = BASE64
        .decode(value)
        .map_err(|err| PyValueError::new_err(format!("invalid base64 for {label}: {err}")))?;
    if decoded.len() != N {
        return Err(PyValueError::new_err(format!(
            "{label} must decode to {N} bytes, got {}",
            decoded.len()
        )));
    }
    decoded
        .try_into()
        .map_err(|_| PyValueError::new_err(format!("failed to convert {label} into fixed-size array")))
}

fn decode_vec(label: &str, value: &str) -> PyResult<Vec<u8>> {
    BASE64
        .decode(value)
        .map_err(|err| PyValueError::new_err(format!("invalid base64 for {label}: {err}")))
}

#[pyfunction]
fn generate_key() -> PyResult<String> {
    let mut key = [0u8; KEY_BYTES];
    OsRng.fill_bytes(&mut key);
    Ok(BASE64.encode(key))
}

#[pyfunction]
fn generate_nonce() -> PyResult<String> {
    let mut nonce = [0u8; NONCE_BYTES];
    OsRng.fill_bytes(&mut nonce);
    Ok(BASE64.encode(nonce))
}

#[pyfunction(signature = (plaintext, key_b64, nonce_b64=None))]
fn encrypt(plaintext: &str, key_b64: &str, nonce_b64: Option<&str>) -> PyResult<(String, String)> {
    let key = decode_fixed::<KEY_BYTES>("key", key_b64)?;
    let nonce_bytes = match nonce_b64 {
        Some(value) => decode_fixed::<NONCE_BYTES>("nonce", value)?,
        None => {
            let mut generated = [0u8; NONCE_BYTES];
            OsRng.fill_bytes(&mut generated);
            generated
        }
    };
    let cipher = Aes256Gcm::new_from_slice(&key)
        .map_err(|_| PyValueError::new_err("invalid key length"))?;
    let nonce = Nonce::from_slice(&nonce_bytes);
    let ciphertext = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|_| PyValueError::new_err("encryption failed"))?;
    let ciphertext_b64 = BASE64.encode(ciphertext);
    let nonce_b64_out = BASE64.encode(nonce_bytes);
    Ok((ciphertext_b64, nonce_b64_out))
}

#[pyfunction]
fn decrypt(ciphertext_b64: &str, key_b64: &str, nonce_b64: &str) -> PyResult<String> {
    let key = decode_fixed::<KEY_BYTES>("key", key_b64)?;
    let nonce = decode_fixed::<NONCE_BYTES>("nonce", nonce_b64)?;
    let ciphertext = decode_vec("ciphertext", ciphertext_b64)?;
    let cipher = Aes256Gcm::new_from_slice(&key)
        .map_err(|_| PyValueError::new_err("invalid key length"))?;
    let nonce = Nonce::from_slice(&nonce);
    let plaintext = cipher
        .decrypt(nonce, ciphertext.as_ref())
        .map_err(|_| PyValueError::new_err("decryption failed"))?;
    String::from_utf8(plaintext).map_err(|_| PyValueError::new_err("plaintext is not valid UTF-8"))
}

#[pymodule]
fn encryption_rust(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(generate_key, module)?)?;
    module.add_function(wrap_pyfunction!(generate_nonce, module)?)?;
    module.add_function(wrap_pyfunction!(encrypt, module)?)?;
    module.add_function(wrap_pyfunction!(decrypt, module)?)?;
    module.add("KEY_LENGTH", KEY_BYTES)?;
    module.add("NONCE_LENGTH", NONCE_BYTES)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add("__doc__", "AES-256-GCM helpers exposed to Python via PyO3")?;
    module.add("RUST_RELEASE", option_env!("PROFILE").unwrap_or("unknown"))?;
    let _ = py;
    Ok(())
}

