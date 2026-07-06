import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import DashboardLayout from "@/components/layout/DashboardLayout";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

import FixList from "@/pages/FixList";
import Onboarding from "@/pages/Onboarding";
import Reports from "@/pages/Reports";
import Billing from "@/pages/Billing";

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

        {/* Main app */}
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<FixList />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/billing" element={<Billing />} />
        </Route>

        {/* Old route redirects */}
        <Route path="/fix-list" element={<Navigate to="/dashboard" replace />} />
        <Route path="/scan" element={<Navigate to="/onboarding" replace />} />
        <Route path="/crawl-status" element={<Navigate to="/onboarding" replace />} />
        <Route path="/seo-connections" element={<Navigate to="/reports" replace />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}