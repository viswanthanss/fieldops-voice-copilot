export interface EvidenceItem {
  document_id: string;
  document_type: string;
  revision: string;
  effective_date?: string;
  model: string;
  section: string;
  score: number;
  snippet: string;
}

export interface LatencyBreakdown {
  normalization_ms?: number;
  authorization_ms?: number;
  retrieval_ms?: number;
  evidence_gate_ms?: number;
  llm_generation_ms?: number;
  grounding_validation_ms?: number;
  total_ms?: number;
}

export interface TurnAttribution {
  turn_id: number;
  retrieval_id: string;
  evidence_gate_decision: "PASS" | "FAIL_NO_EVIDENCE" | "FAIL_LOW_RELEVANCE" | "FAIL_MODEL_MISMATCH" | "FAIL_EQUIPMENT_MISMATCH" | "FAIL_STALE_REVISION" | "FAIL_UNAUTHORIZED";
  grounding_status: "PASS" | "FAIL" | "SKIPPED";
  retrieved_evidence: EvidenceItem[];
  latencies: LatencyBreakdown;
  prompt_version?: string;
}

export interface VoiceMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: string;
  isInterrupted?: boolean;
  attribution?: TurnAttribution;
}

export interface AuthContext {
  tenant_id: string;
  site_ids: string[];
  asset_ids: string[];
  roles: string[];
  user_id: string;
}

export interface SessionResponse {
  session_id: string;
  livekit_token: string;
  livekit_url: string;
  auth_context: AuthContext;
  expires_at: string;
  is_demo?: boolean;
}
