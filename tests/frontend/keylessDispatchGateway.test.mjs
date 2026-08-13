import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDispatchGatewayRequest,
  taskNameForDrain,
  taskNameForScan,
} from "../../base44/functions/startStandardScanJob/cloudTasks.js";

const QUEUE = "projects/seo-autopilot-501517/locations/europe-west1/queues/fixlist-standard150";


test("gateway request signing matches the Python verifier contract", async () => {
  const task = {
    name: taskNameForScan(QUEUE, "scan123", 1),
    dispatchDeadline: "480s",
  };
  const result = await buildDispatchGatewayRequest({
    signingKey: "unit-test-root-secret",
    queuePath: QUEUE,
    body: { task },
    timestampSeconds: 1786600000,
  });

  assert.equal(result.timestamp, "1786600000");
  assert.equal(
    result.payloadText,
    `{"queue_path":"${QUEUE}","task":{"name":"${QUEUE}/tasks/standard150-scan123-a1","dispatchDeadline":"480s"}}`,
  );
  assert.equal(
    result.signature,
    "bc2006e9ae0c8bb48c04020b1ba7f69417d84070a10a63914c93c7477c070072",
  );
});


test("scan and drain task names stay attempt-bound and deterministic", () => {
  assert.equal(
    taskNameForScan(QUEUE, "scan_abc", 2),
    `${QUEUE}/tasks/standard150-scan_abc-a2`,
  );
  assert.equal(
    taskNameForDrain(QUEUE, "scan_abc", 2),
    `${QUEUE}/tasks/standard150-drain-scan_abc-a2`,
  );
});


test("gateway request builder rejects non-numeric timestamps", async () => {
  await assert.rejects(
    () => buildDispatchGatewayRequest({
      signingKey: "unit-test-root-secret",
      queuePath: QUEUE,
      body: { task: null },
      timestampSeconds: Number.NaN,
    }),
    /Invalid dispatch timestamp/,
  );
});
