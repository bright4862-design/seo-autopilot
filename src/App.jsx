import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';
import ProtectedRoute from '@/components/ProtectedRoute';
import ScrollToTop from './components/ScrollToTop';

// Auth pages
import Login from '@/pages/Login';
import Register from '@/pages/Register';
import ForgotPassword from '@/pages/ForgotPassword';
import ResetPassword from '@/pages/ResetPassword';

// Public pages
import Landing from '@/pages/Landing';

// App pages
import Onboarding from '@/pages/Onboarding';
import Dashboard from '@/pages/Dashboard';
import CrawlStatus from '@/pages/CrawlStatus';
import Issues from '@/pages/Issues';
import Metadata from '@/pages/Metadata';
import Redirects from '@/pages/Redirects';
import Canonicals from '@/pages/Canonicals';
import JsRendering from '@/pages/JsRendering';
import Competitors from '@/pages/Competitors';
import Developer from '@/pages/Developer';
import Reports from '@/pages/Reports';
import Billing from '@/pages/Billing';
import Admin from '@/pages/Admin';
import Assistant from '@/pages/Assistant';

import DashboardLayout from '@/components/layout/DashboardLayout';

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin } = useAuth();

  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    } else if (authError.type === 'auth_required') {
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
      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/crawl-status" element={<CrawlStatus />} />
          <Route path="/issues" element={<Issues />} />
          <Route path="/metadata" element={<Metadata />} />
          <Route path="/redirects" element={<Redirects />} />
          <Route path="/canonicals" element={<Canonicals />} />
          <Route path="/js-rendering" element={<JsRendering />} />
          <Route path="/competitors" element={<Competitors />} />
          <Route path="/developer" element={<Developer />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/admin" element={<Admin />} />
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
  )
}

export default App