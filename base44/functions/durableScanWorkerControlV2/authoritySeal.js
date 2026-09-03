const ENCODER = new TextEncoder();

export function stableSerialize(value) {
  return JSON.stringify(canonicalize(value));
}

export async function verifyAuthoritySeal(payload, secret, proof, cryptoImpl = globalThis.crypto) {
  const cleanProof = typeof proof === "string" ? proof.trim().toLowerCase() : "";
  if (!/^[a-f0-9]{64}$/.test(cleanProof)) return false;
  try {
    const key = await importHmacKey(secret, cryptoImpl, ["verify"]);
    return await cryptoImpl.subtle.verify("HMAC", key, hexToBytes(cleanProof), ENCODER.encode(stableSerialize(payload)));
  } catch {
    return false;
  }
}

function canonicalize(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (value && typeof value === "object") {
    return Object.keys(value).sort().reduce((result, key) => {
      const item = value[key];
      if (!["undefined", "function", "symbol"].includes(typeof item)) result[key] = canonicalize(item);
      return result;
    }, {});
  }
  return null;
}

async function importHmacKey(secret, cryptoImpl, usages) {
  const cleanSecret = typeof secret === "string" ? secret : "";
  if (!cleanSecret || !cryptoImpl?.subtle) throw new Error("Authority seal key is unavailable.");
  return cryptoImpl.subtle.importKey("raw", ENCODER.encode(cleanSecret), { name: "HMAC", hash: "SHA-256" }, false, usages);
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  return bytes;
}
