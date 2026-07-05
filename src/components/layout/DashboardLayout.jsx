import React, { useEffect, useMemo, useState } from "react";
import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { flushQueuedEvents } from "@/lib/analytics";
import { ChevronLeft } from "lucide-react";
import MobileBottomNav from "@/components/layout/MobileBottomNav";

const navItems = [
  { label: "Fix List", path: "/dashboard" },
  { label: "Scan Website", path: "/crawl-status" },
  { label: "Website Improvements", path: "/developer" },
  { label: "Scan Report", path: "/reports" },
  { label: "Billing", path: "/billing" },
];

const pageTitles = {
  "/dashboard": "Fix List",
  "/crawl-status": "Scan Website",
  "/issues": "Issue Details",
  "/metadata": "Search Details",
  "/redirects": "Redirects",
  "/canonicals": "Preferred Pages",
  "/js-rendering": "Website Rendering",
  "/competitors": "Competitor Opportunities",
  "/developer": "Website Improvements",
  "/reports": "Scan Report",
  "/assistant": "AI Assistant",
  "/billing": "Billing",
  "/admin": "Admin",
};

function NavLink({ item, active }) {
  return (
    <Link
      to={item.path}
      className={`block rounded-xl px-4 py-3 text-[15px] font-medium transition-colors duration-200 ${active ? "bg-slate-100 text-slate-950" : "text-slate-500 hover:bg-slate-50 hover:text-slate-950"}`}
    >
      {item.label}
    </Link>
  );
}

export default function DashboardLayout() {
  const [isAdmin, setIsAdmin] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    flushQueuedEvents();
    base44.auth.me().then((user) => setIsAdmin(user?.role === "admin")).catch(() => {});
  }, []);

  const handleLogout = () => base44.auth.logout("/");

  const title = useMemo(() => pageTitles[location.pathname] || "SEO Autopilot", [location.pathname]);
  const showBack = location.pathname !== "/dashboard";

  return (
    <div className="min-h-screen bg-[#F7F8FA] text-slate-950 dark:bg-slate-950 dark:text-white">
      <aside className="fixed left-0 top-0 hidden h-screen w-64 border-r border-slate-200/70 bg-white lg:block dark:border-slate-800 dark:bg-slate-950">
        <div className="flex h-full flex-col">
          <div className="px-6 pb-6 pt-7">
            <Link to="/dashboard" className="block">
              <div className="text-[15px] font-semibold tracking-tight text-slate-950 dark:text-white">SEO Autopilot</div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">Website SEO assistant</div>
            </Link>
          </div>

          <nav className="space-y-1 px-3">
            {navItems.map((item) => (
              <NavLink key={item.path} item={item} active={location.pathname === item.path} />
            ))}
          </nav>

          <div className="mt-auto space-y-1 border-t border-slate-100 p-3 dark:border-slate-800">
            {isAdmin && (
              <Link
                to="/admin"
                className={`block rounded-xl px-4 py-3 text-[15px] font-medium transition-colors duration-200 ${location.pathname === "/admin" ? "bg-slate-100 text-slate-950 dark:bg-slate-900 dark:text-white" : "text-slate-500 hover:bg-slate-50 hover:text-slate-950 dark:hover:bg-slate-900 dark:hover:text-white"}`}
              >
                Admin
              </Link>
            )}
            <button onClick={handleLogout} className="block min-h-11 w-full rounded-xl px-4 py-3 text-left text-[15px] font-medium text-slate-500 transition-colors duration-200 hover:bg-slate-50 hover:text-slate-950 dark:hover:bg-slate-900 dark:hover:text-white">
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex min-h-14 items-center border-b border-slate-200/70 bg-white/90 px-4 pt-[env(safe-area-inset-top)] backdrop-blur lg:hidden dark:border-slate-800 dark:bg-slate-950/90">
          {showBack ? (
            <button aria-label="Go back" onClick={() => navigate(-1)} className="mr-2 flex min-h-11 min-w-11 items-center justify-center rounded-full text-slate-600 transition-colors duration-200 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-900">
              <ChevronLeft className="h-5 w-5" />
            </button>
          ) : null}
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-950 dark:text-white">{title}</p>
            <p className="truncate text-xs text-slate-500">SEO Autopilot</p>
          </div>
        </header>

        <main className="min-h-screen pb-[calc(env(safe-area-inset-bottom)+5.75rem)] lg:pb-0">
          <Outlet />
        </main>
      </div>

      <MobileBottomNav />
    </div>
  );
}