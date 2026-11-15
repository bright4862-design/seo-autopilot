import contract from "../../data/base44-function-routes.json" with { type: "json" };

const CUSTOMER_ROUTES = ["startStandardScanJob", "getCustomerScanResult", "deleteCustomerScanData"];

export function resolveScanFunctionRoute(name, previewGeneration, routes = contract) {
  const selected = previewGeneration === "V9" && routes.generation === "v8"
    ? routes.candidate_routes.v9
    : routes.routes;
  const key = CUSTOMER_ROUTES.find((canonical) => name === `${canonical}V8`);
  return key ? selected[key] : name;
}
