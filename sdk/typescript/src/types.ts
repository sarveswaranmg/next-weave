/** Shared request/response shapes for the NeuroWeave Cognitive Runtime API. */

export interface ChatOptions {
  provider?: string;
  model?: string;
  memory?: boolean;
  worldModel?: boolean;
  predictiveRecall?: boolean;
  contextComposer?: boolean;
  tokenBudget?: number;
  scheduleBackground?: boolean;
}

export interface ChatResponse {
  user_id: string;
  response: string;
  provider: string;
  model: string;
  usage: Record<string, number>;
  memory_stored: string | null;
  world_model: Record<string, unknown> | null;
  context: Record<string, unknown> | null;
  background_scheduled: string[];
  stage_latency_ms: Record<string, number>;
  total_latency_ms: number;
}

export interface ExplainResponse {
  found: boolean;
  [key: string]: unknown;
}

export interface RuntimeMetricsResponse {
  user_id: string | null;
  memory_count: number;
  concept_count: number;
  identity_nodes: number;
  world_nodes: number;
  world_relationships: number;
  project_count: number;
  compression_ratio: number;
  cognitive_health_score: number;
}
