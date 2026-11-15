// New staged workers sign this value in the completion envelope. An older
// pinned worker may omit it and let the caller use its historical timestamp.
export function stagedCompletionTime(scan, result, now = Date.now()) {
  const readyAt = result?.result_ready_at;
  if (scan?.pipeline_mode !== "staged" || readyAt === undefined) return "";

  const started = Date.parse(scan.started_at || scan.queued_at || scan.created_date || "");
  const ready = typeof readyAt === "string" ? Date.parse(readyAt) : NaN;
  if (!Number.isFinite(started) || !Number.isFinite(ready)
      || new Date(ready).toISOString() !== readyAt || ready < started
      || ready > now + 60_000) {
    throw new Error("Invalid staged completion timestamp");
  }
  return readyAt;
}
