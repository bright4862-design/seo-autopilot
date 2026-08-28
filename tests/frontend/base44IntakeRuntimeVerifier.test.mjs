import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const verifier = "scripts/verify-base44-scan-intake-runtime.sh";

function runVerifier(action, mode) {
  const dir = mkdtempSync(join(tmpdir(), "fixlist-intake-probe-"));
  try {
    const fakeBase44 = join(dir, "base44");
    const fakeDeno = join(dir, "deno");
    writeFileSync(fakeDeno, "#!/usr/bin/env bash\nexit 0\n");
    chmodSync(fakeDeno, 0o755);
    writeFileSync(fakeBase44, `#!/usr/bin/env bash
cat >/dev/null
case "$FAKE_PROBE_MODE" in
  pause)
    echo 'FIXLIST_INTAKE_PROBE={"status":503,"accepted":false,"failure_code":"scan_intake_paused","scan_id":""}'
    ;;
  resume)
    echo 'FIXLIST_INTAKE_PROBE={"status":404,"accepted":false,"failure_code":"project_not_found","scan_id":""}'
    ;;
  stale)
    echo 'FIXLIST_INTAKE_PROBE={"status":503,"accepted":false,"failure_code":"scan_intake_paused","scan_id":""}'
    ;;
  created)
    echo 'FIXLIST_INTAKE_PROBE={"status":200,"accepted":true,"failure_code":"","scan_id":"scan-unexpected"}'
    ;;
  *)
    exit 9
    ;;
esac
`);
    chmodSync(fakeBase44, 0o755);
    return spawnSync("bash", [verifier], {
      encoding: "utf8",
      env: {
        ...process.env,
        ACTION: action,
        FAKE_PROBE_MODE: mode,
        FIXLIST_BASE44_CLI: fakeBase44,
        BASE44_APP_ID: "6a498732ec779dfaaeab0e53",
        PATH: `${dir}:${process.env.PATH || ""}`,
      },
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("pause runtime probe succeeds only on scan_intake_paused", () => {
  const result = runVerifier("pause", "pause");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /BASE44_SCAN_INTAKE_RUNTIME_VERIFIED/);
});

test("resume runtime probe succeeds only after intake reaches project lookup", () => {
  const result = runVerifier("resume", "resume");
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /expected_code=project_not_found/);
});

test("resume fails closed when secret write succeeded but production remains stale", () => {
  const result = runVerifier("resume", "stale");
  assert.notEqual(result.status, 0);
  assert.doesNotMatch(result.stdout, /BASE44_SCAN_INTAKE_RUNTIME_VERIFIED/);
  assert.match(result.stderr, /Runtime intake probe/);
});

test("runtime probe rejects any response that accepted or created a scan", () => {
  for (const action of ["pause", "resume"]) {
    const result = runVerifier(action, "created");
    assert.notEqual(result.status, 0);
    assert.doesNotMatch(result.stdout, /BASE44_SCAN_INTAKE_RUNTIME_VERIFIED/);
  }
});
