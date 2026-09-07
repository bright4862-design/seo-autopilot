const ENCODER = new TextEncoder();

export const AUTHORITY_SEAL_VERSION = "scan_evidence_hmac_sha256_v1";

export function stableSerialize(value) {
  return JSON.stringify(canonicalize(value));
}

export async function createAuthoritySeal(payload, secret, cryptoImpl = globalThis.crypto) {
  const key = await importHmacKey(secret, cryptoImpl, ["sign"]);
  const signature = await cryptoImpl.subtle.sign("HMAC", key, ENCODER.encode(stableSerialize(payload)));
  return bytesToHex(new Uint8Array(signature));
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

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  return bytes;
}
