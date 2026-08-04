import React from "react";
import { Link } from "react-router-dom";

export default function AuthLayout({ icon: Icon, title, subtitle, footer, children }) {
  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[420px] px-6 pb-24">
        <div className="pt-7">
          <Link to="/" className="text-[15px] font-semibold tracking-tight">
            FixList
          </Link>
        </div>

        <div className="mt-20">
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 text-[15px] text-ink-muted">{subtitle}</p>}
        </div>

        <div className="mt-8">{children}</div>

        {footer && (
          <p className="mt-8 border-t border-hairline-soft pt-5 text-[13px] text-ink-muted">{footer}</p>
        )}
      </div>
    </div>
  );
}