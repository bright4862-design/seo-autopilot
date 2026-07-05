import React from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { CreditCard, FileText, ListChecks, Search, Wrench } from "lucide-react";

const items = [
  { label: "Fixes", path: "/dashboard", icon: ListChecks },
  { label: "Scan", path: "/crawl-status", icon: Search },
  { label: "Improve", path: "/developer", icon: Wrench },
  { label: "Report", path: "/reports", icon: FileText },
  { label: "Billing", path: "/billing", icon: CreditCard },
];

export default function MobileBottomNav() {
  const location = useLocation();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200/80 bg-white/90 px-2 pb-[calc(env(safe-area-inset-bottom)+0.35rem)] pt-2 backdrop-blur-xl lg:hidden dark:border-slate-800 dark:bg-slate-950/90">
      <div className="mx-auto grid max-w-md grid-cols-5 gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path;

          return (
            <Link
              key={item.path}
              to={item.path}
              className="relative flex min-h-12 flex-col items-center justify-center rounded-2xl px-1 py-1.5 text-xs font-medium text-slate-500 transition-colors duration-200 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 dark:text-slate-400 dark:hover:text-white"
            >
              {active && (
                <motion.span
                  layoutId="mobile-nav-active"
                  className="absolute inset-0 rounded-2xl bg-blue-50 dark:bg-blue-950/60"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
              <span className="relative z-10 flex flex-col items-center gap-1">
                <Icon className={active ? "h-4 w-4 text-blue-600" : "h-4 w-4"} />
                <span className={active ? "text-blue-600" : ""}>{item.label}</span>
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}