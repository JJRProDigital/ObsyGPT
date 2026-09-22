const backendUrl = import.meta.env.VITE_BACKEND_URL ?? (import.meta.env.DEV ? "" : `${window.location.protocol}//${window.location.hostname}:8000`);

export const UNAUTHORIZED_EVENT = "obsygpt:unauthorized";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const first = detail.find((item) => item && typeof item === "object" && "msg" in item);
    if (first && typeof (first as { msg?: unknown }).msg === "string") return (first as { msg: string }).msg;
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      /* fall through */
    }
  }
  return fallback;
}

/** Login-related paths where a 401 is an expected answer, not a lost session. */
function authPath(path: string): boolean {
  return /\/(login|register|session)$/.test(path);
}

function notifyUnauthorized(path: string): void {
  if (authPath(path)) return;
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

async function parseJson(response: Response): Promise<Record<string, unknown>> {
  const data = await response.json().catch(() => ({}));
  return (data ?? {}) as Record<string, unknown>;
}

async function jsonRequest<T>(path: string, options: RequestInit, fallbackMessage: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {})
      }
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError(0, `Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  const data = await parseJson(response);

  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized(path);
    throw new ApiError(response.status, detailToMessage(data.detail, fallbackMessage));
  }

  return data as T;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  return jsonRequest<T>(path, options, "Request failed");
}

const ACTIVITY_OPEN = "\x00ACT\x00";
const ACTIVITY_CLOSE = "\x00";

export type ActivityEvent = { kind: string; phase?: string; name?: string; iteration?: number; chars?: number; detail?: string; text?: string };

function consumeChunk(buffer: { pending: string }, chunk: string, onToken: (t: string) => void, onActivity?: (a: ActivityEvent) => void) {
  buffer.pending += chunk;
  while (true) {
    const open = buffer.pending.indexOf(ACTIVITY_OPEN);
    if (open === -1) break;
    const before = buffer.pending.slice(0, open);
    if (before) onToken(before);
    const rest = buffer.pending.slice(open + ACTIVITY_OPEN.length);
    const close = rest.indexOf(ACTIVITY_CLOSE);
    if (close === -1) {
      buffer.pending = ACTIVITY_OPEN + rest;
      return;
    }
    const raw = rest.slice(0, close);
    buffer.pending = rest.slice(close + 1);
    if (onActivity) {
      try { onActivity(JSON.parse(raw) as ActivityEvent); } catch { /* ignore malformed frame */ }
    }
  }
  const s = buffer.pending;
  for (let keep = Math.min(ACTIVITY_OPEN.length - 1, s.length); keep > 0; keep--) {
    if (s.endsWith(ACTIVITY_OPEN.slice(0, keep))) {
      if (keep < s.length) onToken(s.slice(0, s.length - keep));
      buffer.pending = s.slice(s.length - keep);
      return;
    }
  }
  if (s) { onToken(s); buffer.pending = ""; }
}

async function streamRequest(
  path: string,
  init: RequestInit,
  onToken: (token: string) => void,
  onActivity?: (activity: ActivityEvent) => void
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}${path}`, { ...init, credentials: "include" });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError(0, `Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) notifyUnauthorized(path);
    const data = await parseJson(response).catch(() => ({}) as Record<string, unknown>);
    throw new ApiError(response.status, detailToMessage(data.detail, (await response.text().catch(() => "")) || "Request failed"));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const buffer = { pending: "" };

  while (true) {
    const result = await reader.read();
    if (result.done) break;
    consumeChunk(buffer, decoder.decode(result.value, { stream: true }), onToken, onActivity);
  }
  if (buffer.pending && !buffer.pending.startsWith(ACTIVITY_OPEN)) onToken(buffer.pending);
}

export async function streamMessage(
  conversationId: number,
  message: string,
  options: { agent_id?: number | null; workflow_id?: number | null; attachment_ids?: number[]; mode?: string },
  onToken: (token: string) => void,
  onActivity?: (activity: ActivityEvent) => void
): Promise<void> {
  await streamRequest(
    `/api/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, ...options })
    },
    onToken,
    onActivity
  );
}

export async function streamApprovalResume(
  approvalId: number,
  approved: boolean,
  onToken: (token: string) => void,
  onActivity?: (activity: ActivityEvent) => void
): Promise<void> {
  await streamRequest(
    `/api/approvals/${approvalId}/${approved ? "approve" : "deny"}`,
    { method: "POST", headers: { "Content-Type": "application/json" } },
    onToken,
    onActivity
  );
}

export async function uploadAttachment(file: File): Promise<{ attachment: { id: number; file_name: string; mime_type: string; size_bytes: number }; artifact: { id: number; artifact_type: string; title: string; content: string } }> {
  const body = new FormData();
  body.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${backendUrl}/api/attachments`, {
      method: "POST",
      credentials: "include",
      body
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError(0, `Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  const data = await parseJson(response);

  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized("/api/attachments");
    throw new ApiError(response.status, detailToMessage(data.detail, "Upload failed"));
  }

  return data as {
    attachment: { id: number; file_name: string; mime_type: string; size_bytes: number };
    artifact: { id: number; artifact_type: string; title: string; content: string };
  };
}
