"""
Deterministic Query Normalizer for FieldOps Voice Copilot.

Extracts equipment types, asset IDs, model families, error codes, and operational
intents in sub-millisecond time using regex and heuristic parsing without any remote LLM calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NormalizedQuery:
    """Structured representation of a technician's voice query."""
    original: str
    cleaned: str
    equipment_type: Optional[str] = None  # e.g. "compressor", "pump", "generator"
    model: Optional[str] = None           # e.g. "CP-200", "CP-300"
    asset_id: Optional[str] = None        # e.g. "CP-204", "CP-301", "PUMP-102"
    error_code: Optional[str] = None      # e.g. "E17", "E08", "E03"
    intent: str = "general"               # "troubleshooting", "procedure", "specification", "status"
    symptom: Optional[str] = None         # e.g. "won't restart", "overheating", "vibrating"
    keywords: List[str] = field(default_factory=list)

    @property
    def search_query(self) -> str:
        """
        Synthesize an optimized retrieval query string prioritizing high-signal terms.
        """
        tokens = []
        if self.model:
            tokens.append(self.model)
        if self.error_code:
            tokens.append(self.error_code)
        if self.symptom:
            tokens.append(self.symptom)
        if self.equipment_type and not self.model:
            tokens.append(self.equipment_type)
        
        # If no specific tokens extracted, fallback to the cleaned original
        if not tokens:
            return self.cleaned
        return " ".join(tokens) + " " + self.cleaned


# Regex patterns for deterministic extraction
RE_ERROR_CODE = re.compile(r"\b[Ee](\d{1,3})\b", re.IGNORECASE)
RE_ASSET_ID = re.compile(r"\b([A-Za-z]{2,4}-\d{3,4}[A-Za-z]?)\b")
RE_CP200_FAMILY = re.compile(r"\b(CP-?2\d{2})\b", re.IGNORECASE)
RE_CP300_FAMILY = re.compile(r"\b(CP-?3\d{2})\b", re.IGNORECASE)

EQUIPMENT_KEYWORDS = {
    "compressor": ["compressor", "reciprocating", "rotary screw", "air compressor"],
    "pump": ["pump", "centrifugal pump", "vacuum pump"],
    "motor": ["motor", "drive", "vfd", "inverter"],
    "generator": ["generator", "genset", "alternator"],
}

INTENT_KEYWORDS = {
    "troubleshooting": [
        "error", "code", "fault", "alarm", "trip", "tripped", "failing", "failed",
        "won't start", "wont start", "won't restart", "wont restart", "stopped",
        "overheating", "hot", "vibrating", "leak", "leaking", "smoke", "noise"
    ],
    "procedure": [
        "how to", "how do i", "steps to", "procedure", "replace", "replacement",
        "clean", "cleaning", "restart", "reset", "calibrate", "inspect", "service",
        "maintenance", "oil change", "filter change"
    ],
    "specification": [
        "spec", "specification", "specs", "pressure", "temperature", "tolerance",
        "torque", "voltage", "amperage", "rating", "capacity", "rpm", "clearance"
    ],
    "status": [
        "status", "condition", "state", "operational", "running"
    ]
}

SYMPTOM_PATTERNS = [
    (re.compile(r"\b(won'?t\s+restart|cannot\s+restart|unable\s+to\s+restart)\b", re.I), "won't restart"),
    (re.compile(r"\b(won'?t\s+start|cannot\s+start|unable\s+to\s+start)\b", re.I), "won't start"),
    (re.compile(r"\b(overheating|high\s+temp|too\s+hot|discharge\s+temp)\b", re.I), "overheating"),
    (re.compile(r"\b(vibrat(ing|ion)|shaking|abnormal\s+vibration)\b", re.I), "vibration"),
    (re.compile(r"\b(low\s+pressure|pressure\s+drop|loss\s+of\s+pressure)\b", re.I), "low pressure"),
    (re.compile(r"\b(oil\s+leak|air\s+leak|coolant\s+leak)\b", re.I), "leak"),
]


def normalize_query(text: str) -> NormalizedQuery:
    """
    Deterministically normalizes a raw voice transcript into structured technical context.
    Executes in <1ms without any external network or LLM calls.
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    lower = cleaned.lower()

    # 1. Error code extraction (e.g. E17, e17, E-17 -> E17)
    error_code = None
    err_match = RE_ERROR_CODE.search(cleaned)
    if err_match:
        code_num = err_match.group(1).zfill(2)
        error_code = f"E{code_num}"

    # 2. Asset ID and Model Family extraction
    asset_id = None
    model = None

    # Check for specific asset ID pattern (e.g. CP-204, CP-301)
    asset_match = RE_ASSET_ID.search(cleaned)
    if asset_match:
        raw_asset = asset_match.group(1).upper()
        # Canonicalize hyphen
        if "-" not in raw_asset and len(raw_asset) >= 5:
            raw_asset = f"{raw_asset[:2]}-{raw_asset[2:]}"
        asset_id = raw_asset

    # Model family mapping
    if RE_CP200_FAMILY.search(cleaned):
        model = "CP-200"
    elif RE_CP300_FAMILY.search(cleaned):
        model = "CP-300"
    elif asset_id:
        if asset_id.startswith("CP-2"):
            model = "CP-200"
        elif asset_id.startswith("CP-3"):
            model = "CP-300"

    # 3. Equipment type extraction
    equipment_type = None
    for eq_type, keywords in EQUIPMENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            equipment_type = eq_type
            break
    if not equipment_type and model and model.startswith("CP-"):
        equipment_type = "compressor"

    # 4. Intent classification
    intent = "general"
    intent_scores = {}
    for candidate_intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            intent_scores[candidate_intent] = score
    if intent_scores:
        intent = max(intent_scores.items(), key=lambda x: x[1])[0]

    # 5. Symptom extraction
    symptom = None
    for pattern, sym_label in SYMPTOM_PATTERNS:
        if pattern.search(lower):
            symptom = sym_label
            break

    # 6. Extract search keywords
    words = re.findall(r"\b[A-Za-z0-9_-]{3,}\b", cleaned)
    stop_words = {"the", "and", "for", "with", "what", "should", "first", "check", "how", "this", "that"}
    keywords = [w for w in words if w.lower() not in stop_words]

    return NormalizedQuery(
        original=text,
        cleaned=cleaned,
        equipment_type=equipment_type,
        model=model,
        asset_id=asset_id,
        error_code=error_code,
        intent=intent,
        symptom=symptom,
        keywords=keywords,
    )
