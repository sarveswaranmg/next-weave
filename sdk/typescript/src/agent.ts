/**
 * CognitiveAgent — the five-minute integration surface.
 *
 * ```ts
 * import { CognitiveAgent } from "neurowave";
 *
 * const agent = new CognitiveAgent({
 *   provider: "google",
 *   memory: true,
 *   worldModel: true,
 *   predictiveRecall: true,
 *   contextComposer: true,
 * });
 *
 * const response = await agent.chat("123", "Help me design a distributed cache.");
 * ```
 */
import { NeuroWeaveClient } from "./client.js";
import type { ChatOptions, ChatResponse } from "./types.js";

export interface CognitiveAgentOptions extends ChatOptions {
  baseUrl?: string;
  apiKey?: string;
}

export class CognitiveAgent {
  readonly client: NeuroWeaveClient;
  private readonly defaults: ChatOptions;

  constructor(options: CognitiveAgentOptions = {}) {
    const { baseUrl, apiKey, ...defaults } = options;
    this.client = new NeuroWeaveClient({ baseUrl, apiKey });
    this.defaults = {
      provider: "google",
      memory: true,
      worldModel: true,
      predictiveRecall: true,
      contextComposer: true,
      ...defaults,
    };
  }

  async chat(userId: string, message: string, overrides: ChatOptions = {}): Promise<ChatResponse> {
    return this.client.chat(userId, message, { ...this.defaults, ...overrides });
  }

  async explain(userId: string, subjectType: string, subjectId?: string) {
    return this.client.explain(userId, subjectType, subjectId);
  }

  async metrics(userId?: string) {
    return this.client.metrics(userId);
  }

  /** GDPR/CCPA right to be forgotten: permanently delete all of this user's data. */
  async forgetUser(userId: string) {
    return this.client.deleteUser(userId);
  }
}
