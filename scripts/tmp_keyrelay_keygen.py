from pathlib import Path
import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

root = Path('/app/.tmp-fixlist-key-sync')
root.mkdir(mode=0o700, parents=True, exist_ok=True)
private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
private_bytes = private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
public_bytes = private.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)
(root / 'private.pem').write_bytes(private_bytes)
(root / 'public.pem').write_bytes(public_bytes)
os.chmod(root / 'private.pem', 0o600)
os.chmod(root / 'public.pem', 0o644)
print(public_bytes.decode('ascii'), end='')
