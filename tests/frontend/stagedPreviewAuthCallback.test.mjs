import assert from "node:assert/strict";
import test from "node:test";
import { isPreviewAuthCallback } from "../../scripts/preview-base44-v9.mjs";

const origin = "http://127.0.0.1:4174";
const path = "/api/apps/auth/final-callback";
const state = { app_id: "6a498732ec779dfaaeab0e53", domain: origin, from_url: `${origin}/dashboard` };
const query = (value = state) => new URLSearchParams({ login_code: "a".repeat(40), state: JSON.stringify(value) });

test("the preview admits only the FixList callback into its own origin", () => {
  assert.equal(isPreviewAuthCallback(path, "GET", query(), origin), true);
  for (const changed of [
    { app_id: "another-app" },
    { domain: "https://example.test" },
    { from_url: "https://example.test" },
    { from_url: "http://127.0.0.1:5173/dashboard" },
    { from_url: "http://another@127.0.0.1:4174/dashboard" },
  ]) assert.equal(isPreviewAuthCallback(path, "GET", query({ ...state, ...changed }), origin), false);
});

test("the callback leaves other auth paths and ambiguous parameters closed", () => {
  const duplicate = query();
  duplicate.append("state", "{}");
  assert.equal(isPreviewAuthCallback(path, "GET", duplicate, origin), false);
  assert.equal(isPreviewAuthCallback(path, "POST", query(), origin), false);
  assert.equal(isPreviewAuthCallback("/api/apps/auth/callback", "GET", query(), origin), false);
  assert.equal(isPreviewAuthCallback(path, "GET", new URLSearchParams({ login_code: "a".repeat(40), state: "broken" }), origin), false);
});
