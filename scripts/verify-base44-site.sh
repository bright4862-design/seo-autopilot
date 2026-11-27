#!/usr/bin/env bash
# Prove that the public customer site serves the exact release source.
#
# Both release paths call this with only EXPECTED_SOURCE_SHA set -- the site
# publish (deploy-base44-beta-site.sh) and the worker promotion gate
# (fixlist-cloud-operator.yml) -- so the defaults below ARE the canonical
# production hosts. Base44 now serves this app's own site at
# getfixlist.base44.app ("Visit your site at: https://getfixlist.base44.app",
# release run 35358749857); the retired rich-rank-pilot-flow.base44.app answers
# 404 and must never be the host that decides a release.
set -euo pipefail

EXPECTED_SOURCE_SHA="${EXPECTED_SOURCE_SHA:-}"
EXPECTED_SCAN_FUNCTION_GENERATION="${EXPECTED_SCAN_FUNCTION_GENERATION:-}"
PUBLIC_URL="${PUBLIC_URL:-https://getfixlist.com/}"
BASE44_URL="${BASE44_URL:-https://getfixlist.base44.app/}"

if ! printf '%s' "$EXPECTED_SOURCE_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "EXPECTED_SOURCE_SHA must be the exact 40-character source SHA." >&2
  exit 2
fi
case "$EXPECTED_SCAN_FUNCTION_GENERATION" in
  ""|PUBLIC|V9|PUBLISHED_PILOT|PAID_PILOT) ;;
  *) echo "EXPECTED_SCAN_FUNCTION_GENERATION must name a supported site mode." >&2; exit 2 ;;
esac

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

pilot=false
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if (( $# > 0 )); then
  [[ $# == 2 && "$1" == --published-pilot && ( "$2" == PUBLISHED_PILOT || "$2" == PAID_PILOT ) ]] || exit 2
  pilot=true
  EXPECTED_SCAN_FUNCTION_GENERATION="$2"
  PUBLIC_URL=https://getfixlist.com/
  BASE44_URL=https://getfixlist.base44.app/
  bash "$repo_root/scripts/build-published-pilot-site.sh" "$EXPECTED_SOURCE_SHA" "$2" "$TMP/source" >&2
  pilot_dist="$TMP/source/dist"
  local_assets="$(python3 "$repo_root/scripts/lib/published-site-assets.py" "$pilot_dist/index.html")"
  read -r local_script local_style <<<"$local_assets"
fi

verify_bundle_identity() {
  node --expose-internals - "$1" "$EXPECTED_SOURCE_SHA" "$EXPECTED_SCAN_FUNCTION_GENERATION" <<'NODE'
const fs = require("node:fs");
const [path, expectedSource, expectedGeneration] = process.argv.slice(2);
let tree;
try {
  // Acorn ships with Node. The verifier also runs on promotion hosts without
  // npm dependencies. Parse the public asset without loading or executing it.
  const { parse } = require("internal/deps/acorn/acorn/dist/acorn");
  tree = parse(fs.readFileSync(path, "utf8"), { ecmaVersion: "latest", sourceType: "module" });
} catch {
  process.exit(12);
}

const bindings = new Map();
for (const statement of tree.body) {
  if (statement.type !== "VariableDeclaration" || statement.kind !== "const") continue;
  for (const { id, init } of statement.declarations) {
    if (id.type === "Identifier" && init?.type === "Literal" && typeof init.value === "string") {
      bindings.set(id.name, init);
    }
  }
}

const isIdentifier = (node, name) => node?.type === "Identifier" && node.name === name;
const isLiteral = (node, value) => node?.type === "Literal" && node.value === value;
const isWindowType = (node) =>
  node?.type === "UnaryExpression" && node.operator === "typeof" && isIdentifier(node.argument, "window");
const isWindowGuard = (node) => node?.type === "BinaryExpression" && (
  (node.operator === "<" && isWindowType(node.left) && isLiteral(node.right, "u"))
  || (node.operator === "!==" && (
    (isWindowType(node.left) && isLiteral(node.right, "undefined"))
    || (isLiteral(node.left, "undefined") && isWindowType(node.right))
  ))
);
const isFalse = (node) => isLiteral(node, false)
  || (node?.type === "UnaryExpression" && node.operator === "!" && isLiteral(node.argument, 1));
const markers = new Map([
  ["__FIXLIST_SOURCE_SHA__", []],
  ["__FIXLIST_SCAN_FUNCTION_GENERATION__", []],
]);

function visitExpression(node) {
  if (node.type === "SequenceExpression") {
    node.expressions.forEach(visitExpression);
    return;
  }
  if (node.type === "LogicalExpression" && node.operator === "&&" && isWindowGuard(node.left)) {
    visitExpression(node.right);
    return;
  }
  if (node.type !== "CallExpression" || node.callee.type !== "MemberExpression"
    || node.callee.computed || !isIdentifier(node.callee.object, "Object")
    || !isIdentifier(node.callee.property, "defineProperty") || !isIdentifier(node.arguments[0], "window")
    || node.arguments[1]?.type !== "Literal") return;
  const matches = markers.get(node.arguments[1].value);
  if (!matches) return;
  const descriptor = node.arguments[2];
  if (node.arguments.length !== 3 || descriptor?.type !== "ObjectExpression"
    || descriptor.properties.length !== 4) {
    matches.push(null);
    return;
  }
  const properties = new Map();
  for (const property of descriptor.properties) {
    if (property.type === "Property" && !property.computed && property.kind === "init" && !property.method) {
      const key = property.key.type === "Identifier" ? property.key.name : property.key.value;
      properties.set(key, property.value);
    }
  }
  if (properties.size !== 4 || !["enumerable", "configurable", "writable"].every((key) => isFalse(properties.get(key)))) {
    matches.push(null);
    return;
  }
  const value = properties.get("value");
  const literal = value?.type === "Identifier" ? bindings.get(value.name) : value;
  if (literal?.type !== "Literal" || (value?.type === "Identifier" && literal.start >= node.start)) {
    matches.push(null);
    return;
  }
  matches.push(literal.value);
}

function visitStatement(node) {
  if (node.type === "ExpressionStatement") visitExpression(node.expression);
  if (node.type === "IfStatement" && node.alternate === null && isWindowGuard(node.test)) {
    const statements = node.consequent.type === "BlockStatement" ? node.consequent.body : [node.consequent];
    if (statements.every((statement) => statement.type === "ExpressionStatement")) {
      statements.forEach((statement) => visitExpression(statement.expression));
    }
  }
}
tree.body.forEach(visitStatement);

const hasMarker = (name, value) => markers.get(name).length === 1 && markers.get(name)[0] === value;
if (!hasMarker("__FIXLIST_SOURCE_SHA__", expectedSource)) process.exit(10);
if (expectedGeneration && !hasMarker("__FIXLIST_SCAN_FUNCTION_GENERATION__", expectedGeneration)) process.exit(11);
NODE
}

verify_url() {
  local url="$1"
  local page_path="${2:-/}" status html asset style marker_status assets
  # Read the HTTP status instead of letting --fail collapse every answer into
  # curl exit 22. A host that is not serving the app (a retired alias, an
  # unpublished site) is a different failure from a site serving the wrong
  # source, and the release log has to say which one happened.
  if ! status="$(curl --silent --show-error --max-time 30 \
    -H 'Cache-Control: no-cache' \
    -H 'Pragma: no-cache' \
    -o "$TMP/page.html" -w '%{http_code}' \
    "${url%/}${page_path}?fixlist_release_verify=${EXPECTED_SOURCE_SHA}")"; then
    echo "SITE_URL_UNREACHABLE url=$url" >&2
    return 1
  fi
  if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
    echo "SITE_URL_NOT_SERVING url=$url http_status=$status" >&2
    echo "This host is not serving the FixList app. That is a stale or unpublished site URL, not a source-SHA mismatch: compare it with the 'Visit your site at:' line printed by 'site deploy'." >&2
    return 3
  fi
  if [[ "$pilot" == true ]]; then
    assets="$(python3 "$repo_root/scripts/lib/published-site-assets.py" "$TMP/page.html")" || return 1
    read -r asset style <<<"$assets"
  else
    html="$(<"$TMP/page.html")"
    asset="$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' <<<"$html" | head -1 || true)"
  fi
  if [[ -z "$asset" ]]; then
    echo "SITE BUNDLE NOT FOUND: $url" >&2
    return 1
  fi
  curl --fail --silent --show-error --max-time 30 -o "$TMP/bundle.js" \
    -H 'Cache-Control: no-cache' \
    -H 'Pragma: no-cache' \
    "${url%/}${asset}?fixlist_release_verify=${EXPECTED_SOURCE_SHA}" || return 1
  if verify_bundle_identity "$TMP/bundle.js"; then
    if [[ "$pilot" == true ]]; then
      curl --fail --silent --show-error --max-time 30 -o "$TMP/bundle.css" \
        -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
        "${url%/}${style}?fixlist_release_verify=${EXPECTED_SOURCE_SHA}" || return 1
      if [[ "$asset" != "$local_script" || "$style" != "$local_style" ]] \
        || ! cmp -s "$pilot_dist$local_script" "$TMP/bundle.js" || ! cmp -s "$pilot_dist$local_style" "$TMP/bundle.css"; then
        echo "PUBLISHED_PILOT_ASSET_MISMATCH host=$url path=$page_path" >&2
        return 1
      fi
    fi
    printf 'SITE_SOURCE_SHA_VERIFIED %s%s\n' "$url" "$asset"
    return 0
  else
    marker_status=$?
  fi
  case "$marker_status" in
    10) echo "SITE SOURCE SHA MISMATCH: $url$asset" >&2 ;;
    11) echo "SITE SCAN FUNCTION GENERATION MISMATCH: $url$asset" >&2 ;;
    *) echo "SITE BUNDLE IDENTITY UNREADABLE: $url$asset" >&2 ;;
  esac
  return 1
}

verify_url "$PUBLIC_URL"
verify_url "$BASE44_URL"
if [[ "$pilot" == true ]]; then
  verify_url "$PUBLIC_URL" /onboarding
  verify_url "$BASE44_URL" /onboarding
  printf 'PUBLISHED_PILOT_FRONTEND_VERIFIED source_sha=%s mode=%s publication=prebuilt lockfile_build=matched\n' \
    "$EXPECTED_SOURCE_SHA" "$EXPECTED_SCAN_FUNCTION_GENERATION"
fi
printf 'BASE44_SITE_SOURCE_VERIFIED source_sha=%s\n' "$EXPECTED_SOURCE_SHA"
