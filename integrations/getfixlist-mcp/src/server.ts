import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { FixListClient } from "./fixlist-client.js";

const client = new FixListClient();

export function createServer() {
  const server = new McpServer(
    { name: "getfixlist", version: "0.1.0" },
    {
      instructions:
        "GetFixList provides authoritative Standard 150 technical SEO scans. Never invent scan evidence. Start scans only when the user asks. For completed scans, use get_fixlist before explaining findings. Preserve failed/access-limited states as failures rather than presenting partial evidence as a successful audit."
    }
  );

  server.registerTool("start_scan", {
    title: "Start a Standard 150 scan",
    description: "Start a real GetFixList Standard 150 scan for a website when the user explicitly asks to scan or audit it.",
    inputSchema: { domain: z.string().min(3).max(253) },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true }
  }, async ({ domain }) => {
    const scan = await client.startScan(domain);
    return {
      structuredContent: { scan },
      content: [{ type: "text", text: `Started Standard 150 scan ${scan.scan_id} for ${scan.domain}. Status: ${scan.status}.` }]
    };
  });

  server.registerTool("get_scan_status", {
    title: "Get scan status",
    description: "Check the current state and crawl counts for an existing GetFixList scan.",
    inputSchema: { scan_id: z.string().min(1) },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }
  }, async ({ scan_id }) => {
    const scan = await client.getScanStatus(scan_id);
    return {
      structuredContent: { scan },
      content: [{ type: "text", text: `Scan ${scan.scan_id} is ${scan.status}.` }]
    };
  });

  server.registerTool("get_fixlist", {
    title: "Get completed FixList",
    description: "Retrieve the authoritative completed FixList, including score, priorities, affected pages, explanations, and repair guidance.",
    inputSchema: { scan_id: z.string().min(1) },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }
  }, async ({ scan_id }) => {
    const result = await client.getFixList(scan_id);
    return {
      structuredContent: result,
      content: [{ type: "text", text: `Retrieved ${result.fixes.length} FixList items for scan ${result.scan.scan_id}.` }]
    };
  });

  server.registerTool("list_scans", {
    title: "List scan history",
    description: "List historical GetFixList scans, optionally filtered to one domain.",
    inputSchema: { domain: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }
  }, async ({ domain }) => {
    const result = await client.listScans(domain);
    return {
      structuredContent: result,
      content: [{ type: "text", text: `Found ${result.scans.length} historical scans${domain ? ` for ${domain}` : ""}.` }]
    };
  });

  server.registerTool("compare_scans", {
    title: "Compare two scans",
    description: "Compare two completed GetFixList scans to show improvements, regressions, resolved findings, and remaining work.",
    inputSchema: {
      scan_a: z.string().min(1),
      scan_b: z.string().min(1)
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }
  }, async ({ scan_a, scan_b }) => {
    const comparison = await client.compareScans(scan_a, scan_b);
    return {
      structuredContent: { comparison },
      content: [{ type: "text", text: `Compared scans ${scan_a} and ${scan_b}.` }]
    };
  });

  return server;
}
