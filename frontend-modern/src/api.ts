const backendUrl = import.meta.env.VITE_BACKEND_URL ?? (import.meta.env.DEV ? "" : `${window.location.protocol}//${window.location.hostname}:8000`);

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
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
      throw new Error(`Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail ?? "Request failed");
  }

  return data as T;
}

const ACTIVITY_OPEN = "\x00ACT\x00";
const ACTIVITY_CLOSE = "\x00";

export type ActivityEvent = { kind: string; phase?: string; name?: string; iteration?: number; chars?: number; detail?: string };

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

export async function streamMessage(
  conversationId: number,
  message: string,
  options: { agent_id?: number | null; workflow_id?: number | null; attachment_ids?: number[]; mode?: string },
  onToken: (token: string) => void,
  onActivity?: (activity: ActivityEvent) => void
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}/api/conversations/${conversationId}/messages`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, ...options })
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
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

export async function streamApprovalResume(
  approvalId: number,
  approved: boolean,
  onToken: (token: string) => void,
  onActivity?: (activity: ActivityEvent) => void
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${backendUrl}/api/approvals/${approvalId}/${approved ? "approve" : "deny"}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" }
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(`Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
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
      throw new Error(`Cannot reach ObsyGPT backend at ${backendUrl}. Check that the backend is running and CORS allows this frontend URL.`);
    }
    throw error;
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail ?? "Upload failed");
  }

  return data;
}
