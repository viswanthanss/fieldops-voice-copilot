"""
Unit tests for MossRetriever wrapper.
Tests initialization, error handling, metadata filtering, and result mapping with mock client.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.src.config import AgentConfig
from agent.src.retrieval import MossRetriever, RetrievalResponse


@pytest.mark.asyncio
async def test_moss_retriever_missing_credentials():
    """Retriever must raise clear error if Moss credentials are missing."""
    config = AgentConfig(moss_project_id="", moss_project_key="")
    retriever = MossRetriever(config)

    with pytest.raises(RuntimeError) as exc_info:
        await retriever.initialize()

    assert "MOSS CREDENTIALS MISSING" in str(exc_info.value)
    assert "https://moss.dev" in str(exc_info.value)


@pytest.mark.asyncio
async def test_moss_retriever_query_with_mock_client():
    """Retriever correctly queries loaded index and maps SearchResult."""
    config = AgentConfig(
        moss_project_id="test-proj",
        moss_project_key="test-key",
        moss_index_name="test-index",
        moss_top_k=2,
    )

    # Mock official Moss SearchResult and QueryResultDocumentInfo
    mock_doc = MagicMock()
    mock_doc.text = "E17 on CP-200: High discharge temperature."
    mock_doc.score = 0.94
    mock_doc.metadata = {
        "document_id": "CP200-SVC-001",
        "document_type": "service_manual",
        "equipment_type": "compressor",
        "model": "CP-200",
        "revision": "4",
        "effective_date": "2024-01-15",
        "section": "Section 7",
        "chunk_index": 1,
    }
    mock_doc.payload = None

    mock_search_result = MagicMock()
    mock_search_result.docs = [mock_doc]

    mock_client = MagicMock()
    mock_client.load_index = AsyncMock()
    mock_client.query = AsyncMock(return_value=mock_search_result)

    retriever = MossRetriever(config, client=mock_client)
    await retriever.initialize()

    assert retriever.is_ready is True
    mock_client.load_index.assert_awaited_once_with(config.moss_index_name)

    response = await retriever.query("CP-204 E17", metadata_filter={"model": "CP-200"})

    assert isinstance(response, RetrievalResponse)
    assert len(response.results) == 1
    top = response.results[0]
    assert top.model == "CP-200"
    assert top.score == 0.94
    assert top.document_id == "CP200-SVC-001"
    assert response.latency_ms > 0
