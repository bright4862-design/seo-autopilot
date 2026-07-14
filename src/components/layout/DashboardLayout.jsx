import React from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

const navigationItems = [
  { name: "Dashboard", href: "/dashboard" },
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
      <header className="sticky top-0 z-40 border-b border-hairline-soft bg-paper/90 backdrop-blur-xl supports-[backdrop-filter]:bg-paper/80">
        <div className="mx-auto flex h-14 max-w-[680px] items-center gap-4 px-4 sm:px-6">
          <Link
            to="/dashboard"
            className="shrink-0 text-[15px] font-semibold tracking-tight text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink"
          >
            FixList
          </Link>

          <nav className="ml-auto flex min-w-0 items-center gap-3 overflow-x-auto whitespace-nowrap sm:gap-5" aria-label="Account navigation">
            {navigationItems.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`text-[12.5px] font-medium transition-colors sm:text-[13px] ${
                    active ? "text-ink" : "text-ink-faint hover:text-ink"
                  }`}
                >
                  {item.name}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={handleLogout}
              className="text-[12.5px] font-medium text-ink-faint transition-colors hover:text-ink sm:text-[13px]"
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
