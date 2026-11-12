// One build-time selector for the customer scan function adapter and the
// executable Vite entry's public (non-secret) release marker. This is not a
// signed authority proof; it lets the release verifier reject a mismatched
// browser function generation even when the source SHA is correct.
export const SELECTED_SCAN_FUNCTION_GENERATION =
  import.meta.env?.VITE_SCAN_FUNCTION_GENERATION === 'V9' ? 'V9' : 'V8';

export const SELECTED_SCAN_ROUTE_MARKER =
  SELECTED_SCAN_FUNCTION_GENERATION === 'V9'
    ? 'FIXLIST_SELECTED_SCAN_ROUTES_V9_V1'
    : 'FIXLIST_SELECTED_SCAN_ROUTES_V8_V1';
