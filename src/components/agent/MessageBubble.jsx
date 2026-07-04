import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Loader2,
} from "lucide-react";

const statusConfig = {
  pending: { icon: Loader2, className: "text-gray-400 animate-spin", label: "Pending" },
  running: { icon: Loader2, className: "text-blue-500 animate-spin", label: "Running" },
  in_progress: { icon: Loader2, className: "text-blue-500 animate-spin", label: "In progress" },
  completed: { icon: CheckCircle2, className: "text-green-500", label: "Completed" },
  success: { icon: CheckCircle2, className: "text-green-500", label: "Done" },
  failed: { icon: AlertCircle, className: "text-red-500", label: "Failed" },
  error: { icon: AlertCircle, className: "text-red-500", label: "Error" },
};

const formatName = (name) =>
  (name || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function FunctionDisplay({ toolCall }) {
  const [expanded, setExpanded] = useState(false);
  const rawStatus = toolCall.status || "pending";
  const proj = toolCall.display_projection || {};

  let status = rawStatus;
  let failed = ["failed", "error"].includes(rawStatus);

  let results = toolCall.results;
  let parsedResults = results;
  if (typeof results === "string") {
    try { parsedResults = JSON.parse(results); } catch { parsedResults = results; }
  }
  if (parsedResults && typeof parsedResults === "object" && parsedResults.success === false) failed = true;
  if (typeof results === "string" && /error|failed/i.test(results)) failed = true;
  if (failed) status = "failed";

  const cfg = statusConfig[status] || statusConfig.pending;
  const hideDetails = proj.hide_details && proj.details_redacted;
  const label = failed
    ? proj.error_label || cfg.label
    : ["pending", "running", "in_progress"].includes(status)
      ? proj.active_label || cfg.label
      : proj.label || cfg.label;

  let args = toolCall.arguments_string;
  let parsedArgs = args;
  if (typeof args === "string") {
    try { parsedArgs = JSON.parse(args); } catch { parsedArgs = args; }
  }

  const Icon = cfg.icon;

  return (
    <div className="mt-2 border border-gray-100 rounded-lg bg-gray-50/60 text-xs">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-100/50 transition-colors"
      >
        {expanded ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
        <Icon className={`w-3.5 h-3.5 ${cfg.className}`} />
        <span className="font-medium text-gray-600">{formatName(toolCall.name)}</span>
        <span className={`ml-auto ${failed ? "text-red-500" : "text-gray-400"}`}>{label}</span>
      </button>
      {!hideDetails && expanded && (
        <div className="px-3 pb-3 space-y-2">
          {parsedArgs != null && (
            <div>
              <p className="text-gray-400 font-medium mb-1">Parameters</p>
              <pre className="bg-white border border-gray-100 rounded p-2 overflow-x-auto text-gray-600">{typeof parsedArgs === "string" ? parsedArgs : JSON.stringify(parsedArgs, null, 2)}</pre>
            </div>
          )}
          {parsedResults != null && (
            <div>
              <p className="text-gray-400 font-medium mb-1">Result</p>
              <pre className="bg-white border border-gray-100 rounded p-2 overflow-x-auto text-gray-600 max-h-48 overflow-y-auto">{typeof parsedResults === "string" ? parsedResults : JSON.stringify(parsedResults, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={`max-w-[85%] px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white rounded-2xl rounded-br-sm"
            : "bg-white border border-gray-100 rounded-2xl rounded-bl-sm"
        }`}
      >
        {message.content && (
          isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none text-gray-700">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )
        )}
        {message.tool_calls?.map((tc, idx) => (
          <FunctionDisplay key={idx} toolCall={tc} />
        ))}
      </div>
    </div>
  );
}