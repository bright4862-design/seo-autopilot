/** Optional large-scan evidence on worker input or persisted Base44 rows. */
export function repairImpactFields(fix = {}, { persisted = false } = {}) {
  const fields = {};
  const { affected_page_count: count, affected_page_count_is_lower_bound: lowerBound, template_impact_estimates: estimates } = fix;
  // Base44 materializes omitted scalar fields as null and the optional array
  // as empty. These defaults carried no evidence in the worker's payload.
  const hasDefaultedScalar = persisted && (count === null || lowerBound === null);
  const hasDefaultedEstimates = hasDefaultedScalar && Array.isArray(estimates) && estimates.length === 0;
  if (count !== undefined && !(persisted && count === null)) {
    if (!Number.isSafeInteger(count) || count < 0 || count > 500 || count < (fix.affected_pages || []).length) throw new Error("repair_impact_count_invalid");
    fields.affected_page_count = count;
  }
  if (lowerBound !== undefined && !(persisted && lowerBound === null)) {
    if (typeof lowerBound !== "boolean" || fields.affected_page_count === undefined) throw new Error("repair_impact_lower_bound_invalid");
    fields.affected_page_count_is_lower_bound = lowerBound;
  }
  if (estimates !== undefined && !hasDefaultedEstimates && !(persisted && estimates === null)) {
    if (!Array.isArray(estimates) || estimates.length > 50) throw new Error("template_impact_estimates_invalid");
    const keys = ["route_pattern","observed_affected_count","checked_sample_count","inventory_count","estimated_affected_page_count","is_extrapolation","qualification"];
    fields.template_impact_estimates = estimates.map(row => {
      if (!row || Object.keys(row).length !== keys.length || !keys.every(key => Object.hasOwn(row,key))) throw new Error("template_impact_shape_invalid");
      if (typeof row.route_pattern !== "string" || !row.route_pattern.startsWith("/") || row.route_pattern.length > 1000 || typeof row.qualification !== "string" || !row.qualification.trim() || row.qualification.length > 1000 || row.is_extrapolation !== true) throw new Error("template_impact_qualification_invalid");
      if (![row.observed_affected_count,row.checked_sample_count,row.inventory_count,row.estimated_affected_page_count].every(n => Number.isSafeInteger(n) && n >= 0 && n <= 5000) || row.checked_sample_count < 3 || row.observed_affected_count !== row.checked_sample_count || row.inventory_count <= row.checked_sample_count || row.estimated_affected_page_count !== row.inventory_count) throw new Error("template_impact_evidence_invalid");
      return Object.fromEntries(keys.map(key => [key,row[key]]));
    });
  }
  return fields;
}
