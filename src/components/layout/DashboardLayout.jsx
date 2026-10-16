import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";

const navigationItems = [
  { name: "Dashboard", href: "/dashboard" },
  { name: "New scan", href: "/onboarding" },
  { name: "Billing", href: "/billing" },
  { name: "Account", href: "/account" },
];

const focusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink";
const menuFocusRing =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ink";
// Tailwind's `sm` breakpoint: the direct links fit from here up.
const DESKTOP_NAVIGATION_QUERY = "(min-width: 640px)";

export default function DashboardLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const headerRef = useRef(null);
  const menuButtonRef = useRef(null);
  const menuPanelRef = useRef(null);
  const restoreFocusRef = useRef(false);
  const previousPathRef = useRef(location.pathname);

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

  const closeMenu = useCallback((restoreFocus) => {
    restoreFocusRef.current = restoreFocus;
    setMenuOpen(false);
  }, []);

  // Focus returns to the toggle only after the panel is hidden, so it never
  // lands on a link that is about to disappear.
  useEffect(() => {
    if (!menuOpen && restoreFocusRef.current) {
      restoreFocusRef.current = false;
      menuButtonRef.current?.focus();
    }
  }, [menuOpen]);

  // Back/forward and in-app redirects close the menu too, not only menu clicks.
  useEffect(() => {
    if (previousPathRef.current === location.pathname) return;
    previousPathRef.current = location.pathname;
    const panel = menuPanelRef.current;
    closeMenu(Boolean(panel && !panel.hidden && panel.contains(document.activeElement)));
  }, [location.pathname, closeMenu]);

  useEffect(() => {
    if (!menuOpen) return undefined;

    function handleKeyDown(event) {
      // Pull focus back only from the menu itself, never from the page below.
      if (event.key === "Escape") closeMenu(Boolean(headerRef.current?.contains(document.activeElement)));
    }
    function handlePointerDown(event) {
      if (!headerRef.current?.contains(event.target)) closeMenu(false);
    }
    const desktop = typeof window.matchMedia === "function" ? window.matchMedia(DESKTOP_NAVIGATION_QUERY) : null;
    function handleViewportChange(event) {
      if (event.matches) closeMenu(false);
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    desktop?.addEventListener?.("change", handleViewportChange);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
      desktop?.removeEventListener?.("change", handleViewportChange);
    };
  }, [menuOpen, closeMenu]);

  async function handleLogout() {
    closeMenu(false);
    try {
      await logout(false);
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      navigate("/login", { replace: true });
    }
  }

  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <header
        ref={headerRef}
        className="sticky top-0 z-40 border-b border-hairline-soft bg-paper/90 backdrop-blur-xl supports-[backdrop-filter]:bg-paper/80"
      >
        <div className="mx-auto flex h-14 max-w-[880px] items-center gap-4 px-4 sm:px-6">
          <Link
            to="/dashboard"
            className={`shrink-0 text-[15px] font-semibold tracking-tight text-ink ${focusRing}`}
          >
            FixList
          </Link>

          <nav className="ml-auto hidden items-center gap-5 whitespace-nowrap sm:flex" aria-label="Account navigation">
            {navigationItems.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-sm text-[13px] font-medium transition-colors ${focusRing} ${
                    active ? "text-ink" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {item.name}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={handleLogout}
              className={`rounded-sm text-[13px] font-medium text-ink-muted transition-colors hover:text-ink ${focusRing}`}
            >
              Log out
            </button>
          </nav>

          <button
            ref={menuButtonRef}
            type="button"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => (menuOpen ? closeMenu(false) : setMenuOpen(true))}
            className={`-mr-2 ml-auto inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium text-ink transition-colors hover:bg-ink/[0.04] sm:hidden ${focusRing}`}
          >
            {menuOpen ? <X aria-hidden="true" className="h-4 w-4" /> : <Menu aria-hidden="true" className="h-4 w-4" />}
            Menu
          </button>
        </div>

        <nav
          id={menuId}
          ref={menuPanelRef}
          hidden={!menuOpen}
          aria-label="Account navigation"
          className="border-t border-hairline-soft sm:hidden"
        >
          <ul className="mx-auto max-w-[880px] px-2 py-2">
            {navigationItems.map((item) => {
              const active = isActive(item.href);
              return (
                <li key={item.name}>
                  <Link
                    to={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => closeMenu(true)}
                    className={`flex min-h-11 items-center rounded-lg px-3 text-[15px] transition-colors ${menuFocusRing} ${
                      active ? "bg-ink/[0.04] font-semibold text-ink" : "font-medium text-ink-muted hover:bg-ink/[0.04] hover:text-ink"
                    }`}
                  >
                    {item.name}
                  </Link>
                </li>
              );
            })}
            <li className="mt-1 border-t border-hairline-soft pt-1">
              <button
                type="button"
                onClick={handleLogout}
                className={`flex min-h-11 w-full items-center rounded-lg px-3 text-left text-[15px] font-medium text-ink-muted transition-colors hover:bg-ink/[0.04] hover:text-ink ${menuFocusRing}`}
              >
                Log out
              </button>
            </li>
          </ul>
        </nav>
      </header>

      <main className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
