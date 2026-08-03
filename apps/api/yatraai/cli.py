"""YatraAI command line: seed, pipeline, experiments and maintenance tasks."""

from __future__ import annotations

import argparse
import json
import sys

from yatraai.config import get_settings
from yatraai.logging_config import configure_logging, get_logger

log = get_logger("yatraai.cli")


# --------------------------------------------------------------------------- #
def cmd_seed(args: argparse.Namespace) -> int:
    from yatraai.db.session import ensure_extensions, session_scope
    from yatraai.seed.loader import load_all_seed_data

    ensure_extensions()
    with session_scope() as session:
        counts = load_all_seed_data(
            session,
            include_knowledge=args.knowledge,
            build_embeddings=args.embeddings,
        )
    print(json.dumps({"status": "ok", **counts}, indent=2))
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    from yatraai.pipelines import medallion

    if args.all:
        results = medallion.run_all()
    elif args.layer == "bronze":
        results = {"bronze": medallion.run_bronze()}
    elif args.layer == "silver":
        results = medallion.run_silver()
    else:
        results = medallion.run_gold()

    summary = {
        name: {
            "layer": r.layer,
            "rows_in": r.rows_in,
            "rows_out": r.rows_out,
            "rejected": r.rows_rejected,
            "ms": round(r.duration_ms, 1),
            "path": r.path,
        }
        for name, r in results.items()
    }
    print(json.dumps(summary, indent=2))
    total_rejected = sum(r.rows_rejected for r in results.values())
    if total_rejected and args.strict:
        print(f"FAILED: {total_rejected} rows rejected (strict mode)", file=sys.stderr)
        return 1
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Create tables directly from metadata (dev/demo shortcut for alembic)."""
    from yatraai.db import models  # noqa: F401
    from yatraai.db.base import Base
    from yatraai.db.session import ensure_extensions, get_engine

    ensure_extensions()
    Base.metadata.create_all(get_engine())
    print(json.dumps({"status": "ok", "tables": len(Base.metadata.tables)}, indent=2))
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    from yatraai.db.session import session_scope
    from yatraai.seed.knowledge_builder import embed_missing_chunks

    with session_scope() as session:
        written = embed_missing_chunks(session)
    print(json.dumps({"status": "ok", "embeddings_written": written}, indent=2))
    return 0


def cmd_purge_locations(args: argparse.Namespace) -> int:
    from yatraai.db.session import session_scope
    from yatraai.services.location import purge_expired_location_data

    with session_scope() as session:
        stats = purge_expired_location_data(session)
    print(json.dumps({"status": "ok", **stats}, indent=2))
    return 0


def cmd_demo_user(args: argparse.Namespace) -> int:
    from yatraai.db.session import session_scope
    from yatraai.services.demo import ensure_demo_data

    with session_scope() as session:
        info = ensure_demo_data(session, reset=args.reset)
    print(json.dumps({"status": "ok", **info}, indent=2, default=str))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from yatraai.services.status import service_status_snapshot

    s = get_settings()
    print(
        json.dumps(
            {
                "env": s.yatra_env,
                "database": "postgres" if s.uses_postgres else "sqlite",
                "providers": service_status_snapshot(),
            },
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yatraai", description="YatraAI operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Load the curated catalogue (idempotent)")
    p_seed.add_argument("--knowledge", action="store_true", help="also build the RAG corpus")
    p_seed.add_argument("--embeddings", action="store_true", help="also embed knowledge chunks")
    p_seed.set_defaults(func=cmd_seed)

    p_pipe = sub.add_parser("pipeline", help="Run Bronze/Silver/Gold transformations")
    p_pipe.add_argument("--all", action="store_true", help="run every layer in order")
    p_pipe.add_argument("--layer", choices=["bronze", "silver", "gold"], default="bronze")
    p_pipe.add_argument("--strict", action="store_true", help="exit non-zero if rows are rejected")
    p_pipe.set_defaults(func=cmd_pipeline)

    sub.add_parser("migrate", help="Create tables from ORM metadata").set_defaults(func=cmd_migrate)
    sub.add_parser("embed", help="Embed knowledge chunks missing vectors").set_defaults(
        func=cmd_embed
    )
    sub.add_parser("purge-locations", help="Delete expired location data").set_defaults(
        func=cmd_purge_locations
    )
    sub.add_parser("status", help="Show provider/database status").set_defaults(func=cmd_status)

    p_demo = sub.add_parser("demo", help="Create the demo account and sample trip")
    p_demo.add_argument("--reset", action="store_true", help="recreate demo data from scratch")
    p_demo.set_defaults(func=cmd_demo_user)

    return parser


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    configure_logging(s.yatra_log_level, s.yatra_log_json)
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:
        log.exception("cli.failed", command=args.command, error=str(exc))
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
