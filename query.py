"""Command-line entry point for the Phase 7 grounded query pipeline."""

from __future__ import annotations

import argparse

from app.llm import QueryService


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the facts-only HDFC fund assistant")
    parser.add_argument("--question", required=True, help="Question to answer")
    arguments = parser.parse_args()
    response = QueryService().answer(arguments.question)
    print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
