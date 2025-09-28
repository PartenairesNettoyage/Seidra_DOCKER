import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../lib/api-client";

const originalFetch = globalThis.fetch;

describe("apiClient", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("compose correctement l'URL et renvoie les données JSON", async () => {
    const responsePayload = { total: 0, jobs: [] };

    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/jobs?status=done&limit=10");
      return new Response(JSON.stringify(responsePayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    globalThis.fetch = mockFetch as typeof globalThis.fetch;

    const result = await apiClient.listJobs({ status: "done", limit: 10 });
    expect(result).toEqual(responsePayload);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("lève une erreur sur un statut HTTP en erreur", async () => {
    const mockFetch = vi.fn(async () =>
      new Response("Not found", { status: 404, headers: { "Content-Type": "text/plain" } })
    );

    globalThis.fetch = mockFetch as typeof globalThis.fetch;

    await expect(apiClient.getJob("123")).rejects.toThrowError(/Not found/);
  });

  it("retourne les informations du job de prévisualisation", async () => {
    const responsePayload = {
      job_id: "preview-job-42",
      status: "queued",
      message: "Preview en file d'attente",
      persona_id: 7,
      estimated_time: 45,
    };

    const mockFetch = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/personas/7/preview");
      return new Response(JSON.stringify(responsePayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    globalThis.fetch = mockFetch as typeof globalThis.fetch;

    const result = await apiClient.previewPersona(7);
    expect(result).toEqual(responsePayload);
    expect(result.job_id).toBe("preview-job-42");
  });
});

afterAll(() => {
  globalThis.fetch = originalFetch;
});
