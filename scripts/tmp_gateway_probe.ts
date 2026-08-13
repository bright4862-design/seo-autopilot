const response = await base44.functions.invoke("startStandardScanJob", {
  request_id: "scanreq_gatewayprobe_20260813_1239_01",
  idempotency_key: "scanreq_gatewayprobe_20260813_1239_01",
  scan_id: "6a7d9fb96027fde860ce0da4",
  scan_run_id: "6a7d9fb96027fde860ce0da4",
  website_url: "https://example.com/",
  submitted_url: "https://example.com/",
  normalized_domain: "example.com",
  scan_mode: "standard_150",
  business_name: "Dispatch Probe 2",
  cms_platform: "Custom",
});
console.log(JSON.stringify(response?.data ?? response));
