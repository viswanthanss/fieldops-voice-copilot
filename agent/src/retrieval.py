"""
Embedded Moss Retrieval Runtime for FieldOps Voice Copilot.

Loads the versioned Moss index into memory at agent startup.
All per-turn retrieval queries execute in-process against the embedded runtime (<10ms target),
keeping external cloud APIs and relational databases completely off the realtime hot path.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import structlog

from .config import AgentConfig

logger = structlog.get_logger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieved evidence chunk with rich equipment and document metadata."""
    text: str
    score: float
    document_id: str
    document_type: str
    equipment_type: str
    model: str
    revision: str
    effective_date: str
    section: str
    chunk_index: int
    retrieval_latency_ms: float
    index_version: str
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResponse:
    """Structured response from the embedded Moss runtime."""
    results: List[RetrievalResult]
    query: str
    latency_ms: float
    index_version: str
    retrieval_id: str
    top_score: float = 0.0

    def __post_init__(self):
        if self.results:
            self.top_score = max(r.score for r in self.results)


class MossRetriever:
    """
    Embedded Moss Runtime wrapper.
    
    Architecture:
    - Connected once at startup via MossClient.
    - Loads the pre-built index into embedded process memory via `load_index()`.
    - Realtime queries execute locally via `query()` with sub-10ms P95 latency.
    - Supports metadata filtering (e.g. tenant_id, model, site_id) derived from authorization context.
    """

    def __init__(self, config: AgentConfig, client: Optional[Any] = None):
        self._config = config
        self._client = client
        self._index_name = config.moss_index_name
        self._index_version = config.moss_index_version
        self._is_loaded = False
        self._load_latency_ms = 0.0

    async def initialize(self) -> None:
        """
        Pre-load the Moss index into embedded memory at agent startup.
        Called once during worker initialization before accepting voice sessions.
        """
        start = time.perf_counter()
        
        if not self._client:
            if not self._config.moss_project_id or not self._config.moss_project_key:
                err_msg = (
                    "MOSS CREDENTIALS MISSING: MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set. "
                    "To enable realtime embedded retrieval, obtain credentials at https://moss.dev "
                    "and add them to your environment."
                )
                logger.error("moss_credentials_missing", index_name=self._index_name)
                raise RuntimeError(err_msg)

            from moss import MossClient
            self._client = MossClient(
                self._config.moss_project_id,
                self._config.moss_project_key,
            )

        logger.info(
            "loading_embedded_moss_index",
            index_name=self._index_name,
            index_version=self._index_version,
        )

        try:
            # Load the index into local process memory for sub-10ms queries
            await self._client.load_index(self._index_name)
            self._is_loaded = True
            self._load_latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "embedded_moss_index_ready",
                index_name=self._index_name,
                load_time_ms=round(self._load_latency_ms, 2),
            )
        except Exception as exc:
            logger.error("embedded_moss_load_failed", error=str(exc))
            raise

    async def query(
        self,
        query_text: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResponse:
        """
        Execute in-process retrieval against the loaded Moss index.

        Args:
            query_text: The normalized search string.
            metadata_filter: Optional authorization-constrained metadata filter
                             (e.g. {"field": "model", "condition": {"$eq": "CP-200"}} or {"$and": [...]}).
            top_k: Maximum number of evidence chunks to retrieve.

        Returns:
            RetrievalResponse with scored evidence chunks and measured execution latency.
        """
        if not self._is_loaded and self._client is None:
            raise RuntimeError("Embedded Moss index is not loaded. Call initialize() before querying.")

        retrieval_id = f"ret-{uuid.uuid4().hex[:8]}"
        k = top_k or self._config.moss_top_k
        start = time.perf_counter()

        from moss import QueryOptions

        # Build official QueryOptions with metadata filter
        query_options = QueryOptions(
            top_k=k,
            filter=metadata_filter if metadata_filter else None,
        )

        try:
            search_result = await self._client.query(
                self._index_name,
                query_text,
                query_options,
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            logger.error("moss_query_failed", query=query_text, error=str(exc), latency_ms=latency)
            raise

        latency_ms = (time.perf_counter() - start) * 1000

        # Map official QueryResultDocumentInfo objects to domain RetrievalResult
        results: List[RetrievalResult] = []
        raw_docs = getattr(search_result, "docs", []) or []

        for doc in raw_docs:
            meta = getattr(doc, "metadata", None) or {}
            
            # Fallback to parsing payload JSON if metadata was stored in payload
            if not meta and hasattr(doc, "payload") and doc.payload:
                try:
                    meta = json.loads(doc.payload)
                except Exception:
                    pass

            score = float(getattr(doc, "score", 0.0))
            text = getattr(doc, "text", "")

            results.append(
                RetrievalResult(
                    text=text,
                    score=score,
                    document_id=meta.get("document_id", "DOC-UNKNOWN"),
                    document_type=meta.get("document_type", "manual"),
                    equipment_type=meta.get("equipment_type", "compressor"),
                    model=meta.get("model", "UNKNOWN"),
                    revision=str(meta.get("revision", "1")),
                    effective_date=meta.get("effective_date", ""),
                    section=meta.get("section", "general"),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    retrieval_latency_ms=latency_ms,
                    index_version=self._index_version,
                    raw_metadata=meta,
                )
            )

        logger.info(
            "moss_retrieval_success",
            retrieval_id=retrieval_id,
            query=query_text[:60],
            result_count=len(results),
            top_score=round(max((r.score for r in results), default=0.0), 3),
            latency_ms=round(latency_ms, 2),
        )

        return RetrievalResponse(
            results=results,
            query=query_text,
            latency_ms=latency_ms,
            index_version=self._index_version,
            retrieval_id=retrieval_id,
        )

    @property
    def is_ready(self) -> bool:
        return self._is_loaded

    @property
    def index_version(self) -> str:
        return self._index_version
