#!/usr/bin/env bash
# Guarded activation and drain-aware recovery for the fixed staged-scan queue.
#
# The stage queue (fixlist-scan-stages) carries every staged batch/finalize
# task. It is provisioned PAUSED. The existing cutover controls cover only the
# entry and drain queues; this tool owns the stage queue alone.
#
#   status       read only: queue/IAM/config readback, task counts, cohort state
#   activate     PAUSED -> RUNNING behind one exactly configured 0% revision
#   drain-pause  RUNNING -> PAUSED only after intake is off and all queues drain
#   recover      PAUSED with stranded tasks -> RUNNING so admitted scans finish
#
# Safety rules:
# - Fixed project/region/service/queue; nothing is accepted from input except
#   the exact candidate revision and bounded confirmations.
# - Exact current main source (release-source-guard) for every mutation.
# - Never deletes or purges tasks, never deletes the queue, never touches the
#   entry/drain queues, traffic, IAM, secrets, Base44 or the admission barrier.
# - Pausing is the dangerous direction here: a paused stage queue strands
#   admitted scans mid-pipeline. A pause therefore requires new staged intake to
#   be off and every queue that can feed the stage queue to be empty; a task
#   that appears after the pause is compensated by resuming, never by waiting.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO_ROOT/scripts/lib/release-source-guard.sh"

PROJECT="seo-autopilot-501517"
REGION="europe-west1"
SERVICE="fixlist-standard150-worker"
GATEWAY="fixlist-dispatch-gateway"
STAGE_QUEUE="fixlist-scan-stages"
ENTRY_QUEUE="fixlist-standard150"
DRAIN_QUEUE="fixlist-standard150-drain"
BUCKET="fixlist-scan-workspaces-seo-autopilot-501517"
WORKER_SA="fixlist-standard150-worker@seo-autopilot-501517.iam.gserviceaccount.com"
INVOKER_SA="fixlist-standard150-invoker@seo-autopilot-501517.iam.gserviceaccount.com"

OPERATION="${OPERATION:-status}"
SOURCE_SHA="${SOURCE_SHA:-}"
CONFIRM="${CONFIRM:-}"
STAGED_REVISION="${STAGED_REVISION:-}"
DRAIN_TIMEOUT_SECONDS="${STAGED_QUEUE_DRAIN_TIMEOUT_SECONDS:-900}"
DRAIN_POLL_SECONDS="${STAGED_QUEUE_DRAIN_POLL_SECONDS:-30}"
DRAIN_STABLE_READS="${STAGED_QUEUE_DRAIN_STABLE_READS:-3}"
GUARD=(python3 "$REPO_ROOT/scripts/staged_queue_guard.py")

refuse() { echo "Refusing staged queue operation: $*" >&2; exit 2; }

# Overrides are refused, not ignored: an operator who names another queue or
# project has the wrong runbook, and silently using the fixed one would hide it.
for name in GCP_PROJECT:"$PROJECT" GCP_REGION:"$REGION" CLOUD_RUN_SERVICE:"$SERVICE" STAGED_QUEUE:"$STAGE_QUEUE"; do
  var="${name%%:*}"; want="${name#*:}"
  [[ -z "${!var:-}" || "${!var}" == "$want" ]] || refuse "$var must be $want."
done
for value in "$DRAIN_TIMEOUT_SECONDS" "$DRAIN_POLL_SECONDS" "$DRAIN_STABLE_READS"; do
  [[ "$value" =~ ^[0-9]+$ ]] || refuse "drain timing values must be non-negative integers."
done
(( DRAIN_TIMEOUT_SECONDS <= 3600 && DRAIN_STABLE_READS >= 1 )) || refuse "drain timeout must be <=3600s and stable reads >=1."
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || refuse "exact 40-character SOURCE_SHA required."

case "$OPERATION" in
  status) ;;
  activate)
    [[ "$CONFIRM" == "ACTIVATE-STAGED-QUEUE:${SOURCE_SHA}:${STAGE_QUEUE}:${STAGED_REVISION}" ]] \
      || refuse "exact ACTIVATE-STAGED-QUEUE:<source-sha>:${STAGE_QUEUE}:<staged-revision> confirmation required." ;;
  drain-pause)
    [[ "$CONFIRM" == "DRAIN-PAUSE-STAGED-QUEUE:${SOURCE_SHA}:${STAGE_QUEUE}:BASE44-STAGED-INTAKE-OFF" ]] \
      || refuse "exact DRAIN-PAUSE-STAGED-QUEUE:<source-sha>:${STAGE_QUEUE}:BASE44-STAGED-INTAKE-OFF confirmation required." ;;
  recover)
    [[ "$CONFIRM" == "RECOVER-STAGED-QUEUE:${SOURCE_SHA}:${STAGE_QUEUE}:BASE44-STAGED-INTAKE-OFF" ]] \
      || refuse "exact RECOVER-STAGED-QUEUE:<source-sha>:${STAGE_QUEUE}:BASE44-STAGED-INTAKE-OFF confirmation required." ;;
  *) refuse "unsupported operation $OPERATION." ;;
esac
fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

describe_worker() {
  gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format=json > "$WORK/service.json"
  rm -f "$WORK"/revision-*.json
  local name
  while read -r name; do
    [[ -n "$name" ]] || continue
    gcloud run revisions describe "$name" --project="$PROJECT" --region="$REGION" --format=json > "$WORK/revision-$name.json"
  done < <("${GUARD[@]}" addressable "$WORK/service.json")
}

describe_gateway() {
  local serving
  gcloud run services describe "$GATEWAY" --project="$PROJECT" --region="$REGION" --format=json > "$WORK/gateway-service.json"
  serving="$(python3 -c 'import json,sys
t=[e for e in json.load(open(sys.argv[1])).get("status",{}).get("traffic",[]) if int(e.get("percent") or 0)==100]
print(t[0]["revisionName"] if len(t)==1 else "")' "$WORK/gateway-service.json")"
  [[ -n "$serving" ]] || refuse "dispatch gateway has no single 100%-serving revision."
  gcloud run revisions describe "$serving" --project="$PROJECT" --region="$REGION" --format=json > "$WORK/gateway-revision.json"
}

queue_state() {
  gcloud tasks queues describe "$1" --project="$PROJECT" --location="$REGION" --format='value(state)'
}

task_count() {
  gcloud tasks list --queue="$1" --project="$PROJECT" --location="$REGION" --limit=1000 --format=json > "$WORK/tasks-$1.json"
  "${GUARD[@]}" count "$WORK/tasks-$1.json"
}

verify_infra() {
  # Reuse the existing read-only verifier: bucket privacy/lifecycle, queue
  # retry policy, resource-scoped IAM and, when a task exists, its OIDC.
  local state="$1" target="$2" audience="$3" task="${4:-}"
  local extra=()
  [[ -n "$task" ]] && extra=(--task "${task##*/}")
  python3 "$REPO_ROOT/scripts/verify_staged_scan_infra.py" \
    --project "$PROJECT" --region "$REGION" --bucket "$BUCKET" --queue "$STAGE_QUEUE" \
    --worker-sa "$WORKER_SA" --invoker-sa "$INVOKER_SA" \
    --worker-url "$target" --token-audience "$audience" \
    --expected-queue-state "$state" "${extra[@]}"
}

require_intake_disabled() {
  describe_worker
  describe_gateway
  "${GUARD[@]}" intake-disabled "$WORK/service.json" "$WORK/gateway-revision.json" "$WORK"/revision-*.json
}

wait_for_empty_feeders() {
  # Stage tasks are created by entry deliveries (plan), by batches and by
  # drain watchdogs (limited finalize). All three queues must stay empty for
  # several consecutive reads before a pause cannot strand anything.
  local deadline=$(( SECONDS + DRAIN_TIMEOUT_SECONDS )) stable=0 s e d
  while :; do
    s="$(task_count "$STAGE_QUEUE")"; e="$(task_count "$ENTRY_QUEUE")"; d="$(task_count "$DRAIN_QUEUE")"
    echo "STAGED_QUEUE_DRAIN_READ stage=$s entry=$e drain=$d"
    if [[ "$s" == 0 && "$e" == 0 && "$d" == 0 ]]; then
      stable=$(( stable + 1 ))
      (( stable >= DRAIN_STABLE_READS )) && return 0
    else
      stable=0
    fi
    if (( SECONDS >= deadline )); then
      echo "STAGED_QUEUE_DRAIN_INCOMPLETE stage=$s entry=$e drain=$d; queue left RUNNING so admitted scans can finish." >&2
      return 1
    fi
    sleep "$DRAIN_POLL_SECONDS"
  done
}

status_command() {
  local state count first origin
  describe_worker
  origin="$("${GUARD[@]}" origin "$WORK/service.json")"
  state="$(queue_state "$STAGE_QUEUE")"
  count="$(task_count "$STAGE_QUEUE")"
  first="$("${GUARD[@]}" first-task "$WORK/tasks-$STAGE_QUEUE.json")"
  echo "STAGED_QUEUE_STATE state=$state tasks=$count entry_tasks=$(task_count "$ENTRY_QUEUE") drain_tasks=$(task_count "$DRAIN_QUEUE")"
  if [[ -n "$STAGED_REVISION" ]]; then
    found="$("${GUARD[@]}" activation "$WORK/service.json" "$STAGED_REVISION" "$WORK"/revision-*.json)"
    echo "STAGED_CANDIDATE_CONFIG $found"
    target="$(sed -n 's/.*target=\([^ ]*\).*/\1/p' <<< "$found")"
    verify_infra "$state" "$target" "$origin" "$first"
  fi
  if describe_gateway && "${GUARD[@]}" intake-disabled "$WORK/service.json" "$WORK/gateway-revision.json" "$WORK"/revision-*.json; then
    :
  else
    echo "STAGED_INTAKE_ENABLED somewhere GCP can read (see refusal above); Base44 is not readable from here."
  fi
}

activate_command() {
  local found target origin count
  [[ "$(queue_state "$STAGE_QUEUE")" == PAUSED ]] || refuse "activation expects a PAUSED stage queue; use status."
  count="$(task_count "$STAGE_QUEUE")"
  [[ "$count" == 0 ]] || refuse "the paused queue already holds $count task(s); use recover, not activate."
  describe_worker
  found="$("${GUARD[@]}" activation "$WORK/service.json" "$STAGED_REVISION" "$WORK"/revision-*.json)"
  echo "STAGED_CANDIDATE_CONFIG $found"
  target="$(sed -n 's/.*target=\([^ ]*\).*/\1/p' <<< "$found")"
  origin="$(sed -n 's/.*audience=\([^ ]*\).*/\1/p' <<< "$found")"
  verify_infra PAUSED "$target" "$origin"
  gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  verify_infra RUNNING "$target" "$origin"
  echo "STAGED_QUEUE_ACTIVATED queue=$STAGE_QUEUE revision=$STAGED_REVISION target=$target"
}

drain_pause_command() {
  [[ "$(queue_state "$STAGE_QUEUE")" == RUNNING ]] || refuse "drain-pause expects a RUNNING stage queue."
  require_intake_disabled
  wait_for_empty_feeders || exit 1
  require_intake_disabled
  gcloud tasks queues pause "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  if [[ "$(task_count "$STAGE_QUEUE")" != 0 || "$(task_count "$ENTRY_QUEUE")" != 0 || "$(task_count "$DRAIN_QUEUE")" != 0 ]]; then
    # A task raced the pause: resume rather than strand an admitted scan.
    gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
    echo "STAGED_QUEUE_PAUSE_COMPENSATED: work appeared during pause; queue resumed." >&2
    exit 1
  fi
  [[ "$(queue_state "$STAGE_QUEUE")" == PAUSED ]] || { echo "Stage queue did not report PAUSED." >&2; exit 1; }
  echo "STAGED_QUEUE_DRAINED_AND_PAUSED queue=$STAGE_QUEUE"
}

recover_command() {
  local count
  [[ "$(queue_state "$STAGE_QUEUE")" == PAUSED ]] || refuse "recover expects a PAUSED stage queue."
  require_intake_disabled
  count="$(task_count "$STAGE_QUEUE")"
  gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  [[ "$(queue_state "$STAGE_QUEUE")" == RUNNING ]] || { echo "Stage queue did not report RUNNING." >&2; exit 1; }
  echo "STAGED_QUEUE_RECOVERED queue=$STAGE_QUEUE pending_tasks=$count; run drain-pause once admitted scans finish."
}

case "$OPERATION" in
  status) status_command ;;
  activate) activate_command ;;
  drain-pause) drain_pause_command ;;
  recover) recover_command ;;
esac
