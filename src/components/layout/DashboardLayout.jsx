import React from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

const navigationItems = [
  { name: "FixList", href: "/dashboard" },
  { name: "New scan", href: "/onboarding" },
  { name: "Billing", href: "/billing" },
];

export default function DashboardLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  function isActive(href) {
    if (href === "/dashboard") {
      return (
        location.pathname === "/dashboard" ||
        location.pathname === "/fix-list" ||
        location.pathname === "/issues"
      );
    }

    if (href === "/onboarding") {
      return (
        location.pathname === "/onboarding" ||
        location.pathname === "/scan" ||
        location.pathname === "/crawl-status"
      );
    }

    return location.pathname === href || location.pathname.startsWith(`${href}/`);
  }

  function handleLogout() {
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <header className="border-b border-hairline-soft">
        <div className="mx-auto flex h-14 max-w-[680px] items-center justify-between px-6">
          <Link to="/dashboard" className="text-[15px] font-semibold tracking-tight text-ink">
            FixList
          </Link>

          <nav className="flex items-center gap-5">
            {navigationItems.map((item) => (
              <Link
                key={item.name}
                to={item.href}
                className={`text-[13px] font-medium transition-colors ${
                  isActive(item.href) ? "text-ink" : "text-ink-faint hover:text-ink"
                }`}
              >
                {item.name}
              </Link>
            ))}
            <button
              type="button"
              onClick={handleLogout}
              className="text-[13px] font-medium text-ink-faint transition-colors hover:text-ink"
            >
              Log out
            </button>
          </nav>
        </div>
      </header>

      <main className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
