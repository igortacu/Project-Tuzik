"""Command-line entry point: `python -m second_brain index|query`."""

import argparse
import sys
from pathlib import Path

from second_brain import config
from second_brain.pipelines import index_pipeline, query_pipeline


def _cmd_index(args: argparse.Namespace) -> int:
    vault_path = args.vault_path or config.VAULT_PATH
    if not vault_path:
        print(
            "No vault path given (pass --vault-path or set OBSIDIAN_VAULT_PATH in .env)",
            file=sys.stderr,
        )
        return 1

    print(f"Indexing vault at {vault_path} ...")
    index_pipeline.full_rebuild(Path(vault_path))
    print("Done.")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    answer = query_pipeline.answer_query(args.question, top_k=args.top_k)
    print(answer)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="second_brain", description="Local RAG pipeline over an Obsidian vault."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser(
        "index", help="Full rebuild of the index from the vault."
    )
    index_parser.add_argument(
        "--vault-path", default=None, help="Override OBSIDIAN_VAULT_PATH from .env"
    )
    index_parser.set_defaults(func=_cmd_index)

    query_parser = subparsers.add_parser("query", help="Ask a question against the indexed vault.")
    query_parser.add_argument("question", help="The question to ask.")
    query_parser.add_argument("--top-k", type=int, default=None, help="Override config.TOP_K")
    query_parser.set_defaults(func=_cmd_query)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
