# FieldOps Voice Copilot — System Requirements & Traceability Specification

**Document Version:** 1.0.0  
**Date:** September 2026  
**Project:** FieldOps Voice Copilot — Evidence-Gated Realtime AI for Industrial Technicians  
**Hackathon:** YC Fall 2026 × Moss — The Zero Latency Builder Sprint  
**Track:** Real-Time Voice and Conversational AI  

---

## 1. Introduction & System Scope

FieldOps Voice Copilot delivers hands-free, low-latency, evidence-gated procedural intelligence to industrial technicians diagnosing high-pressure machinery (e.g. reciprocating and rotary screw compressors) in noisy plant environments.

The architecture enforces a strict physical separation:
- **Realtime Data Plane (Hot Path):** LiveKit WebRTC Transport -> STT -> Query Normalization -> Scope Authorization -> In-Process Embedded Moss Retrieval -> Evidence Sufficiency Gate -> LLM -> Grounding Validator -> Streaming TTS.
- **Control Plane (Off Hot Path):** FastAPI, SQLAlchemy, SQLite/PostgreSQL, managing user sessions, asset registries, audit logs, and data privacy.

---

## 2. Functional Requirements (FR)

| Req ID | Requirement Statement | Rationale | Acceptance Criteria | Component | Implementation | Test File |
|---|---|---|---|---|---|---|
| **FR-001** | **Realtime Voice Session Initialization** | Technicians must establish authenticated, bidirectional audio streams hands-free. | LiveKit session token issued with server-derived scope metadata; fails closed if unconfigured. | Control Plane | `backend/app/sessions.py` | `backend/tests/test_sessions.py` |
| **FR-002** | **Deterministic Query Normalization** | Spoken industrial terminology (e.g., "CP two hundred", "E seventeen") must be canonicalized before search. | Normalized query extracts canonical error codes (e.g., `E17`), model families (`CP-200`), and intent. | Agent Plane | `agent/src/normalizer.py` | `agent/tests/test_normalizer.py` |
| **FR-003** | **Pre-Retrieval Scope Verification** | Spoken technician utterances cannot expand authorized maintenance boundaries. | Access to assets or sites outside user's assigned JWT scope is rejected prior to Moss invocation. | Agent Plane | `agent/src/authorization.py` | `agent/tests/test_authorization.py` |
| **FR-004** | **In-Process Embedded Moss Retrieval** | Critical retrieval must execute locally with sub-10ms P95 latency without per-query cloud roundtrips. | Moss index loaded into process memory at worker startup; queries execute via embedded runtime. | Embedded Moss | `agent/src/retrieval.py` | `agent/tests/test_retrieval_unit.py` |
| **FR-005** | **Deterministic Evidence Sufficiency Gate** | Model hallucinations and irrelevant procedures must be blocked before calling the LLM generator. | Gate evaluates relevance, model compatibility, and document manifest revisions; fails safely on mismatch. | Agent Plane | `agent/src/evidence_gate.py` | `agent/tests/test_evidence_gate.py` |
| **FR-006** | **Post-Generation Grounding Validation** | Every technical claim emitted over audio must be audited against retrieved evidence. | Validator verifies candidate response; emits PASS/FAIL; permits max 1 regeneration before safe refusal. | Agent Plane | `agent/src/grounding.py` | `agent/tests/test_prompt_injection.py` |

---

## 3. Non-Functional Requirements (NFR)

| Req ID | Requirement Statement | Rationale | Target Metric / SLA | Status | Verification |
|---|---|---|---|---|---|
| **NFR-001** | **Query Normalization Latency** | Heuristic regex matching must not add perceptible delay. | P95 <= 1.5ms | **PASS** (0.175ms measured) | `evaluation/benchmark.py` |
| **NFR-002** | **Authorization Scope Latency** | Pre-retrieval security check must execute in-memory. | P95 <= 1.0ms | **PASS** (0.121ms measured) | `evaluation/benchmark.py` |
| **NFR-003** | **Embedded Moss Retrieval Latency** | In-process retrieval SLA target. | P95 <= 10.0ms | **7.4ms Ref** (Published Moss 100k Benchmark) | `evaluation/benchmark.py` |
| **NFR-004** | **Evidence Sufficiency Gate Latency** | Deterministic gating must complete in-memory before LLM. | P95 <= 2.0ms | **PASS** (0.491ms measured) | `evaluation/benchmark.py` |
| **NFR-005** | **Pre-LLM Local CPU Total** | Total local execution prior to LLM/TTS synthesis. | P95 <= 15.0ms | **PASS** (0.628ms measured) | `evaluation/benchmark.py` |

---

## 4. Security Requirements (SEC)

*Aligned with OWASP Top 10 API and LLM Application Security Guidelines.*

| Req ID | Security Requirement | Threat Mitigated | Implementation Defense | Verification Test |
|---|---|---|---|---|
| **SEC-001** | **Fail-Closed Authentication** | Broken Authentication (OWASP A01) | Unauthenticated requests return HTTP 401; missing LiveKit metadata aborts voice session. | `backend/tests/test_auth.py` |
| **SEC-002** | **Broken Object-Level Authorization** | BOLA / Privilege Escalation (OWASP A03) | Authorization context derived exclusively server-side from DB; client speech cannot expand scope. | `agent/tests/test_authorization.py` |
| **SEC-003** | **Prompt Injection Isolation** | LLM01: Prompt Injection | Retrieved documentation text treated as untrusted data; adversarial system commands inertly ignored. | `agent/tests/test_prompt_injection.py` |
| **SEC-004** | **Rate Limiting & Payload Defense** | Denial of Service (OWASP A04) | 100 req/min rate limiter on control plane; request body capped at 1 MB; security headers applied. | `backend/tests/test_auth.py` |
| **SEC-005** | **No Secret Persistence** | Sensitive Data Exposure (OWASP A02) | Cryptographic secrets loaded from environment; zero API keys committed or sent in public channels. | Repository scan |

---

## 5. Privacy Requirements (PRV)

| Req ID | Requirement Statement | Implementation Defense | Verification |
|---|---|---|---|
| **PRV-001** | **Zero Raw Voice Recording Persistence** | Audio streams are processed in realtime WebRTC memory; no audio recordings written to disk by default. | Architecture invariant |
| **PRV-002** | **Ephemeral Transcript Retention** | Conversation state retained only for active session duration in memory / Redis TTL. | `agent/src/session.py` |
| **PRV-003** | **GDPR Article 17 Data Erasure** | `POST /api/v1/privacy/delete` purges all user sessions, feedbacks, and anonymizes audit logs. | `backend/tests/test_privacy.py` |

---

## 6. Observability Requirements (OBS)

| Req ID | Requirement Statement | Implementation Defense |
|---|---|---|
| **OBS-001** | **OpenTelemetry Distributed Tracing** | Spans created for normalization, authorization, retrieval, evidence gate, LLM, grounding, and voice turns. |
| **OBS-002** | **Trace Correlation Identifiers** | Every turn correlates `session_id`, `turn_id`, `retrieval_id`, `prompt_hash`, and `index_version`. |
| **OBS-003** | **Prompt Version & Hash Auditing** | `PROMPT_VERSION` (`v1.2.0`) and SHA-256 hash stamped on all telemetry traces. |

---

## 7. Comprehensive Requirements Traceability Matrix

```
Requirement ID ──► Architectural Node ──► Source Code File ────────► Unit / Integration Test
─────────────────────────────────────────────────────────────────────────────────────────────
FR-001 (Init)      FastAPI Control Plane  backend/app/sessions.py     backend/tests/test_sessions.py
FR-002 (Normalize) Query Normalizer       agent/src/normalizer.py     agent/tests/test_normalizer.py
FR-003 (AuthScope) Pre-Retrieval Auth     agent/src/authorization.py  agent/tests/test_authorization.py
FR-004 (Moss)      Embedded Moss Runtime  agent/src/retrieval.py      agent/tests/test_retrieval_unit.py
FR-005 (Gate)      Evidence Sufficiency   agent/src/evidence_gate.py  agent/tests/test_evidence_gate.py
FR-006 (Grounding) Grounding Validator    agent/src/grounding.py      agent/tests/test_prompt_injection.py
NFR-001..005       Pipeline Latency       agent/src/agent.py          evaluation/benchmark.py
SEC-001 (Auth)     JWT Auth Engine        backend/app/auth.py         backend/tests/test_auth.py
SEC-002 (BOLA)     Scope Boundary         agent/src/authorization.py  agent/tests/test_authorization.py
SEC-003 (Inject)   CRISPE Prompts         agent/src/prompts.py        agent/tests/test_prompt_injection.py
PRV-001..003       Privacy Service        backend/app/privacy.py      backend/tests/test_privacy.py
OBS-001..003       Telemetry Engine       agent/src/telemetry.py      agent/src/agent.py
```
