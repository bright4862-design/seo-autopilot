import React, { useEffect, useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { BarChart3, FileText, ListChecks, LogOut, Menu, Search, Shield, Wrench, X } from "lucide-react";

const navItems = [
  { label: "Fix List", path: "/dashboard", icon: ListChecks },
  { label: "Scan Website", path: "/crawl-status", icon: Search },
  { label: "Competitor Gaps", path: "/competitors", icon: BarChart3 },
  { label: "Website Improvements", path: "/developer", icon: Wrench },
  { label: "Scan Report", path: "/reports", icon: FileText },
  { label: "Billing", path: "/billing", icon: FileText },
];

function NavLink({ item, active, onClick }) {
  return (
    <Link
      to={item.path}
      onClick={onClick}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition hover:bg-slate-50 hover:text-slate-950 ${active ? "bg-slate-100 text-blue-600" : "text-slate-500"}`}
    >
      <item.icon className="h-4 w-4" />
      {item.label}
    </Link>
  );
}

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const location = useLocation();

  useEffect(() => {
    base44.auth.me().then((user) => setIsAdmin(user?.role === "admin")).catch(() => {});
  }, []);

  const handleLogout = () => base44.auth.logout("/");

  const sidebar = (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-20 items-center gap-3 px-6">
        <Link to="/dashboard" onClick={() => setSidebarOpen(false)} className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-950 text-sm font-semibold text-white">S</div>
          <span className="text-base font-semibold tracking-tight text-slate-950">SEO Autopilot</span>
        </Link>
      </div>

      <nav className="space-y-1 px-3">
        {navItems.map((item) => (
          <NavLink key={item.path} item={item} active={location.pathname === item.path} onClick={() => setSidebarOpen(false)} />
        ))}
      </nav>

      <div className="mt-auto space-y-1 border-t border-slate-200/70 p-3">
        {isAdmin && (
          <Link
            to="/admin"
            onClick={() => setSidebarOpen(false)}
            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition hover:bg-slate-50 hover:text-slate-950 ${location.pathname === "/admin" ? "bg-slate-100 text-blue-600" : "text-slate-500"}`}
          >
            <Shield className="h-4 w-4" />
            Admin
          </Link>
        )}
        <button onClick={handleLogout} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-950">
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <aside className="fixed left-0 top-0 hidden h-screen w-64 border-r border-slate-200/70 bg-white lg:block">{sidebar}</aside>

      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="Close menu" className="absolute inset-0 bg-slate-950/20" onClick={() => setSidebarOpen(false)} />
          <aside className="relative h-full w-72 border-r border-slate-200/70 bg-white shadow-xl">
            <button aria-label="Close menu" onClick={() => setSidebarOpen(false)} className="absolute right-4 top-4 rounded-full p-2 text-slate-500 hover:bg-slate-50">
              <X className="h-4 w-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center border-b border-slate-200/70 bg-white/85 px-4 backdrop-blur lg:hidden">
          <button aria-label="Open menu" onClick={() => setSidebarOpen(true)} className="rounded-full p-2 text-slate-600 hover:bg-slate-50">
            <Menu className="h-5 w-5" />
          </button>
        </header>
        <main className="min-h-screen">
          <Outlet />
        </main>
      </div>
    </div>
  );
}