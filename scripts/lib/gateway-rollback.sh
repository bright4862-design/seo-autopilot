#!/usr/bin/env bash
# Sourced by the gateway publisher; never opens admission or touches workers.
rollback_gateway() {
  local tmp deadline
  if [[ -z "${PRE_DEPLOY_REVISION:-}" || ! -s "${GATEWAY_ROLLBACK_BASELINE:-}" ]]; then
    echo 'GATEWAY_ROLLBACK_FAILED: no verified previous gateway target.' >&2; return 1
  fi
  if [[ "${GATEWAY_ROLLBACK_URL:-}" != https://* ]]; then
    echo 'GATEWAY_ROLLBACK_FAILED: no verified previous gateway URL.' >&2; return 1
  fi
  tmp="$(mktemp -d)"
  if ! gcloud run services update-traffic "$GATEWAY" --project="$PROJECT" --region="$REGION" \
      --to-revisions="${PRE_DEPLOY_REVISION}=100" --quiet; then
    echo 'GATEWAY_ROLLBACK_FAILED: traffic restore command failed.' >&2
    rm -rf "$tmp"; return 1
  fi
  deadline=$(( SECONDS + ${GATEWAY_ROLLBACK_TIMEOUT_SECONDS:-180} ))
  while :; do
    if gcloud run services describe "$GATEWAY" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/service.json" \
      && gcloud run revisions describe "$PRE_DEPLOY_REVISION" --project="$PROJECT" --region="$REGION" --format=json > "$tmp/revision.json" \
      && curl --fail --silent --show-error --max-time 20 "$GATEWAY_ROLLBACK_URL/health" > "$tmp/health.json" \
      && python3 "$REPO_ROOT/scripts/verify_gateway_rollback.py" \
        --service-json "$tmp/service.json" --revision-json "$tmp/revision.json" \
        --health-json "$tmp/health.json" --baseline-json "$GATEWAY_ROLLBACK_BASELINE" \
        --expected-revision "$PRE_DEPLOY_REVISION" --expected-source-sha "$GATEWAY_ROLLBACK_SOURCE_SHA"; then
      echo "GATEWAY_ROLLBACK_VERIFIED revision=$PRE_DEPLOY_REVISION"
      rm -rf "$tmp"; return 0
    fi
    if (( SECONDS >= deadline )); then
      echo 'GATEWAY_ROLLBACK_FAILED: previous serving identity did not recover.' >&2
      rm -rf "$tmp"; return 1
    fi
    sleep 3
  done
}

gateway_rollback_on_failure() {
  local status="$1"
  if (( status != 0 )) && [[ "${GATEWAY_PROMOTION_ATTEMPTED:-0}" == 1 && "${GATEWAY_DEPLOY_VERIFIED:-0}" != 1 ]]; then
    if ! rollback_gateway; then return 3; fi
  fi
  return "$status"
}
