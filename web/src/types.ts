export interface Session {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export type ChatItem =
  | {
      id: string;
      type: "text";
      role: "user" | "assistant";
      content: string;
      created_at: string;
      chat_id: string;
    }
  | {
      id: string;
      type: "tool_call";
      name: string;
      input: unknown;
      created_at: string;
    }
  | {
      id: string;
      type: "artifact";
      artifact: Artifact;
      created_at: string;
    };

export type ArtifactKind = "csv" | "pdf" | "json" | "txt" | "xlsx" | "other";

export interface Artifact {
  id: string;
  name: string;
  kind: ArtifactKind;
  size?: number;         // bytes
  url?: string;          // download URL
  created_at: string;
}
