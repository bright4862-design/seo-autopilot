from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from flask import jsonify

from main import SIGNING_ROOT, app

RELAY_LABEL = b"fixlist-sealed-signing-key-v1"
RELAY_JWK_PATH = Path(__file__).with_name("relay_public_jwk.json")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _mgf1(seed: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(output[:length])


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _load_public_jwk() -> dict[str, str]:
    value = json.loads(RELAY_JWK_PATH.read_text(encoding="utf-8"))
    if value.get("kty") != "RSA" or not value.get("n") or not value.get("e"):
        raise RuntimeError("sealed relay public JWK is invalid")
    return value


def _rsa_oaep_sha256_encrypt(public_jwk: dict[str, str], plaintext: bytes) -> bytes:
    n = int.from_bytes(_b64url_decode(public_jwk["n"]), "big")
    e = int.from_bytes(_b64url_decode(public_jwk["e"]), "big")
    if e != 65537:
        raise RuntimeError("sealed relay RSA exponent must be 65537")

    k = (n.bit_length() + 7) // 8
    h_len = hashlib.sha256().digest_size
    if k < 256:
        raise RuntimeError("sealed relay RSA key is too small")
    if len(plaintext) > k - (2 * h_len) - 2:
        raise RuntimeError("signing key is too large for sealed relay RSA key")

    label_hash = hashlib.sha256(RELAY_LABEL).digest()
    ps = b"\x00" * (k - len(plaintext) - (2 * h_len) - 2)
    data_block = label_hash + ps + b"\x01" + plaintext
    seed = os.urandom(h_len)
    db_mask = _mgf1(seed, k - h_len - 1)
    masked_db = _xor(data_block, db_mask)
    seed_mask = _mgf1(masked_db, h_len)
    masked_seed = _xor(seed, seed_mask)
    encoded = b"\x00" + masked_seed + masked_db

    message = int.from_bytes(encoded, "big")
    if message >= n:
        raise RuntimeError("sealed relay encoded message exceeds modulus")
    ciphertext = pow(message, e, n)
    return ciphertext.to_bytes(k, "big")


@app.get("/sealed-signing-key-v1")
def sealed_signing_key_v1():
    public_jwk = _load_public_jwk()
    ciphertext = _rsa_oaep_sha256_encrypt(public_jwk, SIGNING_ROOT.encode("utf-8"))
    fingerprint_source = json.dumps(public_jwk, sort_keys=True, separators=(",", ":")).encode("utf-8")
    response = jsonify({
        "ok": True,
        "algorithm": "RSA-OAEP-SHA256",
        "label_b64": base64.b64encode(RELAY_LABEL).decode("ascii"),
        "public_jwk_sha256": hashlib.sha256(fingerprint_source).hexdigest(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    })
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
