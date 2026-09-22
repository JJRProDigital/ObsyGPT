import { describe, expect, it, vi, afterEach } from "vitest";
import { ApiError, UNAUTHORIZED_EVENT, apiRequest } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("apiRequest", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws ApiError with the HTTP status on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(422, { detail: "Validation failed" })));
    await expect(apiRequest("/api/thing")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "Validation failed"
    });
  });

  it("stringifies object details instead of [object Object]", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(400, { detail: { field: "model_id", msg: "required" } })));
    await expect(apiRequest("/api/thing")).rejects.toMatchObject({
      message: JSON.stringify({ field: "model_id", msg: "required" })
    });
  });

  it("extracts msg from fastapi validation arrays", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(422, { detail: [{ msg: "field required", loc: ["body", "x"] }] })));
    await expect(apiRequest("/api/thing")).rejects.toMatchObject({ message: "field required" });
  });

  it("dispatches UNAUTHORIZED_EVENT on 401 for non-auth paths", async () => {
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { detail: "expired" })));
    await expect(apiRequest("/api/memory")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it("does NOT dispatch UNAUTHORIZED_EVENT for login failures", async () => {
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { detail: "bad credentials" })));
    await expect(apiRequest("/api/login")).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });
});
