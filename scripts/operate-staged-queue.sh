#!/usr/bin/env bash
# Guarded activation and drain-aware recovery for the fixed staged-scan queue.
#
# The stage queue (fixlist-scan-stages) carries every staged batch/finalize
# task. It is provisioned PAUSED. The existing cutover controls cover only the
# entry and drain queues; this tool owns the stage queue alone.
#
#   status       read only: queue/IAM/config readback, task counts, cohort state
#   activate     PAUSED -> RUNNING behind one exactly configured 0% revision
#   drain-pause  RUNNING -> PAUSED only when the coordinator proves admissions are
#                closed and every admitted scan is terminal, and all queues drain
#   recover      PAUSED with stranded tasks -> RUNNING once admissions are closed
#
# Safety rules:
# - Fixed project/region/service/queue; nothing is accepted from input except
#   the exact candidate revision and bounded confirmations.
# - Exact current main source (release-source-guard) for every mutation.
# - Never deletes or purges tasks, never deletes the queue, never touches the
#   entry/drain queues, traffic, IAM, secrets, Base44 or the admission barrier.
# - Pausing is the dangerous direction here: a paused stage queue strands
#   admitted scans mid-pipeline. Empty task lists alone cannot prove that: a
#   frontier can be committed while its next task is not yet enqueued. A pause
#   therefore requires the coordinator's signed barrier snapshot to show claims
#   CLOSED with zero active/bound/live obligations (an admission is released
#   only at a terminal state), before and after the pause, plus empty queues.
#   Anything that appears after the pause is compensated by resuming.
# - Worker revisions and their tags are never changed: an in-flight scan keeps
#   its pinned tagged revision and OIDC route until it is terminal.
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
BARRIER_EXPECTED_GENERATION="${BARRIER_EXPECTED_GENERATION:-}"
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
  drain-pause|recover)
    [[ "$BARRIER_EXPECTED_GENERATION" =~ ^[0-9]+$ ]] || refuse "exact BARRIER_EXPECTED_GENERATION required."
    prefix="DRAIN-PAUSE"; [[ "$OPERATION" == recover ]] && prefix="RECOVER"
    [[ "$CONFIRM" == "${prefix}-STAGED-QUEUE:${SOURCE_SHA}:${STAGE_QUEUE}:${BARRIER_EXPECTED_GENERATION}" ]] \
      || refuse "exact ${prefix}-STAGED-QUEUE:<source-sha>:${STAGE_QUEUE}:<barrier-generation> confirmation required." ;;
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
  serving="$("${GUARD[@]}" serving "$WORK/gateway-service.json")"
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

barrier_proof() {
  # The existing operator verifies the coordinator's HMAC-signed drain
  # snapshot; this tool only accepts its single status line. No proof, no pause.
  local mode="$1" ticket="${CHANGE_TICKET:-staged-queue-${OPERATION}}"
  local reason="${CUTOVER_REASON:-Staged queue ${OPERATION} admission proof}"
  OPERATION=barrier-status CONFIRM="" SOURCE_SHA="$SOURCE_SHA" \
    BARRIER_EXPECTED_GENERATION="$BARRIER_EXPECTED_GENERATION" BARRIER_EXPECTED_PRIOR_MODE=closed \
    CHANGE_TICKET="$ticket" CUTOVER_REASON="$reason" \
    bash "$REPO_ROOT/scripts/fixlist-cloud-operator.sh" > "$WORK/barrier.out" 2> "$WORK/barrier.err" || {
      cat "$WORK/barrier.err" >&2
      echo "Refusing: the signed admission barrier snapshot could not be read." >&2
      return 1
    }
  "${GUARD[@]}" barrier "$WORK/barrier.out" "$BARRIER_EXPECTED_GENERATION" "$mode"
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
    found="$("${GUARD[@]}" activation "$WORK/service.json" "$STAGED_REVISION" "$SOURCE_SHA" "$WORK"/revision-*.json)"
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
  found="$("${GUARD[@]}" activation "$WORK/service.json" "$STAGED_REVISION" "$SOURCE_SHA" "$WORK"/revision-*.json)"
  echo "STAGED_CANDIDATE_CONFIG $found"
  target="$(sed -n 's/.*target=\([^ ]*\).*/\1/p' <<< "$found")"
  origin="$(sed -n 's/.*audience=\([^ ]*\).*/\1/p' <<< "$found")"
  verify_infra PAUSED "$target" "$origin"
  gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  if ! verify_infra RUNNING "$target" "$origin"; then
    # The resume already happened. Report the observed state rather than let
    # an operator assume the queue is still PAUSED; do not pause blindly.
    echo "STAGED_QUEUE_PARTIAL_ACTIVATION observed_state=$(queue_state "$STAGE_QUEUE" || echo unknown) tasks=$(task_count "$STAGE_QUEUE" || echo unknown); post-resume verification failed." >&2
    exit 3
  fi
  echo "STAGED_QUEUE_ACTIVATED queue=$STAGE_QUEUE revision=$STAGED_REVISION target=$target"
}

drain_pause_command() {
  local proof
  [[ "$(queue_state "$STAGE_QUEUE")" == RUNNING ]] || refuse "drain-pause expects a RUNNING stage queue."
  barrier_proof drained || exit 1
  wait_for_empty_feeders || exit 1
  proof="$(barrier_proof drained)" || exit 1
  gcloud tasks queues pause "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  if ! barrier_proof drained >/dev/null \
    || [[ "$(task_count "$STAGE_QUEUE")" != 0 || "$(task_count "$ENTRY_QUEUE")" != 0 || "$(task_count "$DRAIN_QUEUE")" != 0 ]]; then
    # Work or an admission raced the pause: resume rather than strand a scan.
    gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
    echo "STAGED_QUEUE_PAUSE_COMPENSATED: work or an admission appeared during pause; queue resumed." >&2
    exit 1
  fi
  echo "STAGED_QUEUE_PAUSE_PROOF $proof"
  [[ "$(queue_state "$STAGE_QUEUE")" == PAUSED ]] || { echo "Stage queue did not report PAUSED." >&2; exit 1; }
  echo "STAGED_QUEUE_DRAINED_AND_PAUSED queue=$STAGE_QUEUE"
}

recover_command() {
  local count proof verified target origin first task
  [[ "$(queue_state "$STAGE_QUEUE")" == PAUSED ]] || refuse "recover expects a PAUSED stage queue."
  # Only NEW admissions must be impossible. Outstanding obligations are the
  # scans this exists to save, and their tagged worker revisions keep running
  # with whatever cohort they had: stage endpoints drain regardless of it.
  proof="$(barrier_proof closed)" || exit 1
  # Before anything is dispatched, every pending task must carry the delivery
  # identity the worker would accept: its own pinned, still-addressable source
  # tag, POST to /scan-batch or /scan-finalize, the fixed invoker OIDC identity,
  # the canonical audience and the 480s deadline. One bad task refuses all.
  describe_worker
  count="$(task_count "$STAGE_QUEUE")"
  mkdir -p "$WORK/stage-tasks"
  while read -r task; do
    [[ -n "$task" ]] || continue
    gcloud tasks describe "${task##*/}" --queue="$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" \
      --format=json > "$WORK/stage-tasks/$(printf '%s' "${task##*/}" | tr -c 'A-Za-z0-9_-' '_').json"
  done < <("${GUARD[@]}" names "$WORK/tasks-$STAGE_QUEUE.json")
  verified="$("${GUARD[@]}" recover-tasks "$WORK/service.json" "$WORK/tasks-$STAGE_QUEUE.json" \
    "$WORK/stage-tasks" "$WORK"/revision-*.json)"
  origin="$("${GUARD[@]}" origin "$WORK/service.json")"
  target="$("${GUARD[@]}" first-tag-url "$WORK/service.json" "$WORK/tasks-$STAGE_QUEUE.json" "$WORK/stage-tasks")"
  first="$("${GUARD[@]}" first-task "$WORK/tasks-$STAGE_QUEUE.json")"
  # Queue retry policy, bucket and resource-scoped IAM, still PAUSED.
  verify_infra PAUSED "$target" "$origin" "$first"
  if [[ "$count" == 0 ]]; then
    echo "STAGED_QUEUE_RECOVER_TASKS verified=0; no pending tasks, per-task identity unverified."
  else
    echo "STAGED_QUEUE_RECOVER_TASKS $verified"
  fi
  gcloud tasks queues resume "$STAGE_QUEUE" --project="$PROJECT" --location="$REGION" >/dev/null
  [[ "$(queue_state "$STAGE_QUEUE")" == RUNNING ]] || { echo "Stage queue did not report RUNNING." >&2; exit 1; }
  echo "STAGED_QUEUE_RECOVERED queue=$STAGE_QUEUE pending_tasks=$count $proof; run drain-pause once admitted scans are terminal."
}

case "$OPERATION" in
  status) status_command ;;
  activate) activate_command ;;
  drain-pause) drain_pause_command ;;
  recover) recover_command ;;
esac
