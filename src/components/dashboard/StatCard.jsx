import React from "react";

export default function StatCard({ icon: Icon, label, value, color = "blue", subtitle }) {
  const colorMap = {
    blue: "bg-blue-50 text-blue-600",
    green: "bg-green-50 text-green-600",
    amber: "bg-amber-50 text-amber-600",
    purple: "bg-purple-50 text-purple-600",
    red: "bg-red-50 text-red-600",
    cyan: "bg-cyan-50 text-cyan-600",
  };

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 hover:shadow-md hover:shadow-gray-100 transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg ${colorMap[color]} flex items-center justify-center`}>
          <Icon className="w-4 h-4" />
        </div>
        <span className="text-2xl font-bold text-gray-900">{value}</span>
      </div>
      <p className="text-sm font-medium text-gray-600">{label}</p>
      {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  );
}