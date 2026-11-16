import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { admissionTargetOrigin as launcherOrigin } from "../../base44/functions/startStandardScanJobV9/admissionClient.js";
import { admissionTargetOrigin as relayOrigin } from "../../base44/functions/durableScanWorkerControlV9/admissionClient.js";

test("the launcher, worker relay, and coordinator agree on the exact origin key", () => {
  const origins = new Map([
    ["https://Example.com/catalog?q=1#spec", "https://example.com:443"],
    ["https://www.example.com/", "https://www.example.com:443"],
    ["https://EXAMPLE.com.:8443/catalog", "https://example.com.:8443"],
    ["http://example.com:80/", "http://example.com:80"],
    ["https://bücher.example/catalog", "https://xn--bcher-kva.example:443"],
    ["https://[2606:4700:0000:0000::1111]:443/help", "https://[2606:4700::1111]:443"],
  ]);
  const supplied = Array.from(origins, ([url]) => launcherOrigin(url));
  const expected = Array.from(origins.values());
  assert.deepEqual(supplied, expected);
  assert.deepEqual(Array.from(origins.keys(), relayOrigin), expected);

  const stored = spawnSync("python3", ["-c", `
import json
import sys
from admission import normalize_target_origin
print(json.dumps([normalize_target_origin(origin) for origin in json.load(sys.stdin)]))
`], {
    cwd: fileURLToPath(new URL("../../admission-coordinator/", import.meta.url)),
    input: JSON.stringify(supplied),
    encoding: "utf8",
  });
  assert.equal(stored.status, 0, stored.stderr || String(stored.error || ""));
  assert.deepEqual(JSON.parse(stored.stdout), expected);
});
