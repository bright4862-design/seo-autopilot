import React from 'react';

// A reachable auth-boundary screen, so it uses the same paper/ink palette and
// centred column as AuthLayout rather than the template's slate card.
const UserNotRegisteredError = () => {
  return (
    <div className="min-h-screen bg-paper text-ink antialiased">
      <div className="mx-auto max-w-[420px] px-6 pb-24">
        <div className="pt-7 text-[15px] font-semibold tracking-tight">FixList</div>

        <div className="mt-20">
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
            This account doesn&rsquo;t have access
          </h1>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink-muted">
            You are signed in, but this account isn&rsquo;t registered to use FixList.
          </p>
        </div>

        <div className="mt-8 border-t border-hairline-soft pt-5 text-[14px] leading-relaxed text-ink-muted">
          <p>If you think this is a mistake:</p>
          <ul className="mt-3 space-y-1.5">
            <li>Check that you signed in with the right email address.</li>
            <li>Log out and sign in again with that account.</li>
            <li>Contact support to ask for access.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default UserNotRegisteredError;
