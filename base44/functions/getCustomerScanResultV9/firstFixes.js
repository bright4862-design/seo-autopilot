/** Select a short, varied first screen from the server's existing priority order. */
const id = fix => String(fix?.fix_id || fix?.issue_id || fix?.id || "");
const root = fix => String(fix?.root_cause_id || fix?.raw_finding?.root_cause_id || fix?.rule || "");
const template = fix => String(fix?.template_key || fix?.page_template_family || fix?.raw_finding?.template_key || "");
const ownerCanDo = fix => ["you", "owner", "business_owner", "site_owner"].includes(String(fix?.who_can_do_this || fix?.who_does_it || fix?.implementation_owner || fix?.raw_finding?.implementation_owner || "").toLowerCase()) || String(fix?.difficulty || "").toLowerCase() === "easy";
const rank = fix => Number.isFinite(Number(fix?.canonical_action_rank)) && Number(fix?.canonical_action_rank) > 0 ? Number(fix.canonical_action_rank) : Number.MAX_SAFE_INTEGER;
const compatible = (fix, chosen) => !chosen.some(other => id(other) === id(fix) || (root(fix) && root(other) === root(fix)) || (template(fix) && template(other) === template(fix)));

const factorScore = fix => {
  const value = fix?.stage3_priority_factors?.priority_factor_score ?? fix?.raw_finding?.stage3_delivery?.priority_factors?.priority_factor_score;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

export function topFixIds(fixes = []) {
  const ordered = fixes.filter(fix => id(fix)).map((fix, index) => ({fix, index})).sort((a, b) => ((factorScore(b.fix) ?? -Infinity) - (factorScore(a.fix) ?? -Infinity)) || rank(a.fix) - rank(b.fix) || a.index - b.index).map(row => row.fix);
  const selected = [];
  for (const fix of ordered) {
    if (compatible(fix, selected)) selected.push(fix);
    if (selected.length === 3) break;
  }
  if (!selected.some(ownerCanDo)) {
    const owner = ordered.find(ownerCanDo);
    if (owner) {
      // The owner action takes one slot. Drop conflicting root/template cards,
      // then refill in priority order while preserving that actionable step.
      const withOwner = [owner, ...selected.filter(fix => compatible(fix, [owner]))].slice(0, 3);
      for (const fix of ordered) {
        if (withOwner.length === 3) break;
        if (compatible(fix, withOwner)) withOwner.push(fix);
      }
      selected.splice(0, selected.length, ...withOwner);
    }
  }
  return selected.sort((a, b) => ordered.indexOf(a) - ordered.indexOf(b)).map(id);
}

export function withFirstFixes(projection, run = {}) {
  if (run.page_cap !== undefined && (projection.authority_verified || projection.result_integrity_verified)) {
    return {...projection, top_fix_ids: topFixIds(projection.fixItems || [])};
  }
  return projection;
}
