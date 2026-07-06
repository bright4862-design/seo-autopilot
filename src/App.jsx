import React from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  CreditCard,
  LogOut,
  Menu,
  Plug,
  Search,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const navigationItems = [
  { name: "Fix Pages", href: "/dashboard", icon: CheckCircle2 },
  { name: "Scan Website", href: "/onboarding", icon: Search },
  { name: "SEO Connections", href: "/reports", icon: Plug },
  { name: "Billing", href: "/billing", icon: CreditCard },
];

export default function DashboardLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = React.useState(false);

  function isActive(href) {
    if (href === "/dashboard") {
      return (
        location.pathname === "/dashboard" ||
        location.pathname === "/fix-list"
      );
    }

    if (href === "/reports") {
      return (
        location.pathname === "/reports" ||
        location.pathname === "/seo-connections"
      );
    }

    return location.pathname === href || location.pathname.startsWith(`${href}/`);
  }

  function handleLogout() {
    try {
      window.localStorage.removeItem("seo_autopilot:gsc_connection");
    } catch {
      // Ignore localStorage errors.
    }

    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <MobileHeader
        mobileOpen={mobileOpen}
        onToggle={() => setMobileOpen((value) => !value)}
      />

      <div className="flex">
        <aside className="hidden min-h-screen w-72 shrink-0 border-r border-slate-200 bg-white lg:block">
          <SidebarContent
            isActive={isActive}
            onNavigate={() => setMobileOpen(false)}
            onLogout={handleLogout}
          />
        </aside>

        {mobileOpen ? (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-slate-950/40"
              onClick={() => setMobileOpen(false)}
            />

            <aside className="relative h-full w-80 max-w-[85vw] border-r border-slate-200 bg-white shadow-xl">
              <SidebarContent
                isActive={isActive}
                onNavigate={() => setMobileOpen(false)}
                onLogout={handleLogout}
              />
            </aside>
          </div>
        ) : null}

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MobileHeader({ mobileOpen, onToggle }) {
  return (
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 lg:hidden">
      <Link to="/dashboard" className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-600 text-white">
          <CheckCircle2 className="h-5 w-5" />
        </div>

        <div>
          <div className="font-bold leading-tight text-slate-950">
            SEO Pilot
          </div>
          <div className="text-xs text-slate-500">Fix List</div>
        </div>
      </Link>

      <Button type="button" variant="outline" size="icon" onClick={onToggle}>
        {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>
    </header>
  );
}

function SidebarContent({ isActive, onNavigate, onLogout }) {
  return (
    <div className="flex h-full min-h-screen flex-col">
      <div className="border-b border-slate-100 p-6">
        <Link to="/dashboard" onClick={onNavigate} className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-white">
            <CheckCircle2 className="h-6 w-6" />
          </div>

          <div>
            <div className="text-lg font-bold leading-tight text-slate-950">
              SEO Pilot
            </div>
            <div className="text-sm text-slate-500">Autopilot dashboard</div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 space-y-2 p-4">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);

          return (
            <Link
              key={item.name}
              to={item.href}
              onClick={onNavigate}
              className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition ${
                active
                  ? "bg-slate-950 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
              }`}
            >
              <Icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-100 p-4">
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
        >
          <LogOut className="h-5 w-5" />
          Log out
        </button>
      </div>
    </div>
  );
}