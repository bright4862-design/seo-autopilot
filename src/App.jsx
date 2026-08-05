import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import DashboardLayout from "@/components/layout/DashboardLayout";
import ProtectedRoute from "@/components/ProtectedRoute";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

import FixList from "@/pages/FixList";
import Onboarding from "@/pages/Onboarding";
import Billing from "@/pages/Billing";
import Assistant from "@/pages/Assistant";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public pages */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Authenticated app */}
        <Route
          element={
            <ProtectedRoute
              unauthenticatedElement={<Navigate to="/login" replace />}
            />
          }
        >
          <Route element={<DashboardLayout />}>
            <Route path="/dashboard" element={<FixList />} />
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/billing" element={<Billing />} />
          </Route>
        </Route>

        {/* Hidden / old pages */}
        <Route path="/reports" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/seo-connections"
          element={<Navigate to="/dashboard" replace />}
        />
        <Route path="/issues" element={<Navigate to="/dashboard" replace />} />
        <Route path="/fix-list" element={<Navigate to="/dashboard" replace />} />
        <Route path="/scan" element={<Navigate to="/onboarding" replace />} />
        <Route
          path="/crawl-status"
          element={<Navigate to="/onboarding" replace />}
        />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
