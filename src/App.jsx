import { Toaster } from "@/components/ui/toaster";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClientInstance } from "@/lib/query-client";
import {
  BrowserRouter as Router,
  Route,
  Routes,
  Navigate,
} from "react-router-dom";

import PageNotFound from "./lib/PageNotFound";
import { AuthProvider, useAuth } from "@/lib/AuthContext";
import UserNotRegisteredError from "@/components/UserNotRegisteredError";
import ProtectedRoute from "@/components/ProtectedRoute";
import ScrollToTop from "./components/ScrollToTop";

// Auth pages
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

// Public pages
import Landing from "@/pages/Landing";

// App pages
import Onboarding from "@/pages/Onboarding";
import FixList from "@/pages/FixList";
import Billing from "@/pages/Billing";

import DashboardLayout from "@/components/layout/DashboardLayout";

const AuthenticatedApp = () => {
  const {
    isLoadingAuth,
    isLoadingPublicSettings,
    authError,
    navigateToLogin,
  } = useAuth();

  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  if (authError) {
    if (authError.type === "user_not_registered") {
      return <UserNotRegisteredError />;
    }

    if (authError.type === "auth_required") {
      navigateToLogin();
      return null;
    }
  }

  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      {/* Protected */}
      <Route
        element={
          <ProtectedRoute
            unauthenticatedElement={<Navigate to="/login" replace />}
          />
        }
      >
        <Route element={<DashboardLayout />}>
          {/* Main visible pages */}
          <Route path="/dashboard" element={<FixList />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/billing" element={<Billing />} />

          {/* Old/hidden routes redirected so they do not 404 */}
          <Route path="/scan" element={<Navigate to="/onboarding" replace />} />
          <Route
            path="/scan-website"
            element={<Navigate to="/onboarding" replace />}
          />
          <Route
            path="/start-review"
            element={<Navigate to="/onboarding" replace />}
          />
          <Route
            path="/crawl-status"
            element={<Navigate to="/onboarding" replace />}
          />

          <Route path="/reports" element={<Navigate to="/dashboard" replace />} />
          <Route path="/issues" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/website-improvements"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/metadata"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/redirects"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/canonicals"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/js-rendering"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/competitors"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/developer"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/assistant"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route path="/admin" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Route>

      <Route path="*" element={<PageNotFound />} />
    </Routes>
  );
};

function App() {
  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <ScrollToTop />
          <AuthenticatedApp />
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AuthProvider>
  );
}

export default App;