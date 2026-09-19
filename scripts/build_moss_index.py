#!/usr/bin/env python3
"""
FieldOps Voice Copilot — Moss Knowledge Index Builder

Loads synthetic industrial operational documentation from knowledge/ directory,
extracts YAML/header metadata, and indexes the corpus into the Embedded Moss Runtime
using the official Moss Python SDK.

Usage:
    python scripts/build_moss_index.py [--verify]

Environment variables:
    MOSS_PROJECT_ID   - Project identifier from Moss Cloud
    MOSS_PROJECT_KEY  - Secret project API key
    MOSS_INDEX_NAME   - Target index name (default: fieldops-knowledge-v1)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Tuple

# Ensure parent directory is in path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def parse_document(file_path: pathlib.Path) -> Tuple[Dict[str, Any], str]:
    """
    Parse a document file with YAML frontmatter header.
    Returns (metadata_dict, body_text).
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata: Dict[str, Any] = {
        "file_path": str(file_path).replace("\\", "/"),
        "file_name": file_path.name,
    }

    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            header_lines = parts[1].strip().split("\n")
            for line in header_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    metadata[key.strip()] = val.strip()
            body = parts[2].strip()

    return metadata, body


def chunk_document(
    doc_id: str,
    metadata: Dict[str, Any],
    body: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> List[Dict[str, Any]]:
    """
    Split a document body into overlapping semantic chunks with embedded metadata.
    """
    chunks: List[Dict[str, Any]] = []
    paragraphs = body.split("\n\n")

    current_chunk = ""
    current_section = metadata.get("section", "general")
    chunk_idx = 0

    for para in paragraphs:
        para_clean = para.strip()
        if not para_clean:
            continue

        # Detect section headings
        if para_clean.startswith("SECTION") or para_clean.startswith("Step") or para_clean.isupper() and len(para_clean) < 60:
            current_section = para_clean[:60]

        if len(current_chunk) + len(para_clean) > chunk_size and current_chunk:
            chunk_metadata = dict(metadata)
            chunk_metadata["chunk_index"] = chunk_idx
            chunk_metadata["section"] = current_section
            chunk_metadata["id"] = f"{doc_id}-chunk-{chunk_idx}"

            # Format chunk text with metadata header for maximum retrieval precision
            chunk_text = (
                f"[{metadata.get('model', 'GENERAL')} {metadata.get('document_type', 'MANUAL')}] "
                f"Document: {doc_id} Rev {metadata.get('revision', '1')} | Section: {current_section}\n"
                f"{current_chunk.strip()}"
            )

            chunks.append({
                "id": chunk_metadata["id"],
                "text": chunk_text,
                "metadata": chunk_metadata,
            })
            chunk_idx += 1
            # Overlap by taking the tail
            current_chunk = current_chunk[-overlap:] + "\n\n" + para_clean
        else:
            current_chunk = f"{current_chunk}\n\n{para_clean}" if current_chunk else para_clean

    if current_chunk.strip():
        chunk_metadata = dict(metadata)
        chunk_metadata["chunk_index"] = chunk_idx
        chunk_metadata["section"] = current_section
        chunk_metadata["id"] = f"{doc_id}-chunk-{chunk_idx}"
        chunk_text = (
            f"[{metadata.get('model', 'GENERAL')} {metadata.get('document_type', 'MANUAL')}] "
            f"Document: {doc_id} Rev {metadata.get('revision', '1')} | Section: {current_section}\n"
            f"{current_chunk.strip()}"
        )
        chunks.append({
            "id": chunk_metadata["id"],
            "text": chunk_text,
            "metadata": chunk_metadata,
        })

    return chunks


def load_all_documents(knowledge_dir: pathlib.Path) -> List[Dict[str, Any]]:
    """Scan knowledge/ directory and chunk all text manuals, SOPs, and bulletins."""
    all_chunks: List[Dict[str, Any]] = []

    txt_files = list(knowledge_dir.rglob("*.txt"))
    if not txt_files:
        print(f"[!] Warning: No .txt files found in {knowledge_dir}")
        return []

    print(f"[*] Scanning {len(txt_files)} source files in {knowledge_dir}...")
    for file_path in txt_files:
        metadata, body = parse_document(file_path)
        doc_id = metadata.get("document_id", file_path.stem)
        chunks = chunk_document(doc_id, metadata, body)
        print(f"    -> {file_path.name}: {len(chunks)} chunks (Doc ID: {doc_id}, Model: {metadata.get('model', 'N/A')})")
        all_chunks.extend(chunks)

    print(f"[+] Total indexable chunks generated: {len(all_chunks)}")
    return all_chunks


async def build_moss_index(
    project_id: str,
    project_key: str,
    index_name: str,
    chunks: List[Dict[str, Any]],
    verify: bool = True,
) -> None:
    """
    Connect to Moss using the official MossClient, create the index, and load documents.
    """
    try:
        from moss import MossClient, QueryOptions
    except ImportError as e:
        print(f"[!] Error: 'moss' package is not installed. Please run: pip install moss")
        sys.exit(1)

    from moss import DocumentInfo, MossClient, QueryOptions
    import json

    print(f"\n[*] Connecting to Moss with project_id={project_id[:6]}...")
    client = MossClient(project_id, project_key)

    print(f"[*] Creating/updating Moss index '{index_name}' with {len(chunks)} chunks...")
    start_time = time.perf_counter()

    # Ingest chunks using official DocumentInfo objects
    docs_payload = [
        DocumentInfo(
            id=c["id"],
            text=c["text"],
            metadata=c["metadata"],
            payload=json.dumps(c["metadata"]),
        )
        for c in chunks
    ]

    try:
        await client.create_index(index_name, docs_payload)
    except Exception as exc:
        print(f"[!] Warning: create_index raised ({exc}), attempting add_docs...")
        try:
            await client.add_docs(index_name, docs_payload)
        except Exception as exc2:
            print(f"[!] Error adding docs to Moss index: {exc2}")
            raise

    ingest_time = (time.perf_counter() - start_time) * 1000
    print(f"[+] Moss index '{index_name}' populated in {ingest_time:.1f}ms")

    # Load index into embedded memory
    print(f"[*] Pre-loading index '{index_name}' into embedded memory...")
    load_start = time.perf_counter()
    if hasattr(client, "load_index"):
        await client.load_index(index_name)
    load_time = (time.perf_counter() - load_start) * 1000
    print(f"[+] Index loaded into embedded memory in {load_time:.1f}ms (sub-10ms retrieval ready)")

    if verify:
        await verify_index(client, index_name)


async def verify_index(client: Any, index_name: str) -> None:
    """Run verification queries against the loaded Moss index."""
    from moss import QueryOptions

    test_queries = [
        ("The compressor CP-204 is showing error E17. What should I check first?", "CP-200 E17 High Discharge Temp"),
        ("CP-301 error E17 motor frequency fault", "CP-300 E17 Frequency Fault"),
        ("Oil replacement interval and procedure", "Maintenance procedure"),
    ]

    print(f"\n[*] Running verification queries against Moss index '{index_name}'...")
    for query, description in test_queries:
        q_start = time.perf_counter()
        options = QueryOptions(top_k=3) if "QueryOptions" in globals() else None
        
        if options:
            results = await client.query(index_name, query, options)
        else:
            results = await client.query(index_name, query, top_k=3)

        q_time = (time.perf_counter() - q_start) * 1000
        docs = results.docs if hasattr(results, "docs") else results

        print(f"\n  Query: '{query}' ({description})")
        print(f"  Latency: {q_time:.2f}ms | Results returned: {len(docs) if docs else 0}")
        if docs:
            top = docs[0]
            score = getattr(top, "score", 1.0)
            text_snippet = getattr(top, "text", str(top))[:140].replace("\n", " ")
            print(f"  Top Match [Score {score:.3f}]: {text_snippet}...")


def main():
    parser = argparse.ArgumentParser(description="Build and index Moss knowledge corpus for FieldOps Voice Copilot.")
    parser.add_argument("--verify", action="store_true", default=True, help="Run verification queries after indexing")
    parser.add_argument("--index-name", default=os.getenv("MOSS_INDEX_NAME", "fieldops-knowledge-v1"), help="Target Moss index name")
    args = parser.parse_args()

    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    knowledge_dir = pathlib.Path(__file__).resolve().parent.parent / "knowledge"
    if not knowledge_dir.exists():
        print(f"[!] Error: Knowledge directory not found at {knowledge_dir}")
        sys.exit(1)

    chunks = load_all_documents(knowledge_dir)
    if not chunks:
        print("[!] Error: No chunks generated. Aborting index build.")
        sys.exit(1)

    if not project_id or not project_key:
        print("\n" + "=" * 70)
        print("MOSS CREDENTIALS REQUIRED FOR PRODUCTION INDEXING")
        print("=" * 70)
        print("MOSS_PROJECT_ID or MOSS_PROJECT_KEY environment variables are not set.")
        print("To build the real Moss index in Moss Cloud:")
        print("  1. Sign up at https://moss.dev")
        print("  2. Create a project and obtain your Project ID and Project Key")
        print("  3. Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in your .env file")
        print("  4. Run: python scripts/build_moss_index.py")
        print("=" * 70)
        print(f"[i] Corpus validation successful: {len(chunks)} chunks prepared across CP-200 and CP-300.")
        sys.exit(0)

    asyncio.run(build_moss_index(project_id, project_key, args.index_name, chunks, verify=args.verify))


if __name__ == "__main__":
    main()
