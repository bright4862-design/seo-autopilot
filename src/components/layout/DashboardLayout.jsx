import React from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";
import { CheckCircle2, Search, CreditCard } from "lucide-react";

const navigationItems = [
  {
    name: "Fix Pages",
    href: "/dashboard",
    icon: CheckCircle2,
  },
  {
    name: "Scan Website",
    href: "/onboarding",
    icon: Search,
  },
  {
    name: "Billing",
    href: "/billing",
    icon: CreditCard,
  },
];

export default function DashboardLayout() {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-slate-50">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-slate-200 bg-white lg:block">
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-200 px-6 py-5">
            <div className="text-lg font-bold text-slate-950">
              SEO Autopilot
            </div>
            <div className="mt-1 text-xs text-slate-500">
              Scan. Review. Fix.
            </div>
          </div>

          <nav className="flex-1 space-y-1 px-3 py-4">
            {navigationItems.map((item) => {
              const Icon = item.icon;
              const isActive =
                location.pathname === item.href ||
                location.pathname.startsWith(`${item.href}/`);

              return (
                <NavLink
                  key={item.href}
                  to={item.href}
                  className={[
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition",
                    isActive
                      ? "bg-blue-50 text-blue-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                  ].join(" ")}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.name}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur lg:hidden">
          <div className="px-4 py-3">
            <div className="text-base font-bold text-slate-950">
              SEO Autopilot
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2">
              {navigationItems.map((item) => {
                const Icon = item.icon;
                const isActive =
                  location.pathname === item.href ||
                  location.pathname.startsWith(`${item.href}/`);

                return (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    className={[
                      "flex items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-medium transition",
                      isActive
                        ? "bg-blue-50 text-blue-700"
                        : "bg-slate-100 text-slate-600",
                    ].join(" ")}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span>{item.name}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        </header>

        <main className="px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}