const V9_ROUTES = Object.freeze({
  startStandardScanJobV8: "startStandardScanJobV9",
  getCustomerScanResultV8: "getCustomerScanResultV9",
  deleteCustomerScanDataV8: "deleteCustomerScanDataV9",
});

// Deployment opt-in only. This does not grant a page entitlement: admission
// still chooses the mode and cap using the authenticated account on the server.
export function resolveScanFunctionRoute(name, generation = "V8") {
  return generation === "V9" ? V9_ROUTES[name] || name : name;
}
