import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));

// Catch command-output filenames, not normal dotfiles or named release artifacts.
// The 2026-11-19 Base44 builder commit created a tracked file literally named
// two double quotes containing "bash: line 2: \"\" command not found".
const suspiciousRootName = (name) => name.trim() === "" || /^["']{2}$/.test(name);

test("the root filename guard rejects shell redirection artifacts", () => {
  for (const name of ['""', "''", " ", "\t"]) {
    assert.equal(suspiciousRootName(name), true, JSON.stringify(name));
  }
  for (const name of [".gitignore", "package.json", "README.md", ".env.example", "tests"]) {
    assert.equal(suspiciousRootName(name), false, JSON.stringify(name));
  }
});

test("no shell-output filename artifacts exist at the repository root", () => {
  const anomalies = readdirSync(REPO_ROOT).filter(suspiciousRootName);
  assert.deepEqual(anomalies, []);
});
