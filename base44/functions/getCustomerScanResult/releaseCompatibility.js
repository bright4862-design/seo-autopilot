// Historical result compatibility is intentionally narrower than release acceptance.
// A fingerprint listed here may be READ only after its original HMAC authority
// proof, ownership, FixList identity, FixItem identity, and completeness checks
// all pass. It is never treated as evidence that the old release is currently
// deployed or accepted.
export const CUSTOMER_RESULT_READER_VERSION = "customer_result_reader_v3_p1b_historical_compatibility";

export const HISTORICAL_READABLE_RELEASE_FINGERPRINTS = Object.freeze([
  "5d94e93c54a9efb6",
  "7a95768cc8ee2076",
]);

export function isReadableAuthorityReleaseFingerprint(value, currentReleaseFingerprint) {
  const fingerprint = String(value || "").trim().toLowerCase();
  const current = String(currentReleaseFingerprint || "").trim().toLowerCase();
  if (!/^[0-9a-f]{16}$/.test(fingerprint) || !/^[0-9a-f]{16}$/.test(current)) return false;
  return fingerprint === current || HISTORICAL_READABLE_RELEASE_FINGERPRINTS.includes(fingerprint);
}
