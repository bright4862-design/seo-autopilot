import { readFileSync } from "node:fs";
import { RELEASE_FINGERPRINT } from "../../../src/lib/generatedReleaseContract.js";
import { parsePublishedScanOptions, resolveScanFunctionRoute } from "../../../src/lib/scanFunctionRouting.js";

function asScript(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8")
    .replace(/^import[\s\S]*?;\n/gm, "")
    .replace(/^export\s+/gm, "");
}

const clientSource = asScript("../../../src/api/base44Client.js")
  .replace("import.meta.env?.VITE_SCAN_FUNCTION_GENERATION", "generation");
const createBrowserClient = new Function(
  "createClient", "appParams", "parsePublishedScanOptions", "resolveScanFunctionRoute", "RELEASE_FINGERPRINT", "generation",
  `${clientSource}\nreturn base44;`,
);
const createCustomerRead = new Function(
  "base44", "clearCustomerAuthBoundary", `${asScript("../../../src/lib/scanRuns.js")}\nreturn getScanRunWithFixList;`,
);

// Bridge a local handler's Fetch Response to the SDK function transport.
export function loadSavedReportClient(invoke, { generation, userId = "user_hist" } = {}) {
  const sdk = {
    auth: { me: async () => ({ id: userId }) },
    functions: {
      async invoke(name, payload) {
        const response = await invoke(name, payload);
        const data = await response.json();
        if (!response.ok) {
          throw Object.assign(new Error(`Reader HTTP ${response.status}`), { response: { status: response.status, data } });
        }
        return { data, status: response.status };
      },
    },
  };
  return createBrowserClient(() => sdk, {}, parsePublishedScanOptions, resolveScanFunctionRoute, RELEASE_FINGERPRINT, generation);
}

export function savedReportReader(client) {
  return createCustomerRead(client, () => {});
}
