import os
import sys
import pathlib
import pytest

# Ensure repository root and agent package are on sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agent"))

from agent.src.config import AgentConfig
from agent.src.retrieval import RetrievalResult, RetrievalResponse


@pytest.fixture
def sample_auth_context():
    return {
        "tenant_id": "demo",
        "site_ids": ["SITE-A"],
        "asset_ids": ["CP-204"],
        "roles": ["technician"],
        "user_id": "user-test-01",
    }


@pytest.fixture
def agent_config():
    return AgentConfig(
        evidence_min_score=0.65,
        moss_top_k=3,
    )


@pytest.fixture
def make_retrieval_result():
    def _maker(
        text="E17 indicates high discharge temperature above 185F. Inspect condenser coils and coolant level.",
        score=0.88,
        model="CP-200",
        document_id="CP200-SVC-001",
        revision="4",
        equipment_type="compressor",
    ):
        return RetrievalResult(
            text=text,
            score=score,
            document_id=document_id,
            document_type="service_manual",
            equipment_type=equipment_type,
            model=model,
            revision=revision,
            effective_date="2024-01-15",
            section="Section 7 - Error Codes",
            chunk_index=0,
            retrieval_latency_ms=4.2,
            index_version="1.0.0",
        )
    return _maker
