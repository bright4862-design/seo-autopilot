export type ScanStatus = "queued" | "crawling" | "reviewing" | "complete" | "failed" | "cancelled";

export interface ScanSummary {
  scan_id: string;
  domain: string;
  status: ScanStatus;
  pages_found?: number;
  pages_crawled?: number;
  score?: number;
  created_at?: string;
  completed_at?: string;
  error_code?: string;
  error_message?: string;
}

export interface FixItem {
  id: string;
  title: string;
  priority?: string;
  severity?: string;
  why_it_matters?: string;
  what_to_change?: string;
  owner?: string;
  affected_pages?: string[];
}

export interface FixListResult {
  scan: ScanSummary;
  fixes: FixItem[];
}

export class FixListClient {
  constructor(
    private readonly baseUrl = process.env.FIXLIST_API_BASE_URL || "https://getfixlist.com",
    private readonly serviceToken = process.env.FIXLIST_API_TOKEN || ""
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("accept", "application/json");
    if (init.body) headers.set("content-type", "application/json");
    if (this.serviceToken) headers.set("authorization", `Bearer ${this.serviceToken}`);

    const response = await fetch(new URL(path, this.baseUrl), { ...init, headers });
    const text = await response.text();
    let body: unknown = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = { message: text }; }

    if (!response.ok) {
      const message = typeof body === "object" && body && "message" in body
        ? String((body as { message: unknown }).message)
        : `FixList API returned HTTP ${response.status}`;
      throw new Error(message);
    }
    return body as T;
  }

  startScan(domain: string): Promise<ScanSummary> {
    return this.request<ScanSummary>("/api/plugin/scans", {
      method: "POST",
      body: JSON.stringify({ domain, mode: "standard_150" })
    });
  }

  getScanStatus(scanId: string): Promise<ScanSummary> {
    return this.request<ScanSummary>(`/api/plugin/scans/${encodeURIComponent(scanId)}`);
  }

  getFixList(scanId: string): Promise<FixListResult> {
    return this.request<FixListResult>(`/api/plugin/scans/${encodeURIComponent(scanId)}/fixlist`);
  }

  listScans(domain?: string): Promise<{ scans: ScanSummary[] }> {
    const qs = domain ? `?domain=${encodeURIComponent(domain)}` : "";
    return this.request<{ scans: ScanSummary[] }>(`/api/plugin/scans${qs}`);
  }

  compareScans(scanA: string, scanB: string): Promise<unknown> {
    return this.request(`/api/plugin/compare`, {
      method: "POST",
      body: JSON.stringify({ scan_a: scanA, scan_b: scanB })
    });
  }
}
