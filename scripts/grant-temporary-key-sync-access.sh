#!/usr/bin/env bash
set -euo pipefail

PROJECT="seo-autopilot-501517"
SECRET="SCAN_EVIDENCE_SIGNING_KEY"
OPERATOR="fixlist-github-operator@${PROJECT}.iam.gserviceaccount.com"
MEMBER="serviceAccount:${OPERATOR}"
ROLE="roles/secretmanager.secretAccessor"
TITLE="fixlist_beta_key_sync_temp"
EXPIRY="$(date -u -d '+2 hours' '+%Y-%m-%dT%H:%M:%SZ')"

printf '\n==> Grant temporary read access to one FixList signing secret\n'
printf 'project=%s\nsecret=%s\noperator=%s\nexpires=%s\n' "$PROJECT" "$SECRET" "$OPERATOR" "$EXPIRY"

gcloud config set project "$PROJECT" >/dev/null

gcloud secrets add-iam-policy-binding "$SECRET" \
  --project="$PROJECT" \
  --member="$MEMBER" \
  --role="$ROLE" \
  --condition="^@^title=${TITLE}@description=Temporary FixList beta signing-key synchronization@expression=request.time < timestamp('${EXPIRY}')" \
  --quiet >/dev/null

POLICY="$(mktemp)"
trap 'rm -f "$POLICY"' EXIT

gcloud secrets get-iam-policy "$SECRET" \
  --project="$PROJECT" \
  --format=json > "$POLICY"

python3 - "$POLICY" "$MEMBER" "$ROLE" "$TITLE" <<'PY'
import json, sys
path, member, role, title = sys.argv[1:]
policy = json.load(open(path, encoding='utf-8'))
for binding in policy.get('bindings', []):
    condition = binding.get('condition') or {}
    if binding.get('role') == role and member in binding.get('members', []) and condition.get('title') == title:
        print('Verified temporary single-secret accessor binding.')
        break
else:
    raise SystemExit('Temporary key-sync IAM binding was not verified.')
PY

printf '\nTEMP_KEY_SYNC_ACCESS_READY\n'
printf 'expires=%s\n' "$EXPIRY"
printf 'No secret value was read.\n'
