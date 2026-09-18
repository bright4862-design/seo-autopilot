import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

// Release run 35358749857 deployed the V6 site successfully -- getfixlist.com
// served the exact source -- and then failed on `curl: (22) ... 404` because the
// verifier still probed the retired rich-rank-pilot-flow.base44.app alias. These
// tests run the real verifier against a fake `curl` so they can prove which
// hosts decide a release, and that a host answering 404 is reported as a stale
// or unpublished URL instead of looking like a failed deployment.

const VERIFIER = path.resolve("scripts/verify-base44-site.sh");
const SHA = "5e0dc8d083b1284ec36d6a75e0ddc21f1d11c093";
const OTHER_SHA = "0123456789abcdef0123456789abcdef01234567";
const PUBLIC = "https://getfixlist.com";
const BASE44 = "https://getfixlist.base44.app";
const RETIRED = "https://rich-rank-pilot-flow.base44.app";
const ASSET = "/assets/index-BNxSbrsB.js";

// Minimal stand-in for the two curl invocations the verifier makes: the page
// fetch (-o FILE -w '%{http_code}', no --fail) and the bundle fetch (--fail,
// body on stdout). Routes are "status<TAB>url-without-query<TAB>body-file";
// status 000 simulates an unreachable host.
const FAKE_CURL = `#!/usr/bin/env bash
out=""; fmt=""; fail=0; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -w) fmt="$2"; shift 2 ;;
    -H|--max-time) shift 2 ;;
    --fail) fail=1; shift ;;
    --silent|--show-error) shift ;;
    *) url="$1"; shift ;;
  esac
done
printf '%s\\n' "$url" >> "$FAKE_CURL_LOG"
base="\${url%%\\?*}"
status=404; body=""
while IFS=$'\\t' read -r s u f; do
  if [ "$u" = "$base" ]; then status="$s"; body="$f"; break; fi
done < "$FAKE_CURL_ROUTES"
if [ "$status" = "000" ]; then
  echo "curl: (6) Could not resolve host" >&2
  exit 6
fi
if [ -n "$out" ]; then
  if [ -n "$body" ]; then cat "$body" > "$out"; else : > "$out"; fi
  [ "$fmt" = '%{http_code}' ] && printf '%s' "$status"
  exit 0
fi
if [ "$fail" = 1 ] && [ "$status" -ge 400 ]; then
  echo "curl: (22) The requested URL returned error: $status" >&2
  exit 22
fi
[ -n "$body" ] && cat "$body"
exit 0
`;

function sandbox(t, routes) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fixlist-site-verify-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const bin = path.join(dir, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, "curl"), FAKE_CURL, { mode: 0o755 });
  const lines = routes.map(([status, url, body], index) => {
    let file = "";
    if (body !== undefined) {
      file = path.join(dir, `body-${index}`);
      fs.writeFileSync(file, body);
    }
    return `${status}\t${url}\t${file}`;
  });
  fs.writeFileSync(path.join(dir, "routes"), `${lines.join("\n")}\n`);
  fs.writeFileSync(path.join(dir, "requests.log"), "");
  return {
    run(env = {}) {
      const result = spawnSync("bash", [VERIFIER], {
        encoding: "utf8",
        env: {
          PATH: `${bin}${path.delimiter}${process.env.PATH}`,
          FAKE_CURL_ROUTES: path.join(dir, "routes"),
          FAKE_CURL_LOG: path.join(dir, "requests.log"),
          EXPECTED_SOURCE_SHA: SHA,
          ...env,
        },
      });
      const requests = fs.readFileSync(path.join(dir, "requests.log"), "utf8").split("\n").filter(Boolean);
      return { ...result, requests };
    },
  };
}

const page = `<!doctype html><html><head><script type="module" src="${ASSET}"></script></head><body></body></html>`;
const bundle = (sha) => `(()=>{window.__FIXLIST_SOURCE_SHA__="${sha}";})();`;
const servingSite = (origin, sha = SHA) => [
  ["200", `${origin}/`, page],
  ["200", `${origin}${ASSET}`, bundle(sha)],
];

test("with no overrides the verifier proves getfixlist.com and the canonical Base44 site", (t) => {
  const box = sandbox(t, [...servingSite(PUBLIC), ...servingSite(BASE44), ["404", `${RETIRED}/`, "Not Found"]]);
  const result = box.run();

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, new RegExp(`^SITE_SOURCE_SHA_VERIFIED ${PUBLIC}/${ASSET}$`, "m"));
  assert.match(result.stdout, new RegExp(`^SITE_SOURCE_SHA_VERIFIED ${BASE44}/${ASSET}$`, "m"));
  assert.match(result.stdout, new RegExp(`^BASE44_SITE_SOURCE_VERIFIED source_sha=${SHA}$`, "m"));

  const hosts = new Set(result.requests.map((url) => new URL(url).host));
  assert.deepEqual([...hosts].sort(), ["getfixlist.base44.app", "getfixlist.com"]);
  for (const url of result.requests) {
    assert.equal(new URL(url).searchParams.get("fixlist_release_verify"), SHA, "every probe must bypass caches with the exact SHA");
  }
});

test("the verifier no longer names the retired Base44 alias anywhere", () => {
  const source = fs.readFileSync(VERIFIER, "utf8");
  assert.match(source, /BASE44_URL="\$\{BASE44_URL:-https:\/\/getfixlist\.base44\.app\/\}"/);
  assert.match(source, /PUBLIC_URL="\$\{PUBLIC_URL:-https:\/\/getfixlist\.com\/\}"/);
  const code = source.split("\n").filter((line) => !line.trimStart().startsWith("#")).join("\n");
  assert.doesNotMatch(code, /rich-rank-pilot-flow/);
});

test("a stale Base44 host answering 404 is reported as a URL problem, not a failed deployment", (t) => {
  // The shape of run 35358749857: the public site verifies, the alias 404s.
  const box = sandbox(t, [...servingSite(PUBLIC), ["404", `${RETIRED}/`, "Not Found"]]);
  const result = box.run({ BASE44_URL: `${RETIRED}/` });

  assert.equal(result.status, 3, "a host that is not serving the app has its own exit status");
  assert.match(result.stdout, new RegExp(`^SITE_SOURCE_SHA_VERIFIED ${PUBLIC}/${ASSET}$`, "m"));
  assert.match(result.stderr, new RegExp(`SITE_URL_NOT_SERVING url=${RETIRED}/ http_status=404`));
  assert.match(result.stderr, /not a source-SHA mismatch/);
  assert.doesNotMatch(result.stderr, /SITE SOURCE SHA MISMATCH/);
  assert.doesNotMatch(result.stderr, /curl: \(22\)/, "the stale host must not surface as a bare curl failure");
  assert.doesNotMatch(result.stdout, /BASE44_SITE_SOURCE_VERIFIED/, "a 404 host can never be counted as verified");
  assert.ok(!result.requests.some((url) => url.startsWith(`${RETIRED}/assets/`)), "no bundle probe after a 404 page");
});

test("a Base44 site serving a different source still fails as a source mismatch", (t) => {
  const box = sandbox(t, [...servingSite(PUBLIC), ...servingSite(BASE44, OTHER_SHA)]);
  const result = box.run();

  assert.equal(result.status, 1);
  assert.match(result.stderr, new RegExp(`SITE SOURCE SHA MISMATCH: ${BASE44}/${ASSET}`));
  assert.doesNotMatch(result.stdout, /BASE44_SITE_SOURCE_VERIFIED/);
});

test("the public site is still verified first and still fails closed", (t) => {
  const box = sandbox(t, [["404", `${PUBLIC}/`, "Not Found"], ...servingSite(BASE44)]);
  const result = box.run();

  assert.equal(result.status, 3);
  assert.match(result.stderr, new RegExp(`SITE_URL_NOT_SERVING url=${PUBLIC}/ http_status=404`));
  assert.ok(result.requests.every((url) => new URL(url).host === "getfixlist.com"), "stop at the first failed host");
});

test("a page with no bundle and an unreachable host both fail with their own diagnostic", (t) => {
  const noBundle = sandbox(t, [["200", `${PUBLIC}/`, "<html><body>maintenance</body></html>"], ...servingSite(BASE44)]);
  const missing = noBundle.run();
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, new RegExp(`SITE BUNDLE NOT FOUND: ${PUBLIC}/`));

  const offline = sandbox(t, [["000", `${PUBLIC}/`], ...servingSite(BASE44)]);
  const unreachable = offline.run();
  assert.equal(unreachable.status, 1);
  assert.match(unreachable.stderr, new RegExp(`SITE_URL_UNREACHABLE url=${PUBLIC}/`));
});

test("the verifier still refuses a missing or abbreviated source SHA", (t) => {
  const box = sandbox(t, [...servingSite(PUBLIC), ...servingSite(BASE44)]);
  for (const value of ["", SHA.slice(0, 12)]) {
    const result = box.run({ EXPECTED_SOURCE_SHA: value });
    assert.equal(result.status, 2);
    assert.match(result.stderr, /exact 40-character source SHA/);
    assert.equal(result.requests.length, 0);
  }
});

test("both release paths still rely on the verifier's canonical defaults", () => {
  const publish = fs.readFileSync("scripts/deploy-base44-beta-site.sh", "utf8");
  const operator = fs.readFileSync(".github/workflows/fixlist-cloud-operator.yml", "utf8");
  assert.match(publish, /EXPECTED_SOURCE_SHA="\$SOURCE_SHA" bash "\$REPO_ROOT\/scripts\/verify-base44-site\.sh"/);
  assert.match(operator, /EXPECTED_SOURCE_SHA: \$\{\{ steps\.command\.outputs\.product_sha \}\}\n\s+shell: bash\n\s+run: bash \.\/scripts\/verify-base44-site\.sh/);
  for (const source of [publish, operator]) {
    assert.doesNotMatch(source, /BASE44_URL|rich-rank-pilot-flow/, "a caller override would bring the stale-alias failure back");
  }
});
