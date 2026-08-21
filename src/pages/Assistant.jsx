import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import MessageBubble from "@/components/agent/MessageBubble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getActiveProject } from "@/lib/activeProject";
import { trackEvent } from "@/lib/analytics";
import { CUSTOMER_BOUNDARY_EVENT, clearCustomerAuthBoundary } from "@/lib/customerBrowserCache";
import {
  GROK_MAX_MESSAGE_LENGTH,
  conversationMatchesGrokScan,
  createGrokSendGuard,
  grokWorkspaceIdentity,
  grokWorkspaceMatches,
  normalizeGrokDomain,
  resolveActiveGrokConversationId,
  selectGrokConversationForScan,
  selectLatestAuthoritativeGrokScan,
  sortGrokMessages,
} from "@/lib/grokChat";
import {
  AlertTriangle,
  Bot,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  ShieldCheck,
} from "lucide-react";

const SUGGESTIONS = [
  "What should I do first?",
  "Explain the highest-impact recommendation in simple language.",
  "Which fixes can I safely do myself?",
  "Write a short action plan for this FixList.",
];

export default function Assistant() {
  const [project, setProject] = useState(null);
  const [scanRun, setScanRun] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const activeIdRef = useRef(null);
  const scanRunRef = useRef(null);
  const workspaceIdentityRef = useRef(null);
  const workspaceEpochRef = useRef(0);
  const messagesEndRef = useRef(null);
  const sendGuardRef = useRef(null);
  if (!sendGuardRef.current) sendGuardRef.current = createGrokSendGuard();

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeId) || null,
    [activeId, conversations]
  );
  const scanIdentity = scanRun
    ? `${scanRun.id}|${normalizeGrokDomain(scanRun.website_url)}|${scanRun.beta_revision_fingerprint}`
    : "";

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    scanRunRef.current = scanRun;
    workspaceIdentityRef.current = scanRun ? grokWorkspaceIdentity({ scanRun }) : null;
  }, [scanRun]);

  useEffect(() => {
    function clearCustomerWorkspace() {
      workspaceEpochRef.current += 1;
      workspaceIdentityRef.current = null;
      sendGuardRef.current.reset();
      setSending(false);
      setLoadingWorkspace(false);
      setLoadingMessages(false);
      setInput("");
      setError(null);
      clearWorkspace(setProject, setScanRun, setConversations, setActiveId, setMessages);
    }
    window.addEventListener(CUSTOMER_BOUNDARY_EVENT, clearCustomerWorkspace);
    return () => window.removeEventListener(CUSTOMER_BOUNDARY_EVENT, clearCustomerWorkspace);
  }, []);

  useEffect(() => {
    trackEvent("assistant_opened");
    let unsubscribe;
    try {
      unsubscribe = base44.entities.ScanRun.subscribe(() => {
        setRefreshToken((value) => value + 1);
      });
    } catch {
      // Refresh persistence still works without realtime subscriptions.
    }
    return () => {
      if (typeof unsubscribe === "function") unsubscribe();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspace() {
      const loadEpoch = workspaceEpochRef.current;
      setLoadingWorkspace(true);
      setError(null);
      try {
        const { user, project: activeProject } = await getActiveProject();
        if (cancelled || loadEpoch !== workspaceEpochRef.current) return;
        if (!user?.id || !activeProject?.id) {
          clearWorkspace(setProject, setScanRun, setConversations, setActiveId, setMessages);
          return;
        }

        const runs = await base44.entities.ScanRun.filter(
          { project_id: activeProject.id, owner_user_id: user.id },
          "-completed_at",
          30
        );
        const selectedScan = selectLatestAuthoritativeGrokScan(runs, activeProject);
        if (cancelled || loadEpoch !== workspaceEpochRef.current) return;

        setProject(activeProject);
        if (!selectedScan) {
          setScanRun(null);
          setConversations([]);
          setActiveId(null);
          setMessages([]);
          return;
        }

        const loadedConversations = await base44.entities.GrokConversation.filter(
          {
            project_id: activeProject.id,
            scan_run_id: selectedScan.id,
            owner_user_id: user.id,
            normalized_domain: normalizeGrokDomain(selectedScan.website_url),
            release_fingerprint: selectedScan.beta_revision_fingerprint,
          },
          "-last_message_at",
          50
        );
        if (cancelled || loadEpoch !== workspaceEpochRef.current) return;

        const validConversations = (loadedConversations || []).filter((conversation) => (
          conversationMatchesGrokScan(conversation, selectedScan)
        ));
        const current = validConversations.find((conversation) => conversation.id === activeIdRef.current);
        const candidate = selectGrokConversationForScan(validConversations, selectedScan);
        const nextActiveId = resolveActiveGrokConversationId({
          currentConversation: current,
          candidateConversation: candidate,
          scanRun: selectedScan,
        });
        const previousScan = scanRunRef.current;
        if (!previousScan || previousScan.id !== selectedScan.id) setMessages([]);
        setScanRun(selectedScan);
        setConversations(validConversations);
        setActiveId(nextActiveId);
      } catch (loadError) {
        if (cancelled || loadEpoch !== workspaceEpochRef.current) return;
        if (clearCustomerAuthBoundary(loadError)) return;
        console.error("Could not load Grok workspace.", loadError);
        clearWorkspace(setProject, setScanRun, setConversations, setActiveId, setMessages);
        setError("Grok is unavailable right now. Your scans and FixLists are unchanged.");
      } finally {
        if (!cancelled && loadEpoch === workspaceEpochRef.current) setLoadingWorkspace(false);
      }
    }

    loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  useEffect(() => {
    let cancelled = false;
    const loadEpoch = workspaceEpochRef.current;
    if (!activeId || !scanRun) {
      setMessages([]);
      setLoadingMessages(false);
      return undefined;
    }

    const conversation = conversations.find((item) => item.id === activeId);
    if (!conversationMatchesGrokScan(conversation, scanRun)) {
      setActiveId(null);
      setMessages([]);
      return undefined;
    }

    setMessages([]);
    setLoadingMessages(true);
    fetchConversationMessages(conversation, scanRun)
      .then((storedMessages) => {
        if (!cancelled && loadEpoch === workspaceEpochRef.current) setMessages(storedMessages);
      })
      .catch((loadError) => {
        if (cancelled || loadEpoch !== workspaceEpochRef.current) return;
        if (clearCustomerAuthBoundary(loadError)) return;
        console.error("Could not load Grok messages.", loadError);
        setMessages([]);
        setError("This Grok conversation could not be loaded. Your FixList is unchanged.");
      })
      .finally(() => {
        if (!cancelled && loadEpoch === workspaceEpochRef.current) setLoadingMessages(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeId, conversations, scanIdentity]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const startNewConversation = () => {
    if (sending || !scanRun) return;
    setActiveId(null);
    setMessages([]);
    setInput("");
    setError(null);
  };

  const handleSend = async (value) => {
    const content = String(value ?? input).trim();
    if (!content || !scanRun || content.length > GROK_MAX_MESSAGE_LENGTH) return;
    if (!sendGuardRef.current.tryAcquire()) return;

    const workspaceAtSend = grokWorkspaceIdentity({ scanRun });
    const conversationAtSend = conversationMatchesGrokScan(activeConversation, scanRun)
      ? activeConversation
      : null;
    const optimisticId = `pending_${Date.now()}`;
    setInput("");
    setSending(true);
    setError(null);
    setMessages((previous) => [
      ...previous.filter((message) => message.id !== optimisticId),
      { id: optimisticId, role: "user", content, sequence: Number.MAX_SAFE_INTEGER },
    ]);

    try {
      const payload = { message: content, scan_id: scanRun.id };
      if (conversationAtSend?.id) payload.conversation_id = conversationAtSend.id;
      const result = await base44.functions.invoke("grokChat", payload);
      assertCurrentGrokWorkspace(workspaceAtSend, workspaceIdentityRef.current);
      const returnedConversationId = String(result?.conversation_id || "");

      if (!returnedConversationId) {
        setMessages((previous) => previous.filter((message) => message.id !== optimisticId));
        setError(result?.error || "Grok is unavailable right now. Please try again.");
        return;
      }

      const returnedConversation = await base44.entities.GrokConversation.get(returnedConversationId);
      assertCurrentGrokWorkspace(workspaceAtSend, workspaceIdentityRef.current);
      if (!conversationMatchesGrokScan(returnedConversation, scanRun)) {
        throw new Error("Grok returned a conversation for a different scan.");
      }

      const nextConversations = mergeConversations(conversations, returnedConversation)
        .filter((conversation) => conversationMatchesGrokScan(conversation, scanRun));
      const storedMessages = await fetchConversationMessages(returnedConversation, scanRun);
      assertCurrentGrokWorkspace(workspaceAtSend, workspaceIdentityRef.current);
      setConversations(nextConversations);
      setActiveId(returnedConversation.id);
      setMessages(storedMessages);

      trackEvent("assistant_message_sent", {
        conversation_id: returnedConversation.id,
        scan_run_id: scanRun.id,
        message_length: content.length,
        grok_chat_version: result?.grok_chat_version || "",
      });

      if (result?.success !== true) {
        setError(result?.error || "Grok is temporarily unavailable. Your conversation is still saved.");
      }
    } catch (sendError) {
      if (
        sendError?.code === "stale_grok_workspace"
        || !grokWorkspaceMatches(workspaceAtSend, workspaceIdentityRef.current)
      ) {
        setMessages((previous) => previous.filter((message) => message.id !== optimisticId));
        return;
      }
      if (clearCustomerAuthBoundary(sendError)) return;
      console.error("Could not send Grok message.", sendError);
      const preservedId = resolveActiveGrokConversationId({
        currentConversation: conversationAtSend,
        candidateConversation: null,
        scanRun,
      });
      setActiveId(preservedId);
      if (preservedId && conversationAtSend) {
        try {
          setMessages(await fetchConversationMessages(conversationAtSend, scanRun));
        } catch {
          setMessages((previous) => previous.filter((message) => message.id !== optimisticId));
        }
      } else {
        setMessages([]);
      }
      setError("Grok could not send that message. Your current FixList conversation was not switched.");
    } finally {
      sendGuardRef.current.release();
      if (grokWorkspaceMatches(workspaceAtSend, workspaceIdentityRef.current)) setSending(false);
    }
  };

  const hasProject = Boolean(project);
  const hasAuthoritativeScan = Boolean(scanRun);
  const canSend = hasAuthoritativeScan && !loadingWorkspace && !loadingMessages && !sending;
  const domain = normalizeGrokDomain(scanRun?.website_url);

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="mx-auto flex h-[calc(100vh-7rem)] w-full max-w-5xl flex-col px-5 py-8 sm:px-6 lg:py-10">
        <div className="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row">
          <div>
            <p className="text-sm font-medium text-blue-600">Grok in FixList</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Ask Grok</h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-slate-500">
              Ask questions about your latest authoritative FixList. Grok can explain and plan, but it never changes your website or marks fixes complete.
            </p>
            {domain && (
              <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                <ShieldCheck className="h-3.5 w-3.5 text-blue-600" />
                Grounded in {domain}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button asChild variant="outline" className="rounded-full border-slate-200 bg-white px-5 text-sm font-medium text-slate-700 shadow-none hover:bg-slate-50">
              <Link to="/dashboard">View Fix List</Link>
            </Button>
            <Button onClick={startNewConversation} disabled={!hasAuthoritativeScan || sending} className="rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">
              <Plus className="mr-2 h-4 w-4" />
              New chat
            </Button>
          </div>
        </div>

        {error && (
          <div className="mb-5 rounded-3xl border border-amber-100 bg-white p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500" />
              <p className="text-sm leading-6 text-slate-600">{error}</p>
            </div>
          </div>
        )}

        {!loadingWorkspace && !hasAuthoritativeScan && (
          <div className="mb-5 rounded-3xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-950">
              {hasProject ? "No authoritative FixList scan is ready." : "No website project was found."}
            </p>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              Complete a successful Standard 150 scan first. Grok does not use provisional, limited, failed, or mismatched scan data.
            </p>
            <Button asChild className="mt-4 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-none hover:bg-blue-700">
              <Link to="/crawl-status">Scan Website</Link>
            </Button>
          </div>
        )}

        <div className="grid min-h-0 flex-1 gap-5 md:grid-cols-[240px_1fr]">
          <aside className="hidden min-h-0 rounded-3xl border border-slate-200/80 bg-white p-3 shadow-sm md:flex md:flex-col">
            <Button onClick={startNewConversation} disabled={!hasAuthoritativeScan || sending} className="mb-3 rounded-full bg-blue-600 text-sm font-medium text-white shadow-none hover:bg-blue-700" size="sm">
              <Plus className="mr-2 h-4 w-4" />
              New chat
            </Button>

            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
              {loadingWorkspace ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-slate-300" />
                </div>
              ) : conversations.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-slate-400">No saved Grok chats for this scan</p>
              ) : conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => setActiveId(conversation.id)}
                  className={`flex w-full items-center gap-2 rounded-2xl px-3 py-2.5 text-left text-sm transition ${
                    activeId === conversation.id
                      ? "bg-slate-100 text-slate-950"
                      : "text-slate-500 hover:bg-slate-50 hover:text-slate-950"
                  }`}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{conversation.title || `${domain} Grok help`}</span>
                </button>
              ))}
            </div>
          </aside>

          <main className="flex min-h-0 flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm">
            {!hasAuthoritativeScan ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                {loadingWorkspace ? (
                  <Loader2 className="h-7 w-7 animate-spin text-blue-600" />
                ) : (
                  <Bot className="h-8 w-8 text-slate-300" />
                )}
                <h2 className="mt-4 text-lg font-semibold text-slate-950">Grok needs an authoritative scan.</h2>
                <p className="mt-2 max-w-sm text-sm leading-6 text-slate-600">Your browser never sends scan evidence or chat history. The secure backend loads both from your Base44 records.</p>
              </div>
            ) : (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto p-5">
                  {loadingMessages ? (
                    <div className="flex h-full items-center justify-center">
                      <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
                    </div>
                  ) : messages.length === 0 ? (
                    <div className="mx-auto max-w-2xl">
                      <div className="mb-5 rounded-3xl bg-slate-50 p-5">
                        <p className="text-sm font-medium text-slate-950">Authoritative FixList loaded</p>
                        <p className="mt-1 text-sm leading-6 text-slate-600">Ask what to do first, how to implement a recommendation, or which work needs extra care.</p>
                      </div>
                      <p className="mb-3 text-sm text-slate-400">Try one of these:</p>
                      <div className="space-y-2">
                        {SUGGESTIONS.map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            onClick={() => handleSend(suggestion)}
                            disabled={!canSend}
                            className="block w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
                    </div>
                  )}

                  {sending && (
                    <div className="mt-4 flex items-center gap-2 text-sm text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Grok is thinking…
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                <div className="border-t border-slate-100 p-3">
                  <div className="flex gap-2">
                    <Input
                      value={input}
                      onChange={(event) => setInput(event.target.value.slice(0, GROK_MAX_MESSAGE_LENGTH))}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          handleSend();
                        }
                      }}
                      maxLength={GROK_MAX_MESSAGE_LENGTH}
                      placeholder="Ask Grok what to do next…"
                      disabled={!canSend}
                      className="h-11 rounded-full border-slate-200 bg-slate-50 px-4 shadow-none focus-visible:ring-blue-600"
                    />
                    <Button onClick={() => handleSend()} disabled={!canSend || !input.trim()} className="h-11 rounded-full bg-blue-600 px-4 text-white shadow-none hover:bg-blue-700">
                      {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    </Button>
                  </div>
                  <div className="mt-2 flex items-center justify-between px-2 text-[11px] text-slate-400">
                    <span>Advice only — Grok cannot apply fixes.</span>
                    <span>{input.length}/{GROK_MAX_MESSAGE_LENGTH}</span>
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

function assertCurrentGrokWorkspace(expected, current) {
  if (!grokWorkspaceMatches(expected, current)) {
    throw Object.assign(new Error("The signed-in owner, project, scan, domain, or release changed."), {
      code: "stale_grok_workspace",
    });
  }
}

async function fetchConversationMessages(conversation, scanRun) {
  if (!conversationMatchesGrokScan(conversation, scanRun)) return [];
  const user = await base44.auth.me();
  const records = await base44.entities.GrokMessage.filter(
    {
      conversation_id: conversation.id,
      owner_user_id: user.id,
      project_id: scanRun.project_id,
      scan_run_id: scanRun.id,
      normalized_domain: normalizeGrokDomain(scanRun.website_url),
      release_fingerprint: scanRun.beta_revision_fingerprint,
    },
    "created_date",
    200
  );
  return sortGrokMessages(records).filter((message) => ["user", "assistant"].includes(message.role));
}

function mergeConversations(conversations, conversation) {
  return [conversation, ...(conversations || []).filter((item) => item.id !== conversation.id)];
}

function clearWorkspace(setProject, setScanRun, setConversations, setActiveId, setMessages) {
  setProject(null);
  setScanRun(null);
  setConversations([]);
  setActiveId(null);
  setMessages([]);
}
