import React, { useEffect, useMemo, useState } from "react";
import { base44 } from "@/api/base44Client";

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4">
      <p className="text-2xl font-semibold text-slate-950">{value}</p>
      <p className="mt-1 text-sm text-slate-500">{label}</p>
    </div>
  );
}

export default function AdminAnalytics() {
  const [events, setEvents] = useState([]);
  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const [eventRows, userRows, projectRows] = await Promise.all([
        base44.entities.AnalyticsEvent.list("-created_at", 200),
        base44.entities.User.list(),
        base44.entities.BusinessProject.list("-created_date", 200),
      ]);
      setEvents(eventRows);
      setUsers(userRows);
      setProjects(projectRows);
      setLoading(false);
    };
    load();
  }, []);

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const projectById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);

  const count = (name) => events.filter((event) => event.event_name === name).length;
  const countAny = (names) => events.filter((event) => names.includes(event.event_name)).length;

  if (loading) return <div className="p-8 text-center text-sm text-slate-400">Loading analytics…</div>;

  const stats = [
    { label: "Total users", value: users.length },
    { label: "Scans started", value: count("scan_started") },
    { label: "Scans completed", value: count("scan_completed") },
    { label: "Reports exported", value: count("report_exported") },
    { label: "Recommendations opened", value: count("recommendation_opened") },
    { label: "Help requests submitted", value: countAny(["contact_submitted", "cleanup_requested"]) },
    { label: "Cleanup requests", value: count("cleanup_requested") },
    { label: "Waitlist joins", value: count("waitlist_joined") },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => <Stat key={stat.label} label={stat.label} value={stat.value} />)}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-950">Recent events</h2>
          <p className="mt-1 text-sm text-slate-500">Internal product activity only.</p>
        </div>
        {events.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">No analytics events yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70">
                  <th className="px-4 py-3 text-left font-medium text-slate-500">Date</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-500">User</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-500">Event</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-500">Project</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-500">Page</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 50).map((event) => {
                  const user = userById.get(event.owner_user_id);
                  const project = projectById.get(event.project_id);
                  return (
                    <tr key={event.id} className="border-b border-slate-50 last:border-b-0">
                      <td className="whitespace-nowrap px-4 py-3 text-slate-600">{new Date(event.created_at || event.created_date).toLocaleString()}</td>
                      <td className="px-4 py-3 text-slate-600">{user?.email || "—"}</td>
                      <td className="px-4 py-3 font-medium text-slate-950">{event.event_name}</td>
                      <td className="px-4 py-3 text-slate-600">{project?.business_name || "—"}</td>
                      <td className="px-4 py-3 text-slate-500">{event.page || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}