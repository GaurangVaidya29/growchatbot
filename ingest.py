"""Command-line entry point for the phased ingestion pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import ensure_data_directories, load_config
from app.chunker import build_chunks, load_chunks, write_chunk_artifacts
from app.document_loader import load_documents, write_load_manifest
from app.embeddings import EmbeddingService, embed_chunks, write_embedding_manifest
from app.scraper import ApprovedPageScraper, load_source_registry
from app.vector_store import ChromaVectorStore


IMPLEMENTED_STAGES = {"config", "scrape", "load", "chunk", "index"}
ALL_STAGES = ("config", "scrape", "load", "chunk", "index")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Groww FAQ ingestion pipeline")
    parser.add_argument("--stage", choices=ALL_STAGES, default="config")
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    directories = ensure_data_directories(config)

    if args.stage not in IMPLEMENTED_STAGES:
        print(f"Stage '{args.stage}' is planned but not implemented yet.")
        return 2

    if args.stage == "config":
        print("Configuration is valid.")
        print(f"Embedding model: {config.embeddings.model}")
        print(f"Vector collection: {config.vector_db.collection}")
        print(f"Data directories checked: {len(directories)}")
        return 0

    if args.stage == "scrape":
        sources = load_source_registry()
        with ApprovedPageScraper(config.scraping) as scraper:
            results = scraper.scrape_all(sources)

        for result in results:
            message = f"{result.source_id}: {result.status}"
            if result.error:
                message += f" - {result.error}"
            print(message)
        successful = sum(result.status == "SUCCESS" for result in results)
        print(f"Scraped {successful}/{len(results)} approved pages.")
        return 0 if successful == len(results) else 1

    if args.stage == "load":
        result = load_documents()
        manifest_path = write_load_manifest(result)
        print(f"Loaded {result.loaded_count}/{result.expected_count} validated documents.")
        print(f"Load manifest: {manifest_path.relative_to(Path.cwd())}")
        return 0

    if args.stage == "chunk":
        loaded = load_documents()
        result = build_chunks(loaded.documents, config.chunking)
        chunks_path, manifest_path = write_chunk_artifacts(result)
        print(f"Created {len(result.chunks)} chunks from {result.source_count} sources.")
        print(f"Skipped sections: {result.skipped_sections}")
        print(f"Chunk file: {chunks_path.relative_to(Path.cwd())}")
        print(f"Chunk manifest: {manifest_path.relative_to(Path.cwd())}")
        return 0

    chunks = load_chunks()
    embedding_service = EmbeddingService(config.embeddings)
    embedding_batch = embed_chunks(chunks, embedding_service)
    embedding_manifest = write_embedding_manifest(chunks, embedding_batch)
    store = ChromaVectorStore(config.vector_db)
    index_manifest = store.build_index(chunks, embedding_batch)
    print(
        f"Embedded and indexed {index_manifest.chunk_count} chunks "
        f"with {index_manifest.embedding_model}."
    )
    print(f"Embedding dimension: {index_manifest.embedding_dimension}")
    print(f"Active collection: {index_manifest.active_collection}")
    print(f"Embedding manifest: {embedding_manifest.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

