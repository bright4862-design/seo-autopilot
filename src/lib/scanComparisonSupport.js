const SUPPORT_REFERENCES = new Set([
  "CMP-ACCESS", "CMP-CURRENT", "CMP-PREVIOUS", "CMP-SCOPE", "CMP-CONFIG",
  "CMP-TIMEOUT", "CMP-NETWORK", "CMP-GATEWAY-AUTH", "CMP-GATEWAY-ROUTE",
  "CMP-GATEWAY-LIMIT", "CMP-GATEWAY-BUSY", "CMP-GATEWAY-ERROR", "CMP-GATEWAY-INPUT",
  "CMP-RESPONSE", "CMP-REQUEST",
]);

// A reference describes a failed boundary, never a scan, URL, proof or exception.
export function scanComparisonSupportReference(value) {
  return typeof value === "string" && SUPPORT_REFERENCES.has(value) ? value : "";
}
