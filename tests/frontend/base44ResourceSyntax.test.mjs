import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

function filesBelow(directory, predicate) {
  const matches = [];
  for (const name of readdirSync(directory)) {
    const candidate = path.join(directory, name);
    if (statSync(candidate).isDirectory()) matches.push(...filesBelow(candidate, predicate));
    else if (predicate(candidate)) matches.push(candidate);
  }
  return matches.sort();
}

test("every Base44 function source parses before deployment", () => {
  const sources = filesBelow("base44/functions", (file) => /\.(?:js|ts)$/.test(file));
  assert.ok(sources.length > 0, "expected Base44 function sources");

  for (const file of sources) {
    const scriptKind = file.endsWith(".ts") ? ts.ScriptKind.TS : ts.ScriptKind.JS;
    const parsed = ts.createSourceFile(
      file,
      readFileSync(file, "utf8"),
      ts.ScriptTarget.ES2022,
      true,
      scriptKind,
    );
    assert.deepEqual(
      parsed.parseDiagnostics,
      [],
      `${file} has syntax errors: ${parsed.parseDiagnostics
        .map((diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, " "))
        .join("; ")}`,
    );
  }
});

test("every Base44 JSONC resource is strict JSON and function folders match names", () => {
  const resources = [
    ...filesBelow("base44/entities", (file) => file.endsWith(".jsonc")),
    ...filesBelow("base44/functions", (file) => path.basename(file) === "function.jsonc"),
  ];
  assert.ok(resources.length > 0, "expected Base44 resources");

  for (const file of resources) {
    const resource = JSON.parse(readFileSync(file, "utf8"));
    assert.equal(typeof resource.name, "string", `${file} requires a resource name`);
    assert.ok(resource.name.length > 0, `${file} requires a nonempty resource name`);
    if (path.basename(file) === "function.jsonc") {
      assert.equal(
        path.basename(path.dirname(file)),
        resource.name,
        `${file} folder must match the deployed function name`,
      );
    }
  }
});
