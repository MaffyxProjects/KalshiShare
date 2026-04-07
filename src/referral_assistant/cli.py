from __future__ import annotations

import argparse
import json

from referral_assistant.runtime import create_app_context


def init_db_command() -> None:
    context = create_app_context()
    context.database.initialize()
    context.logger.info("Initialized database at %s", context.settings.database_path)
    print(json.dumps({"database_path": str(context.settings.database_path)}))


def run_once_command() -> None:
    context = create_app_context()
    summary = context.scheduler.run_once()
    print(
        json.dumps(
            {
                "processed_candidates": summary.processed_candidates,
                "skipped_duplicates": summary.skipped_duplicates,
                "queued_drafts": summary.queued_drafts,
                "blocked_candidates": summary.blocked_candidates,
                "errors": summary.errors,
            }
        )
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Referral Draft Assistant CLI")
    parser.add_argument(
        "command",
        choices=["init-db", "run-once"],
        help="Command to execute.",
    )
    args = parser.parse_args(argv)

    if args.command == "init-db":
        init_db_command()
        return
    run_once_command()


if __name__ == "__main__":
    main()
