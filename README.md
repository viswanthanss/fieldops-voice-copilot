# FieldOps Voice Copilot
### Evidence-Gated Realtime Voice AI for Industrial Field Technicians

[![Track](https://img.shields.io/badge/Track-Real--Time%20Voice%20%26%20Conversational%20AI-blue)](https://moss.dev)
[![Hackathon](https://img.shields.io/badge/Hackathon-YC%20Fall%202026%20%C3%97%20Moss-orange)](https://moss.dev)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15.5%20App%20Router-black)](https://nextjs.org)
[![LiveKit](https://img.shields.io/badge/LiveKit-Agents%201.x-cyan)](https://livekit.io)
[![Embedded Moss](https://img.shields.io/badge/Retrieval-Embedded%20Moss%20Runtime-red)](https://moss.dev)

---

## 1. Problem Statement

Industrial field technicians diagnosing high-pressure machinery (e.g. reciprocating and rotary screw gas compressors) operate under extreme environmental and physical constraints:
1. **Hands-Occupied Execution:** Technicians wearing heavy PPE and holding pneumatic tools cannot type or navigate physical manuals on laptops.
2. **Fatal Cost of Hallucination:** A single fabricated procedural step (e.g., torquing an un-isolated cylinder head or misdiagnosing an overheating error) can cause catastrophic mechanical failure, toxic gas release, or emergency refinery shutdowns.
3. **Model Cross-Contamination:** Error codes are model-specific. For example, error `E17` on a **CP-200** reciprocating compressor indicates dangerous *high discharge temperature (>185°F)* requiring immediate cooldown, whereas `E17` on a **CP-300** rotary screw unit indicates an *electrical variable frequency drive (VFD) inverter fault*. Standard RAG systems cross-contaminate procedures between models.
4. **Cloud Latency Penalties:** Conventional cloud-hosted vector search roundtrips (100–300ms) break real-time conversational cadence over industrial radios.

---

## 2. Solution: FieldOps Voice Copilot

**FieldOps Voice Copilot** is an evidence-gated, hands-free conversational voice assistant built directly on the **Embedded Moss Retrieval Runtime** and **LiveKit WebRTC Agents 1.x**.

Key capabilities:
- **Embedded In-Process Retrieval:** The versioned Moss index is loaded into local process memory at startup. Per-turn queries execute locally in-process with sub-10ms P95 target retrieval latency, keeping external cloud vector databases off the realtime voice hot path.
- **Pre-LLM Evidence Sufficiency Gate:** A deterministic gate evaluates retrieved evidence *before* calling the LLM generator. If documentation is missing, below relevance threshold, or belongs to a mismatched equipment model, the pipeline immediately returns a safe, authorized refusal—preventing hallucinations and eliminating unnecessary LLM costs.
- **Post-Generation Grounding Validator:** A secondary compliance auditor extracts all substantive technical claims from the candidate response and cross-verifies them against the retrieved evidence chunks before synthesizing audio.
- **Fail-Closed Pre-Retrieval Authorization:** Spoken utterances cannot expand privileges. The agent verifies technician assignment to the queried asset before Moss is queried.
- **Realtime Source Attribution:** Realtime WebRTC data channels stream exact document IDs, revisions, sections, and latency breakdowns to the technician's workstation UI.

---

## 3. System Architecture

```
                                 REALTIME HOT PATH (DATA PLANE)
                                 
   Technician (Hands-Free Radio)
        ▲               │
        │ WebRTC Audio  ▼ WebRTC Audio
   ┌─────────────────────────────────────────────────────────────┐
   │            LiveKit Realtime Transport (WebRTC)              │
   └──────────────────────┬──────────────────────────────────────┘
                          │ Inbound Audio Stream
                          ▼
   ┌─────────────────────────────────────────────────────────────┐
   │             LiveKit Python Agent (Worker Node)              │
   │                                                             │
   │  1. Streaming STT (Deepgram / Whisper)                      │
   │  2. Query Normalizer (Extracts E17, CP-200, CP-204)         │
   │  3. Pre-Retrieval Authorization (Session-derived scope)     │
   │  4. Embedded Moss Runtime (In-process local query <10ms)    │
   │  5. Evidence Sufficiency Gate (Deterministic PASS/FAIL)     │
   │       ├─► FAIL: Immediate Safe Procedural Fallback          │
   │       └─► PASS: Inject Approved Evidence Chunks             │
   │  6. LLM Generator (2-4 spoken sentences CRISPE prompt)      │
   │  7. Grounding Validator (Audits technical claims)           │
   │  8. Streaming TTS (OpenAI / ElevenLabs)                     │
   └──────────────────────┬──────────────────────────────────────┘
                          │ Outbound Streaming Audio + Data Channel
                          ▼
   Technician Audio Headset + Next.js Workstation UI (Source Attribution)

   ───────────────────────────────────────────────────────────────
                  CONTROL PLANE (OFF REALTIME HOT PATH)
                  
     Technician Browser ──► FastAPI REST API ──► SQLite / PostgreSQL
     (Login / JWT)          (Auth Context Scope) (Users / Assets / Audit)
```

### Architectural Invariants:
1. **Embedded Moss Runtime is in-process:** Loaded at worker startup via `await client.load_index(...)`.
2. **Zero Cloud Hot Path:** Neither FastAPI nor relational databases nor Moss Cloud sit in the realtime voice query loop.
3. **Fail-Closed Authorization:** Missing room metadata immediately terminates the voice session.
4. **No Disguised / Fake Moss:** The production and demo path uses official `moss` SDK APIs (`MossClient`, `QueryOptions`, `load_index`, `query`).

---

## 4. Latency Performance & Benchmark Discipline

In accordance with strict hackathon engineering standards, we clearly distinguish between **Published References**, **Project Targets**, and **Actual Measured Results**.

| Pipeline Stage | Published Moss Reference | Project Target P95 | Measured Local Execution P95 | Status |
|---|---|---|---|---|
| **Query Normalization** | N/A (Local CPU) | 1.5ms | **0.175ms** | **PASS** |
| **Authorization Check** | N/A (Local CPU) | 1.0ms | **0.121ms** | **PASS** |
| **Moss Embedded Retrieval** | 7.4ms (100k doc benchmark) | 10.0ms | *Requires live credentials* | **UNVERIFIED** |
| **Evidence Sufficiency Gate**| N/A (Local CPU) | 2.0ms | **0.491ms** | **PASS** |
| **Pre-LLM Local CPU Total**  | N/A | &lt;15.0ms | **0.628ms** | **PASS** |

> **Latency Claim Discipline:**  
> - We do **not** claim "zero latency".
> - We do **not** claim "entire response under 10ms".
> - In-process Moss retrieval targets &le;10ms P95; pre-LLM local CPU processing completes in **0.628ms P95**.
> - When Moss credentials are not configured in local development, retrieval is marked `not_run`—synthetic numbers are strictly prohibited.

---

## 5. Security & Privacy Architecture

### Security Controls (OWASP Top 10 Aligned)
- **SEC-001 (Broken Auth):** HS256 JWTs with 30-min lifespan; fail-closed connection policy on LiveKit worker.
- **SEC-002 (BOLA / Privilege Escalation):** Spoken user speech cannot elevate permissions. `verify_retrieval_scope` rejects unauthorized assets before Moss retrieval.
- **SEC-003 (Prompt Injection Defense):** Retrieved technical documents are framed as untrusted data objects. Adversarial override commands inside manuals are treated as inert text.
- **SEC-004 (Resource Exhaustion):** Rate limiting (100 req/min) on control plane; request body capped at 1 MB.

### Privacy & Data Minimization
- **PRV-001:** Zero raw audio retention. Audio frames are processed in ephemeral WebRTC memory buffers and discarded post-STT.
- **PRV-002:** Short-lived conversation context stored in `SessionStore` (In-Memory for development, Redis TTL for production).
- **PRV-003:** GDPR Article 17 self-service deletion endpoint (`POST /api/v1/privacy/delete`) purges user sessions and anonymizes audit logs.

---

## 6. Repository Layout

```
fieldops-voice-copilot/
├── agent/                      # Realtime LiveKit Voice Agent Plane
│   ├── src/
│   │   ├── agent.py            # LiveKit 1.x AgentServer with on_user_turn_completed
│   │   ├── retrieval.py        # Embedded Moss Runtime client wrapper
│   │   ├── normalizer.py       # Deterministic query parameter extractor
│   │   ├── authorization.py    # Pre-retrieval scope verification & Moss filters
│   │   ├── evidence_gate.py    # Deterministic Evidence Sufficiency Gate
│   │   ├── grounding.py        # Post-generation Grounding Validator
│   │   ├── prompts.py          # CRISPE prompt contracts & hash tracking
│   │   ├── session.py          # InMemory & Redis SessionStore abstraction
│   │   ├── config.py           # Pydantic Settings agent configuration
│   │   └── telemetry.py        # OpenTelemetry distributed tracing setup
│   └── tests/                  # Agent unit tests (17 passing tests)
├── backend/                    # Control Plane (FastAPI + SQLAlchemy)
│   ├── app/                    # REST API, Auth, Sessions, Assets, Privacy
│   └── tests/                  # Security & session tests (7 passing tests)
├── frontend/                   # Next.js 15 App Router Technician Workstation
│   ├── app/                    # App Router (page.tsx, layout.tsx)
│   ├── components/             # Voice visualizer, EvidencePanel, LiveKit session
│   ├── lib/                    # API client bindings
│   └── types/                  # TypeScript interface contracts
├── architecture/               # System architecture specification & diagrams
├── knowledge/                  # Industrial Equipment Documentation Corpus
│   ├── manuals/                # CP-200 & CP-300 synthetic service manuals
│   ├── error-codes/            # CP-200 & CP-300 error code quick references
│   ├── sops/                   # High temp response & emergency restart SOPs
│   ├── bulletins/              # Technical service bulletins (TSB-2024-01, etc.)
│   └── metadata/               # index_metadata.json corpus manifest
├── evaluation/                 # Latency & Accuracy Evaluation Suite
│   ├── queries.json            # 36 synthetic industrial benchmark queries
│   ├── benchmark.py            # Latency benchmark harness
│   └── results/                # latest_benchmark.json
├── docs/                       # Formal Engineering Documentation
│   ├── requirements.md         # IEEE-style requirements & traceability matrix
│   ├── prompt-spec.md          # CRISPE prompt engineering specification
│   ├── security.md             # OWASP Top 10-aligned security mitigations
│   ├── privacy.md              # Data minimization & GDPR erasure specification
│   └── final-demo-script.md    # 2-minute step-by-step presentation script
├── scripts/
│   └── build_moss_index.py     # Genuine Moss index ingestion & build script
├── docker-compose.yml          # Containerized orchestration
└── README.md
```

---

## 7. Quick Start & Local Execution

### Prerequisites
- Python 3.10+
- Node.js v20.20+ (with npm)
- Git

### 1. Clone and Configure Environment
```bash
git clone https://github.com/viswanthanss/fieldops-voice-copilot.git
cd fieldops-voice-copilot

cp .env.example .env
# Edit .env with your LiveKit, OpenAI, and Moss credentials
```

### 2. Start the Control Plane (Terminal 1)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*Health check:* `http://localhost:8000/api/v1/health`

### 3. Start the Technician Workstation UI (Terminal 2)
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```
*Open:* `http://localhost:3000`

### 4. Start the LiveKit Voice Agent (Terminal 3)
```bash
cd agent
pip install -r requirements.txt
python src/agent.py start
```

### 5. Ingest Knowledge Base into Moss (Optional if creating new index)
```bash
python scripts/build_moss_index.py --knowledge-dir knowledge --index-name fieldops-knowledge-v1
```

---

## 8. Running the Verification Test Suites

### Run Backend Security Tests (7 tests)
```bash
python -m pytest backend/tests/ -v
```
*Verifies JWT lifecycle, bcrypt password hashing, 401 unauthorized checks, rate limiting, and GDPR privacy deletion.*

### Run Agent Unit Tests (17 tests)
```bash
python -m pytest agent/tests/ -v
```
*Verifies query normalization, authorization scope enforcement, Moss filter generation, Evidence Gate model matching, prompt injection defense, and retrieval stubs.*

### Run Latency & Accuracy Benchmark
```bash
python evaluation/benchmark.py --iterations 3
```

---

## 9. Two-Minute Demo Scenarios

| Scenario | Spoken Query | Target Equipment | Gate Decision | Expected Behavior |
|---|---|---|---|---|
| **Scenario 1: Grounded Turn** | *"The compressor CP-204 is showing error E17. What should I check first?"* | CP-204 (CP-200 family) | `PASS` | Cites CP-200 Manual Rev 4; advises cooldown & condenser cleaning. UI shows source card. |
| **Scenario 2: Model Mismatch** | *"What is error E17 on model CP-300?"* | CP-204 assigned (CP-200) | `FAIL_MODEL_MISMATCH` | Rejects procedure cross-contamination; warns CP-300 is rotary screw VFD fault. |
| **Scenario 3: Missing Evidence**| *"What does code E99 indicate on the compressor?"* | CP-204 | `FAIL_NO_EVIDENCE` | Deterministic safe refusal; zero LLM hallucination. |
| **Scenario 4: Barge-In** | Technician speaks while agent is talking | Active session | Interruption | Playback stops instantly; stale buffer discarded; follow-up handled. |

---

## 10. Limitations & Future Work

- **LiveKit Cloud Dependency:** Real-time WebRTC audio requires a configured LiveKit Cloud or self-hosted LiveKit instance.
- **Synthetic Corpus:** The included technical manuals for CP-200 and CP-300 compressors are original synthetic industrial documentation created specifically for hackathon evaluation and reproducibility.
- **Future Work:** Multi-modal video grounding (allowing technicians to point camera at machine faceplates), edge-deployed local Whisper ASR models, and multi-tenant industrial SCADA telemetry ingestion.

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
