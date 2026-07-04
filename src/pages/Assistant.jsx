import React, { useState, useEffect, useRef } from "react";
import { base44 } from "@/api/base44Client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import MessageBubble from "@/components/agent/MessageBubble";
import { Send, Plus, MessageSquare, Loader2, Sparkles, Bot } from "lucide-react";

const AGENT_NAME = "seo_assistant";

const SUGGESTIONS = [
  "Explain my most critical SEO issues",
  "What developer recommendations do I have?",
  "Give me step-by-step actions for my top developer recommendation",
  "What does 'canonical' mean and why does it matter?",
];

export default function Assistant() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (!activeId) return;
    const conv = base44.agents.getConversation(activeId);
    setMessages(conv?.messages || []);
    const unsubscribe = base44.agents.subscribeToConversation(activeId, (data) => {
      setMessages(data.messages || []);
    });
    return () => unsubscribe();
  }, [activeId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadConversations = async () => {
    setLoadingConvs(true);
    try {
      const list = await base44.agents.listConversations({ agent_name: AGENT_NAME });
      setConversations(list);
      if (list.length > 0) setActiveId(list[0].id);
    } catch (e) {
      console.error("Failed to load conversations", e);
    }
    setLoadingConvs(false);
  };

  const handleNewConversation = async () => {
    setCreating(true);
    try {
      const conv = await base44.agents.createConversation({
        agent_name: AGENT_NAME,
        metadata: { name: "New conversation", description: "SEO assistance" },
      });
      setConversations([conv, ...conversations]);
      setActiveId(conv.id);
    } catch (e) {
      console.error("Failed to create conversation", e);
    }
    setCreating(false);
  };

  const handleSend = async (text) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    if (!activeId) {
      await handleNewConversation();
    }
    setInput("");
    setSending(true);
    try {
      const conv = base44.agents.getConversation(activeId) || { id: activeId };
      await base44.agents.addMessage(conv, { role: "user", content });
    } catch (e) {
      console.error("Failed to send message", e);
    }
    setSending(false);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-blue-600" /> SEO Assistant
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Plain-English explanations of your issues and step-by-step action plans
          </p>
        </div>
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* Conversations sidebar */}
        <div className="hidden md:flex flex-col w-60 bg-white rounded-2xl border border-gray-100 p-3 flex-shrink-0">
          <Button
            onClick={handleNewConversation}
            disabled={creating}
            className="gradient-primary text-white border-0 mb-3"
            size="sm"
          >
            {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
            New Chat
          </Button>
          <div className="flex-1 overflow-y-auto space-y-1">
            {loadingConvs ? (
              <div className="flex justify-center py-6">
                <Loader2 className="w-5 h-5 text-gray-300 animate-spin" />
              </div>
            ) : conversations.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-6">No conversations yet</p>
            ) : (
              conversations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setActiveId(c.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                    activeId === c.id ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{c.metadata?.name || "Conversation"}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Chat panel */}
        <div className="flex-1 flex flex-col bg-white rounded-2xl border border-gray-100 min-h-0">
          {!activeId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
              <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center mb-4">
                <Bot className="w-7 h-7 text-blue-600" />
              </div>
              <h3 className="font-semibold text-gray-800 mb-1">Ask me anything about your SEO</h3>
              <p className="text-sm text-gray-500 mb-6 max-w-sm">
                I can explain your audit findings in plain English and break down developer fixes into simple steps.
              </p>
              <Button onClick={handleNewConversation} disabled={creating} className="gradient-primary text-white border-0">
                {creating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                Start a Conversation
              </Button>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {messages.length === 0 && (
                  <div className="space-y-2">
                    <p className="text-sm text-gray-400 mb-3">Try one of these:</p>
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => handleSend(s)}
                        disabled={sending}
                        className="block w-full text-left text-sm px-4 py-3 rounded-xl border border-gray-100 hover:border-blue-200 hover:bg-blue-50/50 text-gray-700 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
                {messages.map((m, idx) => (
                  <MessageBubble key={idx} message={m} />
                ))}
                <div ref={messagesEndRef} />
              </div>
              <div className="border-t border-gray-100 p-3 flex gap-2">
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Ask about an issue or a developer recommendation..."
                  disabled={sending}
                  className="h-11"
                />
                <Button
                  onClick={() => handleSend()}
                  disabled={sending || !input.trim()}
                  className="gradient-primary text-white border-0 h-11 px-4"
                >
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}