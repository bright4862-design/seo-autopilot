import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

/**
 * The hosted Base44 release lane failed closed with one undifferentiated
 * "BASE44_API_KEY is malformed", which an operator who cannot read the secret
 * has no way to act on. The guard now classifies the malformation in shape
 * facts only.
 *
 * These run the real function rather than grepping it, so the classification
 * is proven rather than described. Every case here is a malformed key, so the
 * guard returns before the Base44 CLI is ever invoked.
 */

const HELPER = path.resolve("scripts/lib/base44-pinned-cli.sh");

/**
 * Runs the real guard against one candidate key and returns exactly what an
 * operator would read in the Actions log: its stderr plus the exit status,
 * with stdout discarded.
 *
 * The identity file lives in a fresh temporary directory that is removed
 * afterwards, so no candidate key outlives the assertion inspecting it.
 */
function guardStderr(key) {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), "b44guard-"));
  const outFile = path.join(out, "identity");
  try {
    // The helper sets -e, so its deliberate `return 2` would abort the shell
    // before anything could be captured. Relax it around the call only.
    const script = `
      source "${HELPER}"
      set +e
      fixlist_require_base44_owner "" "${outFile}" "app_123" 2>&1 1>/dev/null
      echo "exit=$?"
    `;
    return execFileSync("bash", ["-c", script], {
      encoding: "utf8",
      env: { ...process.env, BASE44_API_KEY: key },
    });
  } finally {
    fs.rmSync(out, { recursive: true, force: true });
  }
}

const SECRET_BODY = "abcdefghijklmnop";

test("a wrong-prefix key is named as such and never echoed", () => {
  const stderr = guardStderr(`sk-live-${SECRET_BODY}`);
  assert.match(stderr, /BASE44_API_KEY is malformed/);
  assert.match(stderr, /missing_b44k_prefix/);
  assert.ok(!stderr.includes(SECRET_BODY), "the guard leaked secret material");
  assert.ok(!stderr.includes("sk-live"), "the guard leaked the key's prefix");
});

test("a pasted quote is distinguished from a genuinely wrong key", () => {
  // Both fail the prefix test; only the classification tells them apart, which
  // is the difference between "rotate the key" and "re-paste it".
  const quoted = guardStderr(`"b44k_${SECRET_BODY}"`);
  assert.match(quoted, /leading_quote/);
  assert.match(quoted, /trailing_quote/);
  assert.ok(!quoted.includes(SECRET_BODY));

  const spaced = guardStderr(` b44k_${SECRET_BODY}`);
  assert.match(spaced, /leading_whitespace/);
  assert.ok(!spaced.includes(SECRET_BODY));
});

test("a quote on either boundary alone is still refused", () => {
  // A trailing quote keeps the b44k_ prefix, carries no whitespace and is under
  // length, so checking only the leading character let it reach the CLI and
  // fail there as an opaque authentication error.
  for (const [key, label] of [
    [`b44k_${SECRET_BODY}"`, "trailing double quote"],
    [`b44k_${SECRET_BODY}'`, "trailing single quote"],
  ]) {
    const stderr = guardStderr(key);
    assert.match(stderr, /BASE44_API_KEY is malformed/, `${label} was accepted`);
    assert.match(stderr, /trailing_quote/, label);
    assert.ok(!stderr.includes(SECRET_BODY), `${label} leaked secret material`);
  }

  const leadingOnly = guardStderr(`"b44k_${SECRET_BODY}`);
  assert.match(leadingOnly, /leading_quote/);
  assert.doesNotMatch(leadingOnly, /trailing_quote/, "only the offending boundary is named");
});

test("a trailing newline is named rather than left to guesswork", () => {
  const stderr = guardStderr(`b44k_${SECRET_BODY}\n`);
  assert.match(stderr, /contains_newline/);
  assert.ok(!stderr.includes(SECRET_BODY));
});

test("a carriage return is refused, not passed into the api_key header", () => {
  // This shape previously satisfied every condition -- b44k_ prefix, no \n,
  // under 512 -- so it reached the header, where a CR breaks or injects.
  const stderr = guardStderr(`b44k_${SECRET_BODY}\r`);
  assert.match(stderr, /BASE44_API_KEY is malformed/);
  assert.match(stderr, /contains_carriage_return/);
  assert.ok(!stderr.includes(SECRET_BODY));
});

test("an over-long value reports its length and nothing else", () => {
  const stderr = guardStderr(`b44k_${"a".repeat(600)}`);
  assert.match(stderr, /longer_than_512/);
  assert.match(stderr, /length=605/);
});

test("the guard never repairs a credential for the operator", () => {
  // Silently trimming a key would mask a wrong secret and make the lane lie
  // about which credential it used.
  const helper = fs.readFileSync(HELPER, "utf8");
  assert.match(helper, /never trimmed or repaired here/);
  // And it must still never print the value or a slice of it.
  assert.doesNotMatch(helper, /slice\(0,\s*\d+\)/);
  assert.doesNotMatch(helper, /echo[^\n]*\$\{?BASE44_API_KEY\}?[^\n]*>&2/);
});
