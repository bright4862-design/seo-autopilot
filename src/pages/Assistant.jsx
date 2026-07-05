import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import { trackEvent } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import MessageBubble from "@/components/agent/MessageBubble";
import {
  Send,
  Plus,
  MessageSquare,
  Loader2,
  Bot,
  Sparkles,
  AlertTriangle,
} from "lucide-react";

const AGENT_NAME = "seo_assistant";

const SUGGESTIONS = [
  "What should I do first?",
  "Explain my recommendations in simple language.",
  "Which items may need help?",
  "Write a short action plan for my website.",
];

function getStatusLabel(status) {
  if (status === "auto_fixed") return "Prepared";
  if (status === "needs_approval") return "Needs review";
  if (status === "needs_developer") return "May need help";
  if (status === "approved") return "Approved";
  if (status === "completed") return "Completed";
  return "Recommended";
}

function getPriorityLabel(priority) {
  if (priority === "critical" || priority === "high") return "High impact";
  if (priority === "medium") return "Medium impact";
  return "Lower impact";
}

function compactIssue(issue) {
  return {
    title: issue.issue_title,
    page: issue.page_url,
    status: getStatusLabel(issue.status),
    priority: getPriorityLabel(issue.priority),
    category: issue.customer_category,
    what_we_found: issue.plain_english_explanation,
    why_it_matters: issue.why_it_matters,
    recommended_next_step: issue.ai_recommendation || issue.recommended_value,
    affected_pages: issue.affected_pages || [],
  };
}

function buildAssistantContext({ project, issues, improvements, insights, reports }) {
  const prepared = issues.filter((issue) => issue.status === "auto_fixed");
  const needsReview = issues.filter((issue) => issue.status === "needs_approval");
  const mayNeedHelp = issues.filter(
    (issue) => issue.status === "needs_developer" || issue.requires_developer
  );

  return {
    instruction:
      "Answer as SEO Autopilot's plain-English SEO assistant for a small business owner. Use the user's actual scan data below. Do not use technical jargon unless you explain it. Do not promise rankings. Do not say anything was fixed or published. Use calm, simple, Apple-like language. Keep answers practical and step-by-step.",
    project: project
      ? {
          business_name: project.business_name,
          website_url: project.website_url,
          business_type: project.business_type,
          city: project.city,
          seo_score: project.seo_score,
          last_scan: project.last_crawl_at,
        }
      : null,
    counts: {
      prepared: prepared.length,
      needs_review: needsReview.length,
      may_need_help: mayNeedHelp.length,
      total_recommendations: issues.length,
    },
    top_recommendations: issues.slice(0, 10).map(compactIssue),
    website_improvements: improvements.slice(0, 8).map((item) => ({
      title: item.title,
      description: item.description,
      priority: item.priority,
      suggested_package: item.recommended_package,
      business_impact: item.business_impact,
    })),
    competitor_opportunities: insights.slice(0, 8).map((item) => ({
      title: item.insight_title,
      explanation: item.explanation,
      recommended_action: item.recommended_action,
      impact: item.impact,
    })),
    latest_reports: reports.slice(0, 3).map((report) => ({
      summary: report.summary,
      next_steps: report.next_steps,
      seo_score: report.seo_score,
    })),
  };
}

export default function Assistant() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const [project, setProject] = useState(null);
  const [issues, setIssues] = useState([]);
  const [improvements, setImprovements] = useState([]);
  const [insights, setInsights] = useState([]);
  const [reports, setReports] = useState([]);

  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingContext, setLoadingContext] = useState(true);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const messagesEndRef = useRef(null);

  const assistantContext = useMemo(
    () => buildAssistantContext({ project, issues, improvements, insights, reports }),
    [project, issues, improvements, insights, reports]
  );

  useEffect(() => {
    trackEvent("assistant_opened");
    loadInitialData();
  }, []);

  useEffect(() => {
    if (!activeId) return;

    let unsubscribe;

    try {
      const conversation = base44.agents.getConversation(activeId);
      setMessages(conversation?.messages || []);

      unsubscribe = base44.agents.subscribeToConversation(activeId, (data) => {
        setMessages(data?.messages || []);
      });
    } catch (err) {
      console.warn("Could not subscribe to conversation.", err);
    }

    return () => {
      if (typeof unsubscribe === "function") unsubscribe();
    };
  }, [activeId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const loadInitialData = async () => {
    await Promise.all([loadConversations(), loadProjectContext()]);
  };

  const loadConversations = async () => {
    setLoadingConversations(true);

    try {
      const list = await base44.agents.listConversations({
        agent_name: AGENT_NAME,
      });

      setConversations(list || []);

      if (list?.length > 0) {
        setActiveId(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load conversations.", err);
      setError("Could not load assistant conversations.");
    } finally {
      setLoadingConversations(false);
    }
  };

  const loadProjectContext = async () => {
    setLoadingContext(true);

    try {
      const user = await base44.auth.me();
      const activeProjectId = window.localStorage.getItem("active_project_id");
      let activeProject = null;

      if (activeProjectId) {
        try {
          activeProject = await base44.entities.BusinessProject.get(activeProjectId);
        } catch {}
      }

      if (!activeProject) {
        const projects = await base44.entities.BusinessProject.list("-last_crawl_at", 10);
        activeProject =
          projects.find(
            (item) => item.owner_user_id === user.id || item.created_by_id === user.id
          ) ||
          projects[0] ||
          null;
      }

      if (!activeProject) {
        setProject(null);
        setIssues([]);
        setImprovements([]);
        setInsights([]);
        setReports([]);
        return;
      }

      setProject(activeProject);
      window.localStorage.setItem("active_project_id", activeProject.id);

      const [issueData, improvementData, insightData, reportData] = await Promise.all([
        base44.entities.SeoIssue.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.DeveloperRecommendation.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.CompetitorInsight.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
        base44.entities.Report.filter({
          project_id: activeProject.id,
          owner_user_id: user.id,
        }),
      ]);

      const activeIssues = (issueData || []).filter(
        (issue) =>
          !["approved", "rejected", "completed"].includes(issue.status)
      );

      setIssues(activeIssues);
      setImprovements(improvementData || []);
      setInsights(insightData || []);
      setReports(reportData || []);
    } catch (err) {
      console.error("Failed to load assistant context.", err);
      setError("Could not load your website scan context.");
    } finally {
      setLoadingContext(false);
    }
  };

  const createConversation = async () => {
    setCreating(true);

    try {
      const conversation = await base44.agents.createConversation({
        agent_name: AGENT_NAME,
        metadata: {
          name: project?.business_name
            ? `${project.business_name} SEO help`
            : "SEO help",
          description: "Plain-English SEO assistance",
        },
      });

      setConversations((previous) => [conversation, ...previous]);
      setActiveId(conversation.id);

      return conversation;
    } catch (err) {
      console.error("Failed to create conversation.", err);
      setError("Could not start a new assistant conversation.");
      return null;
    } finally {
      setCreating(false);
    }
  };

  const getActiveConversation = async () => {
    if (activeId) {
      const existing = base44.agents.getConversation(activeId);
      if (existing) return existing;
      return { id: activeId };
    }

    return await createConversation();
  };

  const buildMessageWithContext = (content) => {
    return [
      content,
      "",
      "Website context for this answer:",
      "```json",
      JSON.stringify(assistantContext, null, 2),
      "```",
    ].join("\n");
  };

  const handleSend = async (text) => {
    const content = String(text ?? input).trim();

    if (!content || sending) return;

    setInput("");
    setSending(true);
    setError(null);

    try {
      let conversation = await getActiveConversation();

      if (!conversation?.id) {
        throw new Error("Could not start a conversation.");
      }

      const contextualMessage = buildMessageWithContext(content);

      await base44.agents.addMessage(conversation, {
        role: "user",
        content: contextualMessage,
      });

      trackEvent("assistant_message_sent", {
        conversation_id: conversation.id,
        message_length: content.length,
        has_project_context: Boolean(project),
        recommendation_count: issues.length,
      });
    } catch (err) {
      console.error("Failed to send message.", err);
      setError("Could not send your message. Please try again.");
      setInput(content);
    } finally {
      setSending(false);
    }
  };

  const hasProject = Boolean(project);
  const hasIssues = issues.length > 0;
  const isLoading = loadingConversations || loadingContext;

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto flex h-[calc(100vh-7rem)] w-full max-w-5xl flex-col px-5 py-8 sm:px-6 lg:py-10">
        <div className="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Plain-English help</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              Ask AI
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-slate-500">
              SEO Autopilot scans your website, reviews important pages, looks for competitor opportunities when possible, and prepares a simple Fix List.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button
              asChild
              variant="outline"
              className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50"
            >
              <Link to="/dashboard">View Fix List</Link>
            </Button>

            <Button
              onClick={createConversation}
              disabled={creating}
              className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
            >
              {creating ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              New chat
            </Button>
          </div>
        </div>

        {error && (
          <div className="mb-5 rounded-3xl border border-red-100 bg-white p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-red-500" />
              <p className="text-sm leading-6 text-slate-600">{error}</p>
            </div>
          </div>
        )}

        {!hasProject && !loadingContext && (
          <div className="mb-5 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-950">
              No website scan found yet.
            </p>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              Scan a website first so the assistant can answer using your actual recommendations.
            </p>
            <Button
              asChild
              className="mt-4 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
            >
              <Link to="/crawl-status">Scan Website</Link>
            </Button>
          </div>
        )}

        <div className="grid min-h-0 flex-1 gap-5 md:grid-cols-[240px_1fr]">
          <aside className="hidden min-h-0 rounded-3xl border border-slate-200/80 bg-white p-3 shadow-sm md:flex md:flex-col">
            <Button
              onClick={createConversation}
              disabled={creating}
              className="mb-3 rounded-full bg-blue-600 text-sm font-medium text-white shadow-none hover:bg-blue-700"
              size="sm"
            >
              {creating ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              New chat
            </Button>

            <div className="min-h-0 flex-1 overflow-y-auto space-y-1">
              {isLoading ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-slate-300" />
                </div>
              ) : conversations.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-slate-400">
                  No chats yet
                </p>
              ) : (
                conversations.map((conversation) => (
                  <button
                    key={conversation.id}
                    onClick={() => setActiveId(conversation.id)}
                    className={`flex w-full items-center gap-2 rounded-2xl px-3 py-2.5 text-left text-sm transition ${
                      activeId === conversation.id
                        ? "bg-slate-100 text-slate-950"
                        : "text-slate-500 hover:bg-slate-50 hover:text-slate-950"
                    }`}
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">
                      {conversation.metadata?.name || "SEO help"}
                    </span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <main className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
            {!activeId ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl bg-slate-100">
                  <Bot className="h-7 w-7 text-blue-600" />
                </div>

                <h2 className="text-lg font-semibold text-slate-950">
                  Ask about your website.
                </h2>

                <p className="mt-2 max-w-sm text-sm leading-6 text-slate-600">
                  I can explain your recommendations and turn them into simple next steps.
                </p>

                <Button
                  onClick={createConversation}
                  disabled={creating}
                  className="mt-6 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700"
                >
                  {creating ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  Start chat
                </Button>
              </div>
            ) : (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto p-5">
                  {messages.length === 0 && (
                    <div className="mx-auto max-w-2xl">
                      <div className="mb-5 rounded-3xl bg-slate-50 p-5">
                        <p className="text-sm font-medium text-slate-950">
                          {hasIssues
                            ? `${issues.length} recommendations loaded`
                            : "Ready to help"}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-slate-600">
                          {hasIssues
                            ? "Ask what to do first, what needs help, or how to explain a recommendation."
                            : "Ask a question, or scan your website to get more personalized answers."}
                        </p>
                      </div>

                      <p className="mb-3 text-sm text-slate-400">
                        Try one of these:
                      </p>

                      <div className="space-y-2">
                        {SUGGESTIONS.map((suggestion) => (
                          <button
                            key={suggestion}
                            onClick={() => handleSend(suggestion)}
                            disabled={sending}
                            className="block w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition hover:bg-slate-50"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-4">
                    {messages.map((message, index) => (
                      <MessageBubble key={index} message={message} />
                    ))}

                    {sending && (
                      <div className="flex items-center gap-2 text-sm text-slate-400">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Thinking…
                      </div>
                    )}

                    <div ref={messagesEndRef} />
                  </div>
                </div>

                <div className="border-t border-slate-100 p-3">
                  <div className="flex gap-2">
                    <Input
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          handleSend();
                        }
                      }}
                      placeholder="Ask what to do next…"
                      disabled={sending}
                      className="h-11 rounded-full border-slate-200 bg-slate-50 px-4 shadow-none focus-visible:ring-blue-600"
                    />

                    <Button
                      onClick={() => handleSend()}
                      disabled={sending || !input.trim()}
                      className="h-11 rounded-full bg-blue-600 px-4 text-white shadow-none hover:bg-blue-700"
                    >
                      {sending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}