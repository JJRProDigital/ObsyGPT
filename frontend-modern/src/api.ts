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

export async function streamMessage(
  conversationId: number,
  message: string,
  options: { agent_id?: number | null; workflow_id?: number | null; attachment_ids?: number[]; mode?: string },
  onToken: (token: string) => void
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

  while (true) {
    const result = await reader.read();
    if (result.done) break;
    onToken(decoder.decode(result.value, { stream: true }));
  }
}

export async function streamApprovalResume(
  approvalId: number,
  approved: boolean,
  onToken: (token: string) => void
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

  while (true) {
    const result = await reader.read();
    if (result.done) break;
    onToken(decoder.decode(result.value, { stream: true }));
  }
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
