/**
 * NeuroWeave TypeScript SDK — low-level HTTP client.
 *
 * Uses the native `fetch` API (available in Node 18+ and all browsers),
 * so this package has zero runtime dependencies.
 */
import type { ChatOptions, ChatResponse, ExplainResponse, RuntimeMetricsResponse } from "./types.js";

export interface NeuroWeaveClientOptions {
  baseUrl?: string;
  apiKey?: string;
  timeoutMs?: number;
}

export class NeuroWeaveClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeoutMs: number;

  constructor(options: NeuroWeaveClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.timeoutMs = options.timeoutMs ?? 60_000;
  }

  private async request<T>(method: string, path: string, body?: unknown, params?: Record<string, string>): Promise<T> {
    const url = new URL(this.baseUrl + path);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) url.searchParams.set(key, value);
      }
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(url.toString(), {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`NeuroWeave API error ${response.status}: ${text}`);
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timeout);
    }
  }

  async chat(userId: string, message: string, options: ChatOptions = {}): Promise<ChatResponse> {
    return this.request<ChatResponse>("POST", "/runtime/chat", {
      user_id: userId,
      message,
      provider: options.provider,
      model: options.model,
      memory: options.memory,
      world_model: options.worldModel,
      predictive_recall: options.predictiveRecall,
      context_composer: options.contextComposer,
      token_budget: options.tokenBudget,
      schedule_background: options.scheduleBackground,
    });
  }

  async health(): Promise<Record<string, unknown>> {
    return this.request("GET", "/runtime/health");
  }

  async version(): Promise<Record<string, unknown>> {
    return this.request("GET", "/runtime/version");
  }

  async metrics(userId?: string): Promise<RuntimeMetricsResponse> {
    return this.request<RuntimeMetricsResponse>("GET", "/runtime/metrics", undefined, userId ? { user_id: userId } : undefined);
  }

  async explain(userId: string, subjectType: string, subjectId?: string): Promise<ExplainResponse> {
    const params: Record<string, string> = { user_id: userId, subject_type: subjectType };
    if (subjectId) params.subject_id = subjectId;
    return this.request<ExplainResponse>("GET", "/runtime/explain", undefined, params);
  }

  async deleteUser(userId: string): Promise<Record<string, unknown>> {
    return this.request("DELETE", `/runtime/users/${userId}`);
  }

  async ingestMemory(userId: string, conversation: string): Promise<Record<string, unknown>> {
    return this.request("POST", "/memory/ingest", { user_id: userId, conversation });
  }

  async getWorldModel(userId: string): Promise<Record<string, unknown>> {
    return this.request("GET", "/world/model", undefined, { user_id: userId });
  }
}
