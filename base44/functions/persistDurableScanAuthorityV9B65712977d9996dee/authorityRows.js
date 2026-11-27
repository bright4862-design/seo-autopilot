export function authorityRowsFromSnapshot(snapshot, {
  fixListId,
  ownerUserId,
  proof,
} = {}) {
  const owner = { owner_user_id: String(ownerUserId || snapshot?.owner_user_id || "") };
  return {
    scanRun: {
      ...snapshot.scan,
      status: "complete",
      status_detail: "",
      fix_list_id: String(fixListId || ""),
      authority_seal_version: snapshot.version,
      authority_sealed_at: snapshot.sealed_at,
      authority_proof: String(proof || "").toLowerCase(),
    },
    fixList: {
      scan_run_id: snapshot.scan_id,
      project_id: snapshot.project_id,
      ...snapshot.fix_list,
      authority_proof: String(proof || "").toLowerCase(),
      ...owner,
    },
    fixItems: snapshot.recommendations.map((fix) => ({
      fix_list_id: String(fixListId || ""),
      scan_run_id: snapshot.scan_id,
      project_id: snapshot.project_id,
      ...fix,
      authority_proof: String(proof || "").toLowerCase(),
      ...owner,
    })),
  };
}

export function missingAuthorityFixRows(desiredRows, existingRows) {
  const existingIds = new Set((existingRows || []).map((row) => String(row?.fix_id || "")).filter(Boolean));
  return (desiredRows || []).filter((row) => !existingIds.has(String(row?.fix_id || "")));
}
