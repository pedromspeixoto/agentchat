import { useState, useEffect, useRef, useCallback } from "react";
import type { Session, Message, ChatItem, Artifact, ArtifactKind } from "./types";
import { getSessions, getMessages, getArtifacts, deleteSession, streamChat } from "./api";
import type { ToolCall } from "./api";

function toTextItem(m: Message): Extract<ChatItem, { type: "text" }> {
  return { id: m.id, type: "text", role: m.role, content: m.content, created_at: m.created_at, chat_id: m.chat_id };
}

function formatDate(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Artifact helpers ──────────────────────────────────────────────────────────

const KIND_META: Record<ArtifactKind, { label: string; color: string; icon: React.ReactNode }> = {
  csv: {
    label: "CSV",
    color: "#00e676",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>
      </svg>
    ),
  },
  pdf: {
    label: "PDF",
    color: "#ff5252",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/><line x1="8" y1="9" x2="10" y2="9"/>
      </svg>
    ),
  },
  json: {
    label: "JSON",
    color: "#40c4ff",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
      </svg>
    ),
  },
  txt: {
    label: "TXT",
    color: "#9e9e9e",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>
      </svg>
    ),
  },
  xlsx: {
    label: "XLSX",
    color: "#69f0ae",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>
      </svg>
    ),
  },
  other: {
    label: "FILE",
    color: "#757575",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
      </svg>
    ),
  },
};

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const meta = KIND_META[artifact.kind] ?? KIND_META['other'];
  return (
    <div className="artifact-card">
      <div className="artifact-icon" style={{ color: meta.color, background: `${meta.color}14` }}>
        {meta.icon}
      </div>
      <div className="artifact-info">
        <div className="artifact-name" title={artifact.name}>{artifact.name}</div>
        <div className="artifact-meta">
          <span className="artifact-badge" style={{ color: meta.color, borderColor: `${meta.color}30`, background: `${meta.color}10` }}>
            {meta.label}
          </span>
          {artifact.size !== undefined && <span>{formatBytes(artifact.size)}</span>}
          <span>{formatDate(artifact.created_at)}</span>
        </div>
      </div>
      {artifact.url && (
        <a className="artifact-download" href={artifact.url} download={artifact.name} title="Download">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
        </a>
      )}
    </div>
  );
}

function ArtifactsPanel({ artifacts, onClose }: { artifacts: Artifact[]; onClose: () => void }) {
  return (
    <div className="canvas-panel-inner">
      <div className="canvas-header">
        <div className="canvas-header-left">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
          </svg>
          <span>Artifacts</span>
          {artifacts.length > 0 && <span className="canvas-count">{artifacts.length}</span>}
        </div>
        <button className="canvas-close" onClick={onClose} title="Close artifacts panel">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div className="canvas-body">
        {artifacts.length === 0 ? (
          <div className="canvas-empty">
            <div className="canvas-empty-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="12" y1="18" x2="12" y2="12"/>
                <line x1="9" y1="15" x2="15" y2="15"/>
              </svg>
            </div>
            <p className="canvas-empty-title">No artifacts yet</p>
            <p className="canvas-empty-desc">Ask AgentChat to generate a file or document and it will appear here.</p>
          </div>
        ) : (
          <div className="artifact-list">
            {artifacts.map((a) => <ArtifactCard key={a.id} artifact={a} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Artifact inline card (appears in chat feed when an artifact is created) ───

function ArtifactInlineCard({ artifact, onView }: { artifact: Artifact; onView: () => void }) {
  const meta = KIND_META[artifact.kind] ?? KIND_META['other'];
  return (
    <div className="artifact-inline-card">
      <div className="artifact-inline-shimmer" />
      <div className="artifact-inline-icon" style={{ color: meta.color, background: `${meta.color}14` }}>
        {meta.icon}
      </div>
      <div className="artifact-inline-body">
        <div className="artifact-inline-label">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Artifact ready
        </div>
        <div className="artifact-inline-name">{artifact.name}</div>
        <div className="artifact-inline-meta">
          <span className="artifact-badge" style={{ color: meta.color, borderColor: `${meta.color}30`, background: `${meta.color}10` }}>
            {meta.label}
          </span>
          {artifact.size !== undefined && <span>{formatBytes(artifact.size)}</span>}
        </div>
      </div>
      <div className="artifact-inline-actions">
        <button className="artifact-inline-view" onClick={onView}>View</button>
        {artifact.url && (
          <a className="artifact-inline-dl" href={artifact.url} download={artifact.name} title="Download">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </a>
        )}
      </div>
    </div>
  );
}

// ── Tool call card ────────────────────────────────────────────────────────────

function ToolCallCard({ name, input }: { name: string; input: unknown }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="tool-card">
      <button className="tool-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="tool-card-left">
          <svg className="tool-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          <span className="tool-label">Tool call</span>
          <code className="tool-name">{name}</code>
        </div>
        <svg className={`tool-chevron${expanded ? " open" : ""}`} width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {expanded && (
        <div className="tool-card-body">
          <pre className="tool-json">{JSON.stringify(input, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function ChatItemView({ item }: { item: ChatItem }) {
  if (item.type === "tool_call") {
    return <div className="tool-row"><ToolCallCard name={item.name} input={item.input} /></div>;
  }
  return (
    <div className={`message ${item.role}`}>
      <div className="message-role">
        {item.role === "user" ? <><span className="role-dot user-dot" />You</> : <><span className="role-dot ai-dot" />AgentChat</>}
      </div>
      <div className="message-bubble">{item.content}</div>
    </div>
  );
}

function ThinkingDots() {
  return <span className="thinking-dots"><span /><span /><span /></span>;
}

// ── Delete modal ──────────────────────────────────────────────────────────────

function DeleteModal({ title, onConfirm, onCancel }: { title: string; onConfirm: () => void; onCancel: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
          </svg>
        </div>
        <h3 className="modal-title">Delete conversation?</h3>
        <p className="modal-desc">
          <span className="modal-session-name">"{title}"</span> will be permanently deleted and cannot be recovered.
        </p>
        <div className="modal-actions">
          <button className="modal-cancel" onClick={onCancel}>Cancel</button>
          <button className="modal-confirm" onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [chatItems, setChatItems] = useState<ChatItem[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [chatStarted, setChatStarted] = useState(false);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Always-current ref for activeId — read by stream callbacks to avoid stale closures
  const activeIdRef = useRef<string | null>(null);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);

  // In-flight streams keyed by session ID — lets background streams run without aborting
  const streamsRef = useRef<Map<string, AbortController>>(new Map());

  useEffect(() => { getSessions().then(setSessions).catch(console.error); }, []);

  useEffect(() => {
    if (!activeId) { setChatItems([]); setArtifacts([]); return; }
    getMessages(activeId).then((msgs) => setChatItems(msgs.map(toTextItem))).catch(console.error);
    getArtifacts(activeId).then(setArtifacts).catch(console.error);
  }, [activeId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatItems, streamingText]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const goToLanding = () => {
    setActiveId(null);
    setChatItems([]);
    setArtifacts([]);
    setStreamingText("");
    setIsStreaming(false);
    setError(null);
    setInput("");
    setChatStarted(false);
    setCanvasOpen(false);
  };

  const startNewChat = () => {
    setActiveId(null);
    setChatItems([]);
    setArtifacts([]);
    setStreamingText("");
    setIsStreaming(false);
    setError(null);
    setInput("");
    setChatStarted(true);
    setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const selectSession = (id: string) => {
    setActiveId(id);
    setChatStarted(true);
    setStreamingText("");
    setError(null);
    // If this session has an active background stream, show the streaming indicator
    setIsStreaming(streamsRef.current.has(id));
  };

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setError(null);
    setStreamingText("");
    setIsStreaming(true);

    const tempId = `opt-${Date.now()}`;
    setChatItems((prev) => [...prev, { id: tempId, type: "text", role: "user", content: prompt, created_at: new Date().toISOString(), chat_id: activeId ?? "" }]);

    // Capture the session at send-time to decide whether to update activeId on new sessions
    const sendingFromSessionId = activeId;
    const abort = new AbortController();
    let resolvedSessionId = activeId;
    // streamSessionId is set once we know which session this stream belongs to
    let streamSessionId: string | null = activeId;

    // Only update visible state if the user is still looking at this stream's session
    const isActiveSession = () => activeIdRef.current === streamSessionId;

    try {
      await streamChat(prompt, activeId, {
        onSessionStart(sessionId, isNew) {
          resolvedSessionId = sessionId;
          streamSessionId = sessionId;
          streamsRef.current.set(sessionId, abort);

          if (isNew) {
            setSessions((prev) => [{ id: sessionId, title: prompt.slice(0, 50) + (prompt.length > 50 ? "…" : ""), created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, ...prev]);
            // Only switch to the new session if the user hasn't navigated away
            if (activeIdRef.current === sendingFromSessionId) {
              setActiveId(sessionId);
            }
            setChatItems((prev) => prev.map((m) => m.id === tempId && m.type === "text" ? { ...m, chat_id: sessionId } : m));
          } else {
            setSessions((prev) => prev.map((s) => s.id === sessionId ? { ...s, updated_at: new Date().toISOString() } : s));
          }
        },
        onTextDelta(delta) {
          if (isActiveSession()) setStreamingText((t) => t + delta);
        },
        onAssistantMessage(text: string, toolCalls: ToolCall[]) {
          if (isActiveSession()) {
            setChatItems((prev) => {
              const newItems: ChatItem[] = [
                ...toolCalls.map((tc) => ({ id: tc.id, type: "tool_call" as const, name: tc.name, input: tc.input, created_at: new Date().toISOString() })),
                ...(text ? [{ id: `msg-${Date.now()}-${Math.random()}`, type: "text" as const, role: "assistant" as const, content: text, created_at: new Date().toISOString(), chat_id: resolvedSessionId ?? "" }] : []),
              ];
              return [...prev, ...newItems];
            });
            setStreamingText("");
          }
        },
        onArtifact(artifact) {
          if (isActiveSession()) {
            setArtifacts((prev) => [...prev, artifact]);
            setCanvasOpen(true);
            setChatItems((prev) => [...prev, {
              id: `artifact-${artifact.id}`,
              type: "artifact" as const,
              artifact,
              created_at: artifact.created_at,
            }]);
          }
        },
        onDone() {
          if (streamSessionId) streamsRef.current.delete(streamSessionId);

          if (isActiveSession()) {
            // Still on this session — commit any trailing streaming text and clear state
            setStreamingText((t) => {
              if (t) setChatItems((prev) => [...prev, { id: `msg-${Date.now()}`, type: "text", role: "assistant", content: t, created_at: new Date().toISOString(), chat_id: resolvedSessionId ?? "" }]);
              return "";
            });
            setIsStreaming(false);
          } else {
            // Completed in background — the server's BackgroundTask has saved the message.
            // The useEffect on activeId will reload messages when the user returns to this session.
            setIsStreaming((current) => {
              // Only clear isStreaming if the user switched to a different session that
              // itself has no active stream.
              const currentActive = activeIdRef.current;
              if (currentActive && !streamsRef.current.has(currentActive)) return false;
              return current;
            });
          }
        },
        onError(message) {
          if (streamSessionId) streamsRef.current.delete(streamSessionId);
          if (isActiveSession()) {
            setError(message);
            setStreamingText("");
            setIsStreaming(false);
          }
        },
      }, abort.signal);
    } catch (err) {
      if (streamSessionId) streamsRef.current.delete(streamSessionId);
      if ((err as Error).name !== "AbortError" && isActiveSession()) {
        setError((err as Error).message ?? "Something went wrong");
      }
      if (isActiveSession()) {
        setStreamingText("");
        setIsStreaming(false);
      }
    }
  }, [input, isStreaming, activeId]);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setDeleteTarget(null);
    // Cancel any in-flight stream for this session before deleting
    streamsRef.current.get(id)?.abort();
    streamsRef.current.delete(id);
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeId === id) { setActiveId(null); setChatItems([]); setArtifacts([]); setChatStarted(false); setCanvasOpen(false); }
  };

  const activeSession = sessions.find((s) => s.id === activeId);
  const showChat = chatStarted || activeId !== null || isStreaming || chatItems.length > 0;

  return (
    <>
      {deleteTarget && (
        <DeleteModal title={deleteTarget.title} onConfirm={confirmDelete} onCancel={() => setDeleteTarget(null)} />
      )}

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo" onClick={goToLanding} style={{ cursor: "pointer" }}>
            <div className="sidebar-logo-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <span className="sidebar-title">AgentChat</span>
          </div>
          <button className="btn-new" onClick={startNewChat}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New
          </button>
        </div>

        <div className="session-list">
          {sessions.length === 0 ? (
            <div className="sidebar-empty">No conversations yet.<br />Start one above.</div>
          ) : sessions.map((s) => (
            <div key={s.id} className={`session-item${s.id === activeId ? " active" : ""}${streamsRef.current.has(s.id) && s.id !== activeId ? " streaming-bg" : ""}`} onClick={() => selectSession(s.id)}>
              <div className="session-info">
                <div className="session-name">{s.title ?? "Untitled"}</div>
                <div className="session-meta">
                  {streamsRef.current.has(s.id) && s.id !== activeId
                    ? <><span className="session-streaming-dot" />Responding…</>
                    : formatDate(s.updated_at)
                  }
                </div>
              </div>
              <button className="btn-delete" onClick={(e) => { e.stopPropagation(); setDeleteTarget({ id: s.id, title: s.title ?? "Untitled" }); }} title="Delete">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {/* Chat area */}
        <div className="chat-area">
          {showChat ? (
            <>
              <div className="chat-header">
                <div className="chat-header-left">
                  <span className={`chat-status-dot${isStreaming ? " pulsing" : ""}`} />
                  <span className="chat-title">{activeSession?.title ?? "New Chat"}</span>
                </div>
                <div className="chat-header-right">
                  {isStreaming && <div className="chat-header-status"><ThinkingDots /><span>Thinking</span></div>}
                  <button
                    className={`canvas-toggle${canvasOpen ? " active" : ""}`}
                    onClick={() => setCanvasOpen((v) => !v)}
                    title="Toggle artifacts panel"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                      <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                    </svg>
                    Artifacts
                    {artifacts.length > 0 && <span className="canvas-toggle-count">{artifacts.length}</span>}
                  </button>
                </div>
              </div>

              <div className="messages">
                {chatItems.map((item) => {
                  if (item.type === "artifact") {
                    return (
                      <div key={item.id} className="artifact-row">
                        <ArtifactInlineCard artifact={item.artifact} onView={() => setCanvasOpen(true)} />
                      </div>
                    );
                  }
                  return <ChatItemView key={item.id} item={item} />;
                })}
                {isStreaming && (
                  <div className="message assistant">
                    <div className="message-role"><span className="role-dot ai-dot" />AgentChat</div>
                    <div className="message-bubble streaming">
                      {streamingText ? <>{streamingText}<span className="streaming-cursor" /></> : <ThinkingDots />}
                    </div>
                  </div>
                )}
                {error && (
                  <div className="error-banner">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    {error}
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              <div className="input-area">
                <div className="input-wrapper">
                  <textarea ref={textareaRef} rows={1} placeholder="Ask anything…" value={input} onChange={handleInputChange} onKeyDown={handleKeyDown} disabled={isStreaming} />
                  <button className="btn-send" onClick={send} disabled={isStreaming || !input.trim()}>
                    {isStreaming ? <span className="btn-spinner" /> : (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                      </svg>
                    )}
                  </button>
                </div>
                <div className="input-hint">Enter to send · Shift+Enter for new line</div>
              </div>
            </>
          ) : (
            <Landing onStart={startNewChat} />
          )}
        </div>

        {/* Canvas panel */}
        {showChat && (
          <div className={`canvas-panel${canvasOpen ? " open" : ""}`}>
            <ArtifactsPanel artifacts={artifacts} onClose={() => setCanvasOpen(false)} />
          </div>
        )}
      </main>
    </>
  );
}

// ── Landing ───────────────────────────────────────────────────────────────────

function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="landing">
      <div className="landing-bg-glow" />
      <div className="landing-grid" />
      <div className="landing-inner">
        <h1 className="landing-headline">
          <span className="headline-light">Your</span>
          <span className="headline-strong">Agent</span>
          <span className="headline-outline">Chat</span>
        </h1>
        <div className="landing-badge">
          <span className="landing-badge-dot" />
          Powered by Claude Agent SDK
        </div>
        <p className="landing-sub">
          A powerful chat interface powered by the Claude Agent SDK.<br />
          Sessions, tools, artifacts, streaming — all wired up.
        </p>
        <button className="btn-start" onClick={onStart}>
          Start a conversation
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
        <div className="features">
          {[
            { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>, title: "Claude Agent SDK", desc: "Built on the official SDK with full tool-use support." },
            { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>, title: "Sandbox Execution", desc: "Run agents in Modal or subprocess sandboxes." },
            { icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>, title: "Full History", desc: "Every conversation saved. Pick up where you left off." },
          ].map(({ icon, title, desc }) => (
            <div className="feature-card" key={title}>
              <div className="feature-icon">{icon}</div>
              <h3>{title}</h3>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
