import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");
const reopen = scanRuns.match(/export async function getScanRunWithFixList[\s\S]*?\n\}/)?.[0] || "";

test("signed terminal previews do not require internal FixItem row ids in the browser", () => {
  assert.match(reopen, /const access = String\(result\.access \|\| "locked"\)/);
  assert.match(reopen, /const authorityVerified = result\.authority_verified === true/);
  assert.match(reopen, /const terminalPreview = access === "preview" && String\(run\.status \|\| ""\) === "complete"/);

  const previewStart = reopen.indexOf("if (terminalPreview)");
  const strictStart = reopen.indexOf("} else if ((fixItems || []).some", previewStart);
  assert.ok(previewStart >= 0, "terminal preview branch must exist");
  assert.ok(strictStart > previewStart, "full-result row identity validation must remain after the preview branch");

  const previewBranch = reopen.slice(previewStart, strictStart);
  assert.match(previewBranch, /!authorityVerified/);
  assert.match(previewBranch, /fixItems\.length > 2/);
  assert.doesNotMatch(previewBranch, /item\.project_id|item\.scan_run_id|item\.fix_list_id/);
});

test("full and non-terminal results keep strict FixItem identity validation", () => {
  assert.match(reopen, /String\(item\.project_id \|\| ""\) !== projectId/);
  assert.match(reopen, /String\(item\.scan_run_id \|\| ""\) !== String\(run\.id \|\| ""\)/);
  assert.match(reopen, /String\(item\.fix_list_id \|\| ""\) !== String\(fixList\?\.id \|\| ""\)/);
});
