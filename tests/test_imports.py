"""Ensure the planned modules are importable before later phases implement them."""

import importlib


def test_project_modules_import() -> None:
    modules = (
        "app.config",
        "app.models",
        "app.scraper",
        "app.document_loader",
        "app.chunker",
        "app.embeddings",
        "app.vector_store",
        "app.retrieval",
        "app.guardrails",
        "app.llm",
        "app.ui",
    )

    for module in modules:
        importlib.import_module(module)

