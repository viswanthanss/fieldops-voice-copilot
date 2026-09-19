# FieldOps Voice Copilot — Privacy & Data Minimization Architecture

**Version:** 1.0.0  
**Date:** September 2026  
**Scope:** Realtime Audio Streaming & Industrial Operational Logs  

> **Privacy Notice:** This document outlines privacy-by-design principles and data minimization practices implemented in FieldOps Voice Copilot. It describes technical controls and does not constitute formal legal certification.

---

## 1. Privacy-by-Design Principles

FieldOps Voice Copilot is engineered around four core privacy principles:

1. **Zero Raw Audio Persistence:** Realtime WebRTC audio packets passing through LiveKit and the Python agent STT pipeline are processed in ephemeral memory buffers. Audio streams are never recorded, serialized, or stored on disk by default.
2. **Data Minimization (GDPR Article 5):** Only operational telemetry necessary to audit equipment safety and pipeline latency is retained. Personal technician identifiers are strictly segregated from diagnostic evidence.
3. **Short-Lived Conversation Context:** Spoken transcripts and multi-turn state are stored ephemerally in `SessionStore` (in-memory for development, Redis with automatic TTL expiration in production).
4. **Technician Data Sovereignty:** Direct GDPR Article 17 ("Right to Erasure") self-service API endpoints enable technicians to permanently purge their sessions and feedback.

---

## 2. Data Classification Matrix

| Data Element | Storage Location | Retention Period | Encryption / Protection |
|---|---|---|---|
| **Raw Technician Voice Stream** | Ephemeral RAM (WebRTC buffer) | 0 seconds (discarded post-STT) | WebSockets / WebRTC DTLS-SRTP |
| **Spoken Transcripts** | SessionStore (Redis / In-Memory) | Active session TTL (default 2h) | In-memory / Redis TLS |
| **Retrieved Technical Evidence** | Embedded Moss Index (Process memory) | Read-only static lifecycle | Preloaded local memory |
| **Audit Logs** | PostgreSQL / SQLite `audit_events` | Configurable (default 90 days) | Encrypted at rest (provider-level) |
| **User Credentials** | `users` table | Account lifetime | Bcrypt password hash (rounds=12) |
| **Session Authorization Context** | JWT claims + DB session record | 30 minutes (token expiry) | HS256 JWT cryptographic signature |

---

## 3. Data Minimization Controls

### Log Masking
- User registration logs mask domain information and truncate emails (e.g. `tech@industrial.test` -> `tec***`).
- Failed authentication logs do not record plaintext attempted passwords.
- Operational telemetry spans record `session_id` and `turn_id` UUIDs, omitting technician names.

### Ephemeral State Isolation
- The `SessionStore` interface (`agent/src/session.py`) enforces strict boundaries:
  - `InMemorySessionStore` clears upon process termination.
  - `RedisSessionStore` attaches automated key expiration (`EXPIRE {session_id} 7200`) so inactive conversations expire automatically.

---

## 4. GDPR Article 17 Data Erasure Workflow

Technicians can exercise their right to erasure at any time via the control plane:

```http
POST /api/v1/privacy/delete HTTP/1.1
Host: localhost:8000
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "confirm": true,
  "reason": "Technician requested GDPR erasure"
}
```

### Execution Lifecycle (`backend/app/privacy.py`):
1. **Audit Event:** Records `DATA_DELETION_REQUEST` with user ID before purging.
2. **Session Records:** Purges all session records associated with the user ID from `sessions`.
3. **Feedback Records:** Purges all user feedback ratings and comments from `feedback`.
4. **Audit Anonymization:** Scrubs user-identifiable fields in past audit events, replacing `user_id` with `ANONYMIZED_USER`.
5. **Account Deactivation:** Sets `is_active = False` on the user record.
6. **Response:** Returns an itemized summary of purged records to the caller (HTTP 200).
