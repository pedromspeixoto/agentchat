import type { Session, Message, Artifact, ArtifactKind } from "./types";

const BASE = "/api/v1";

export async function getSessions(): Promise<Session[]> {
  const r = await fetch(`${BASE}/sessions/`);
  if (!r.ok) throw new Error("Failed to load sessions");
  return r.json();
}

export async function getMessages(sessionId: string): Promise<Message[]> {
  const r = await fetch(`${BASE}/sessions/${sessionId}/messages`);
  if (!r.ok) throw new Error("Failed to load messages");
  const data = await r.json();
  return (data.messages as any[]).map((m) => ({
    ...m,
    attachments: m.metadata?.attachments,
  })) as Message[];
}

export async function deleteSession(sessionId: string): Promise<void> {
  const r = await fetch(`${BASE}/sessions/${sessionId}`, { method: "DELETE" });
  if (!r.ok) throw new Error("Failed to delete session");
}

export async function getArtifacts(sessionId: string): Promise<import("./types").Artifact[]> {
  const r = await fetch(`${BASE}/sessions/${sessionId}/artifacts`);
  if (!r.ok) throw new Error("Failed to load artifacts");
  return r.json();
}

export interface ToolCall {
  id: string;
  name: string;
  input: unknown;
}

export interface StreamCallbacks {
  onSessionStart: (sessionId: string, isNew: boolean) => void;
  onTextDelta: (delta: string) => void;
  onAssistantMessage: (text: string, toolCalls: ToolCall[]) => void;
  onArtifact: (artifact: Artifact) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function streamChat(
  prompt: string,
  sessionId: string | null,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  files?: File[],
): Promise<void> {
  const formData = new FormData();
  formData.append("prompt", prompt);
  if (sessionId) formData.append("session_id", sessionId);
  if (files) {
    for (const file of files) formData.append("files", file);
  }
  const response = await fetch(`${BASE}/chat/`, {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "Unknown error");
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const msg = JSON.parse(raw);
            handleEvent(currentEvent, msg, callbacks);
          } catch {
            // ignore malformed lines
          }
          currentEvent = "";
        }
      }
    }
  } finally {
    reader.releaseLock();
    callbacks.onDone();
  }
}

const KNOWN_KINDS = new Set<ArtifactKind>(["csv", "pdf", "json", "txt", "xlsx"]);

function toKind(raw: unknown): ArtifactKind {
  if (typeof raw === "string" && KNOWN_KINDS.has(raw as ArtifactKind)) return raw as ArtifactKind;
  return "other";
}

function handleEvent(
  eventType: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  msg: Record<string, any>,
  callbacks: StreamCallbacks,
) {
  switch (eventType) {
    case "session_start":
      callbacks.onSessionStart(msg.session_id, msg.is_new);
      break;

    case "StreamEvent": {
      const delta: string = msg.event?.delta?.text ?? msg.delta?.text ?? msg.data?.delta?.text ?? msg.text ?? "";
      if (delta) callbacks.onTextDelta(delta);
      break;
    }

    case "AssistantMessage": {
      const blocks: Array<Record<string, unknown>> = msg.content ?? [];
      const text = blocks.filter((b) => b.__type === "TextBlock").map((b) => (b.text as string) ?? "").join("");
      const toolCalls: ToolCall[] = blocks
        .filter((b) => b.__type === "ToolUseBlock")
        .map((b) => ({
          id: (b.id as string) ?? `tool-${Date.now()}-${Math.random()}`,
          name: (b.name as string) ?? "unknown_tool",
          input: b.input ?? {},
        }));
      callbacks.onAssistantMessage(text, toolCalls);
      break;
    }

    case "Artifact":
      callbacks.onArtifact({
        id: msg.id ?? `art-${Date.now()}`,
        name: msg.name ?? "artifact",
        kind: toKind(msg.kind),
        size: typeof msg.size === "number" ? msg.size : undefined,
        url: typeof msg.url === "string" ? msg.url : undefined,
        created_at: new Date().toISOString(),
      });
      break;

    case "error":
      callbacks.onError(msg.message ?? "Unknown error");
      break;
  }
}
