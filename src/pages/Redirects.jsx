import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { ArrowRightLeft, Download, CheckCircle2, XCircle, ExternalLink } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const exportFormats = [
  { value: "csv", label: "CSV" },
  { value: "htaccess", label: ".htaccess" },
  { value: "nginx", label: "Nginx" },
  { value: "wordpress", label: "WordPress Plugin" },
  { value: "instructions", label: "Developer Instructions" },
];

export default function Redirects() {
  const [redirects, setRedirects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exportFormat, setExportFormat] = useState("csv");

  useEffect(() => {
    const load = async () => {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      if (projects.length > 0) {
        const data = await base44.entities.RedirectRecommendation.filter({ project_id: projects[0].id });
        setRedirects(data);
      }
      setLoading(false);
    };
    load();
  }, []);

  const handleApprove = async (id) => {
    await base44.entities.RedirectRecommendation.update(id, { approval_status: "approved" });
    setRedirects(prev => prev.map(r => r.id === id ? { ...r, approval_status: "approved" } : r));
  };

  const handleReject = async (id) => {
    await base44.entities.RedirectRecommendation.update(id, { approval_status: "rejected" });
    setRedirects(prev => prev.map(r => r.id === id ? { ...r, approval_status: "rejected" } : r));
  };

  const handleExport = () => {
    const approved = redirects.filter(r => r.approval_status === "approved");
    let content = "";

    if (exportFormat === "csv") {
      content = "Source,Destination,Status Code,Reason\n" + approved.map(r => `${r.broken_url},${r.recommended_destination},${r.status_code},"${r.reason}"`).join("\n");
    } else if (exportFormat === "htaccess") {
      content = "# SEO Autopilot - Redirect Map\n" + approved.map(r => `Redirect 301 ${r.broken_url} ${r.recommended_destination}`).join("\n");
    } else if (exportFormat === "nginx") {
      content = "# SEO Autopilot - Nginx Redirects\n" + approved.map(r => `rewrite ^${r.broken_url}$ ${r.recommended_destination} permanent;`).join("\n");
    } else if (exportFormat === "wordpress") {
      content = "# SEO Autopilot - WordPress Redirect Plugin Format\n# Import this into Redirection or Safe Redirect Manager\n" + approved.map(r => `${r.broken_url},${r.recommended_destination}`).join("\n");
    } else {
      content = "SEO Autopilot - Redirect Instructions\n\n" + approved.map((r, i) => `${i + 1}. Redirect ${r.broken_url} → ${r.recommended_destination}\n   Reason: ${r.reason}\n   Status: ${r.status_code}`).join("\n\n");
    }

    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `redirects.${exportFormat === "csv" ? "csv" : "txt"}`;
    a.click();
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Redirect Map</h1>
          <p className="text-sm text-gray-500 mt-1">Broken URLs we found and where to redirect them</p>
        </div>
        <div className="flex gap-2">
          <Select value={exportFormat} onValueChange={setExportFormat}>
            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
            <SelectContent>
              {exportFormats.map(f => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={handleExport} disabled={redirects.filter(r => r.approval_status === "approved").length === 0}>
            <Download className="w-4 h-4 mr-2" /> Export
          </Button>
        </div>
      </div>

      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
        <p className="text-sm text-amber-800">
          <strong>Important:</strong> We never apply redirects automatically. Review each recommendation, approve it, then export the redirect map for your developer or CMS plugin.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        {redirects.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <ArrowRightLeft className="w-8 h-8 mx-auto mb-2 text-gray-300" />
            <p className="font-medium">No redirect recommendations yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/50">
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Broken URL</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3 hidden md:table-cell">Status</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Redirect To</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3 hidden lg:table-cell">Reason</th>
                  <th className="text-left font-medium text-gray-500 px-4 py-3">Confidence</th>
                  <th className="text-right font-medium text-gray-500 px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {redirects.map(r => (
                  <tr key={r.id} className="border-b border-gray-50">
                    <td className="px-4 py-3">
                      <code className="text-xs bg-red-50 text-red-600 px-1.5 py-0.5 rounded">{r.broken_url}</code>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="text-xs font-medium text-gray-600">{r.status_code}</span>
                    </td>
                    <td className="px-4 py-3">
                      <code className="text-xs bg-green-50 text-green-600 px-1.5 py-0.5 rounded">{r.recommended_destination}</code>
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <span className="text-xs text-gray-500">{r.reason}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs font-medium text-gray-600">{r.confidence_score}%</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {r.approval_status === "approved" ? (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">Approved</span>
                      ) : r.approval_status === "rejected" ? (
                        <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded-full">Rejected</span>
                      ) : (
                        <div className="flex gap-1 justify-end">
                          <Button size="sm" variant="ghost" className="h-7 text-green-600 hover:bg-green-50" onClick={() => handleApprove(r.id)}>
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-7 text-red-600 hover:bg-red-50" onClick={() => handleReject(r.id)}>
                            <XCircle className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}