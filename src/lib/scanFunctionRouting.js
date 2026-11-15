import contract from "../../data/base44-function-routes.json" with { type: "json" };
import stagedDeployments from "../../data/generated-staged-v9-routes.json" with { type: "json" };

const CUSTOMER_ROUTES = ["startStandardScanJob", "getCustomerScanResult", "deleteCustomerScanData"];

export function resolveScanFunctionRoute(name, previewGeneration, routes = contract) {
  const key = CUSTOMER_ROUTES.find((canonical) => name === `${canonical}V8`);
  if (!key) return name;
  const stagedPreview = previewGeneration === "V9" && routes.generation === "v8";
  const selected = (stagedPreview ? routes.candidate_routes.v9 : routes.routes)[key];
  if (!stagedPreview && routes.generation !== "v9") return selected;
  const deployment = stagedDeployments.functions[selected];
  if (!deployment) throw new Error("The staged scanner route is unavailable.");
  return deployment.route_name;
}
