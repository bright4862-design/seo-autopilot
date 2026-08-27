import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '@/lib/AuthContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';

// Painted on every authenticated load before the app renders, so it uses the
// same paper/ink palette as the surface that replaces it rather than the
// template's slate.
const DefaultFallback = () => (
  <div
    className="fixed inset-0 flex items-center justify-center bg-paper"
    role="status"
    aria-live="polite"
  >
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-hairline border-t-ink" />
    <span className="sr-only">Loading your account…</span>
  </div>
);

export default function ProtectedRoute({ fallback = <DefaultFallback />, unauthenticatedElement }) {
  const { isAuthenticated, isLoadingAuth, authChecked, authError, checkUserAuth } = useAuth();

  useEffect(() => {
    if (!authChecked && !isLoadingAuth) {
      checkUserAuth();
    }
  }, [authChecked, isLoadingAuth, checkUserAuth]);

  if (isLoadingAuth || !authChecked) {
    return fallback;
  }

  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    }
    return unauthenticatedElement;
  }

  if (!isAuthenticated) {
    return unauthenticatedElement;
  }

  return <Outlet />;
}
