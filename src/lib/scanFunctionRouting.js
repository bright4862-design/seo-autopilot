import contract from "../../data/base44-function-routes.json" with { type: "json" };
import stagedDeployments from "../../data/generated-staged-v9-routes.json" with { type: "json" };

const CUSTOMER_ROUTES = ["startStandardScanJob", "getCustomerScanResult", "deleteCustomerScanData"];

export function resolveScanFunctionRoute(name, previewGeneration, routes = contract) {
  const key = CUSTOMER_ROUTES.find((canonical) => name === `${canonical}V8`);
  if (!key) return name;
  const pilotReader = previewGeneration === "PUBLISHED_PILOT" && key !== "startStandardScanJob";
  const stagedPreview = (previewGeneration === "V9" || pilotReader) && routes.generation === "v8";
  const selected = (stagedPreview ? routes.candidate_routes.v9 : routes.routes)[key];
  if (!stagedPreview && routes.generation !== "v9") return selected;
  const deployment = stagedDeployments.functions[selected];
  if (!deployment) throw new Error("The staged scanner route is unavailable.");
  return deployment.route_name;
}

export function parsePublishedScanOptions(body, expectedFingerprint) {
  if (body?.success !== true || body.version !== "published_scan_options_v1"
      || body.release_fingerprint !== expectedFingerprint) {
    throw new Error("The scan options could not be verified.");
  }
  if (body.launch === "legacy" && body.page_cap === 150) {
    return { pageCap: 150, pilot: false };
  }
  if (body.launch === "pilot" && [150, 500].includes(body.page_cap)) {
    return { pageCap: body.page_cap, pilot: true };
  }
  if (body.launch === "paused" && body.page_cap === null) {
    throw new Error("Your pilot scans are paused.");
  }
  throw new Error("The scan options could not be verified.");
}
