# FieldOps Voice Copilot — 2-Minute Live Demo Script

**Hackathon:** YC Fall 2026 × Moss — The Zero Latency Builder Sprint  
**Track:** Real-Time Voice and Conversational AI  
**Time Limit:** 120 seconds  

---

## Preparation & Pre-Flight Checklist

1. **Terminal 1 (Backend Control Plane):**
   ```powershell
   $env:PATH = "C:\Users\hp\AppData\Local\Programs\Python\Python310;C:\Users\hp\AppData\Local\Programs\Python\Python310\Scripts;" + $env:PATH
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. **Terminal 2 (Frontend Technician UI):**
   ```powershell
   $env:PATH = "C:\Users\hp\AppData\Roaming\fnm\node-versions\v20.20.2\installation;" + $env:PATH
   cd frontend
   npm run dev
   ```
   Open `http://localhost:3000` in Chrome/Edge.
3. **Terminal 3 (LiveKit Realtime Agent):**
   ```powershell
   $env:PATH = "C:\Users\hp\AppData\Local\Programs\Python\Python310;C:\Users\hp\AppData\Local\Programs\Python\Python310\Scripts;" + $env:PATH
   cd agent
   python src/agent.py start
   ```

---

## 2-Minute Chronological Script

### [0:00 – 0:15] The Hook & The Problem
> **Presenter:** "Industrial field technicians diagnosing high-pressure compressors face two critical constraints: their hands are occupied with tools, and a hallucinated procedure can trigger an emergency plant shutdown or fatal safety breach. Traditional voice assistants are too slow and fabricate answers when documentation is missing.
> 
> Meet **FieldOps Voice Copilot** — the first evidence-gated, low-latency realtime voice AI built directly on an embedded, in-process Moss retrieval runtime."

---

### [0:15 – 0:45] Scenario 1: Grounded Retrieval & Source Attribution
*(Action: Click 'Start Voice Session' on the Next.js workstation UI. Status dot turns emerald.)*

> **Presenter (Speaks hands-free into headset):**
> *"The compressor CP-204 is showing error E17. What should I check first?"*

**What happens on screen:**
1. Live transcript streams technician's utterance instantly via LiveKit.
2. Query Normalizer extracts canonical parameters: `model=CP-200`, `error_code=E17`, `asset_id=CP-204`.
3. Pre-retrieval scope check confirms technician is authorized for `CP-204` at `SITE-A`.
4. Embedded Moss runtime retrieves top chunks in process memory.
5. Evidence Sufficiency Gate evaluates relevance, model match, and document revision -> **PASS**.
6. LLM generates grounded 2-sentence guidance.
7. Grounding Validator cross-checks all factual claims -> **PASS**.
8. Voice Copilot speaks immediately over LiveKit streaming audio:
   > *"According to the CP-200 Service Manual Revision 4, error E17 indicates high discharge temperature exceeding 185 degrees. First ensure unit isolation, then inspect the condenser fins for dust fouling."*
9. Evidence Panel displays the exact source: `CP200-SVC-001 Rev 4 Section 7`, relevance score, and local execution breakdown (&lt;1ms pre-LLM CPU time).

---

### [0:45 – 1:10] Scenario 2: Model Mismatch Protection (CP-200 vs CP-300)
> **Presenter:** "Now watch what happens when we ask about a different equipment model. CP-200 E17 is high discharge temperature, but on a CP-300, E17 is a motor frequency inverter fault. A generic RAG system would cross-contaminate."

*(Action: Speak into mic or click Scenario 2 shortcut)*
> **Presenter:** *"What is the procedure for error E17 on model CP-300?"*

**What happens on screen:**
1. Moss retrieves CP-300 manual chunks.
2. Evidence Sufficiency Gate detects model conflict between technician's assigned `CP-204` (CP-200 family) and queried `CP-300` -> **`FAIL_MODEL_MISMATCH`**.
3. Zero LLM hallucination occurs. Gate immediately triggers safe refusal audio:
   > *"Safety notice: Retrieved documentation is for model CP-300, which does not match your assigned equipment CP-200. Procedures cannot be safely transferred between these models."*
4. UI highlights the model isolation boundary in amber.

---

### [1:10 – 1:30] Scenario 3: Unknown Error / Missing Evidence Refusal
*(Action: Speak or click Scenario 3 shortcut)*
> **Presenter:** *"What does error code E99 indicate on the compressor?"*

**What happens on screen:**
1. Search query executed across embedded index.
2. No documentation exists for `E99` -> **`FAIL_NO_EVIDENCE`**.
3. Voice Copilot speaks deterministic safe fallback:
   > *"I do not have authorized documentation in the knowledge base for this query. Please verify the equipment model and error code with plant engineering."*
4. UI displays Evidence Sufficiency Gate Refusal card. Zero hallucinated procedures emitted.

---

### [1:30 – 1:45] Scenario 4: Barge-In / Interruption Handling
*(Action: Ask a question, and while the agent is speaking, speak immediately)*

> **Presenter:** *"What are the safety steps before opening the condenser cover?"*
> *(Copilot begins speaking: "Per standard operating procedure...")*
> **Presenter (Interrupts loudly):** *"Wait — what about the oil level?"*

**What happens on screen:**
1. LiveKit VAD detects barge-in instantly.
2. Agent immediately terminates audio playback.
3. Stale completion buffer is discarded.
4. Agent processes the new question and delivers the oil level procedure seamlessly.

---

### [1:45 – 2:00] Architecture & Technical Summary
> **Presenter:** "To summarize our technical architecture:
> 1. **Zero Cloud Hot Path:** The Moss index is loaded into embedded memory at startup; per-turn retrieval happens locally in-process with sub-10ms P95 latency.
> 2. **Deterministic Evidence Gate:** Pre-LLM gating guarantees unsafe or mismatched procedures are rejected before the generator is even called.
> 3. **LiveKit Realtime Transport:** Sub-500ms voice pipeline with full barge-in and rich data-channel source attribution.
> 4. **No Fabricated Benchmarks:** Every latency and security claim is tested with 17 agent unit tests, 7 backend security tests, and reproducible benchmarks.
> 
> FieldOps Voice Copilot brings real-time zero-latency reliability to the industrial front line. Thank you."
