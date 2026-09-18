// Historical result compatibility is intentionally narrower than release acceptance.
// A fingerprint listed here may be READ only after its original HMAC authority
// proof, ownership, FixList identity, FixItem identity, and completeness checks
// all pass. It is never treated as evidence that the old release is currently
// deployed or accepted.
export const CUSTOMER_RESULT_READER_VERSION = "customer_result_reader_v7_signed_preview_authority";

export const HISTORICAL_READABLE_RELEASE_FINGERPRINTS = Object.freeze([
  "9e4901da590017e1",
  "a511d61013ef9fe3",
  "c73399086107cbaf",
  "5d94e93c54a9efb6",
  "7a95768cc8ee2076",
  "0fa7d98734efb3f2",
]);

export function isReadableAuthorityReleaseFingerprint(value, currentReleaseFingerprint) {
  const fingerprint = String(value || "").trim().toLowerCase();
  const current = String(currentReleaseFingerprint || "").trim().toLowerCase();
  if (!/^[0-9a-f]{16}$/.test(fingerprint) || !/^[0-9a-f]{16}$/.test(current)) return false;
  return fingerprint === current || HISTORICAL_READABLE_RELEASE_FINGERPRINTS.includes(fingerprint);
}
