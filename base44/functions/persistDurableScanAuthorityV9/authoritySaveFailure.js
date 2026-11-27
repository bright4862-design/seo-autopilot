// Base44 packages are deployed independently. Keep this diagnostic limited to
// fixed categories and numeric HTTP status. SDK messages can contain row data.
export function authoritySaveFailure(stage, error) {
  const status = error?.status ?? error?.response?.status;
  if (Number.isInteger(status) && status >= 400 && status <= 599) {
    return { stage, failure_type: "upstream_http", upstream_status: status };
  }

  const message = error instanceof Error && typeof error.message === "string" ? error.message : "";
  const contracts = [
    [/^Missing-H1 comparison /, "comparison_evidence"],
    [/^(published (identity|priority) |canonical repair contract )/, "repair_evidence"],
    [/^(Persisted )?Stage3 /, "stage3_delivery"],
    [/^geo_readiness_contract$/, "geo_readiness"],
    [/^(repair_impact_|template_impact_)/, "repair_impact"],
  ];
  const contract = contracts.find(([pattern]) => pattern.test(message));
  if (contract) return { stage, failure_type: contract[1] };
  if (error instanceof TypeError) return { stage, failure_type: "type_error" };
  if (error instanceof RangeError) return { stage, failure_type: "range_error" };
  return { stage, failure_type: "unexpected_error" };
}
