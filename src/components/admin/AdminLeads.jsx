import React from "react";
import { base44 } from "@/api/base44Client";

const TYPE_LABELS = {
  waitlist: "Waitlist",
  cleanup: "Cleanup",
  custom_rebuild: "Custom Rebuild",
};

const STATUS_STYLES = {
  new: "bg-blue-100 text-blue-700",
  contacted: "bg-amber-100 text-amber-700",
  closed: "bg-gray-100 text-gray-600",
};

export default function AdminLeads({ leads, onStatusChange }) {
  const handleStatus = async (lead, status) => {
    await base44.entities.LeadRequest.update(lead.id, { status });
    onStatusChange(lead.id, status);
  };

  if (leads.length === 0) {
    return <div className="p-8 text-center text-gray-400">No lead requests yet</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[720px]">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            <th className="text-left font-medium text-gray-500 px-4 py-3">Name</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Email</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Website</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Type</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Plan</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Date</th>
            <th className="text-left font-medium text-gray-500 px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {leads.map(lead => (
            <tr key={lead.id} className="border-b border-gray-50 align-top">
              <td className="px-4 py-3 font-medium">{lead.name}</td>
              <td className="px-4 py-3 text-gray-600">{lead.email}</td>
              <td className="px-4 py-3"><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{lead.website_url || "—"}</code></td>
              <td className="px-4 py-3">
                <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">{TYPE_LABELS[lead.request_type] || lead.request_type}</span>
                {lead.message && <p className="text-xs text-gray-400 mt-1 max-w-[200px]">{lead.message}</p>}
              </td>
              <td className="px-4 py-3 text-gray-600">{lead.selected_plan || "—"}</td>
              <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{new Date(lead.created_at || lead.created_date).toLocaleDateString()}</td>
              <td className="px-4 py-3">
                <select
                  value={lead.status}
                  onChange={e => handleStatus(lead, e.target.value)}
                  className={`text-xs px-2 py-1 rounded-full border-0 cursor-pointer ${STATUS_STYLES[lead.status]}`}
                >
                  <option value="new">New</option>
                  <option value="contacted">Contacted</option>
                  <option value="closed">Closed</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}