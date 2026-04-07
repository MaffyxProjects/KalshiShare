from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flask import Flask, flash, redirect, render_template, request, send_file, url_for

from referral_assistant.logging_utils import tail_log_file
from referral_assistant.models import AlertEvent, AlertLevel, DraftStatus, VisibilityStatus
from referral_assistant.runtime import AppContext, create_app_context


_APP_CONTEXT: AppContext | None = None


def get_context() -> AppContext:
    global _APP_CONTEXT
    if _APP_CONTEXT is None:
        _APP_CONTEXT = create_app_context(root_dir=ROOT_DIR)
    return _APP_CONTEXT


def create_flask_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = "referral-assistant-local-only"

    @app.get("/")
    def overview():
        context = get_context()
        metrics = context.database.get_overview_metrics()
        persona_distribution = context.database.get_persona_distribution()
        max_count = max((item["count"] for item in persona_distribution), default=1)
        for item in persona_distribution:
            item["width_pct"] = max(8, int((item["count"] / max_count) * 100))
        events = [dict(row) for row in context.database.list_recent_events(limit=20)]
        return render_template(
            "overview.html",
            metrics=metrics,
            persona_distribution=persona_distribution,
            events=events,
        )

    @app.get("/inbox")
    def inbox():
        context = get_context()
        records = context.database.list_draft_records(
            statuses=[DraftStatus.QUEUED_FOR_MANUAL_REVIEW],
            limit=50,
        )
        packets = [
            {
                "record": record,
                "packet": context.review_helper.prepare(record),
            }
            for record in records
        ]
        return render_template("inbox.html", packets=packets)

    @app.post("/draft/<int:lead_id>/dismiss")
    def dismiss_draft(lead_id: int):
        context = get_context()
        notes = request.form.get("operator_notes", "").strip()
        context.database.dismiss_record(lead_id, operator_notes=notes)
        context.database.log_event(
            AlertEvent(
                event_type="draft_dismissed",
                level=AlertLevel.INFO,
                message=f"Lead {lead_id} was dismissed from the manual review queue.",
                metadata={"lead_id": lead_id},
            )
        )
        flash(f"Draft {lead_id} dismissed.", "info")
        return redirect(url_for("inbox"))

    @app.get("/review")
    def review():
        context = get_context()
        records = context.database.list_draft_records(
            statuses=[
                DraftStatus.QUEUED_FOR_MANUAL_REVIEW,
                DraftStatus.MANUALLY_POSTED,
                DraftStatus.VISIBILITY_VERIFIED,
            ],
            limit=100,
        )
        selected_id = request.args.get("lead_id", type=int)
        selected_record = None
        if records:
            selected_record = next((record for record in records if record.id == selected_id), None)
            if selected_record is None:
                selected_record = records[0]
        packet = context.review_helper.prepare(selected_record) if selected_record else None
        return render_template(
            "review.html",
            records=records,
            selected_record=selected_record,
            packet=packet,
        )

    @app.post("/draft/<int:lead_id>/mark-posted")
    def mark_posted(lead_id: int):
        context = get_context()
        public_post_url = request.form.get("public_post_url", "").strip()
        operator_notes = request.form.get("operator_notes", "").strip()
        context.database.mark_manual_posted(
            lead_id=lead_id,
            public_post_url=public_post_url,
            operator_notes=operator_notes,
        )
        event = AlertEvent(
            event_type="manual_post_recorded",
            level=AlertLevel.INFO,
            message=f"Lead {lead_id} was marked as manually posted.",
            metadata={"lead_id": lead_id, "public_post_url": public_post_url},
        )
        context.database.log_event(event)
        _send_alert_best_effort(context, event)
        flash(f"Lead {lead_id} marked as manually posted.", "success")
        return redirect(url_for("review", lead_id=lead_id))

    @app.post("/draft/<int:lead_id>/verify")
    def verify_visibility(lead_id: int):
        context = get_context()
        record = context.database.get_draft_record(lead_id)
        if record is None:
            flash(f"Lead {lead_id} was not found.", "error")
            return redirect(url_for("review"))

        public_post_url = request.form.get("public_post_url", "").strip() or record.public_post_url
        operator_notes = request.form.get("operator_notes", "").strip()
        if operator_notes != record.operator_notes or public_post_url != record.public_post_url:
            context.database.mark_manual_posted(
                lead_id=lead_id,
                public_post_url=public_post_url,
                operator_notes=operator_notes,
            )

        if not public_post_url:
            flash("Enter a public post URL before running the visibility check.", "error")
            return redirect(url_for("review", lead_id=lead_id))

        packet = context.review_helper.prepare(record)
        result = context.visibility_verifier.verify_visibility(
            lead_id=lead_id,
            public_url=public_post_url,
            expected_snippet=packet.rendered_reply[:140],
        )
        context.database.update_visibility_status(result)
        event = AlertEvent(
            event_type="visibility_check_completed",
            level=AlertLevel.WARNING
            if result.status == VisibilityStatus.NOT_VISIBLE
            else AlertLevel.INFO,
            message=f"Visibility check finished with status {result.status.value}.",
            metadata={
                "lead_id": lead_id,
                "status": result.status.value,
                "checked_url": public_post_url,
            },
        )
        context.database.log_event(event)
        if result.status == VisibilityStatus.NOT_VISIBLE:
            _send_alert_best_effort(context, event)
        flash(result.details, "warning" if result.status == VisibilityStatus.NOT_VISIBLE else "info")
        return redirect(url_for("review", lead_id=lead_id))

    @app.get("/logs")
    def logs():
        context = get_context()
        log_lines = tail_log_file(context.settings.log_path, line_count=250)
        events = [dict(row) for row in context.database.list_recent_events(limit=50)]
        errors = [dict(row) for row in context.database.list_recent_errors(limit=50)]
        return render_template(
            "logs.html",
            log_lines=log_lines,
            events=events,
            errors=errors,
        )

    @app.get("/controls")
    def controls():
        context = get_context()
        kill_switch = context.database.get_kill_switch_state()
        deferred = context.database.list_draft_records(
            statuses=[
                DraftStatus.DEFERRED_BY_CAP,
                DraftStatus.BLOCKED_BY_COMPLIANCE,
                DraftStatus.BLOCKED_BY_MODEL,
            ],
            limit=50,
        )
        return render_template(
            "controls.html",
            kill_switch=kill_switch,
            deferred=deferred,
        )

    @app.post("/controls/run-scheduler")
    def run_scheduler():
        context = get_context()
        summary = context.scheduler.run_once()
        flash(
            (
                f"Scheduler run finished. Processed={summary.processed_candidates}, "
                f"queued={summary.queued_drafts}, blocked={summary.blocked_candidates}, "
                f"errors={summary.errors}."
            ),
            "info",
        )
        return redirect(url_for("controls"))

    @app.post("/controls/kill-switch")
    def toggle_kill_switch():
        context = get_context()
        enabled = request.form.get("enabled", "false").lower() == "true"
        context.database.set_kill_switch(enabled=enabled, changed_by="dashboard")
        event = AlertEvent(
            event_type="kill_switch_changed",
            level=AlertLevel.WARNING if enabled else AlertLevel.INFO,
            message=f"Kill switch {'enabled' if enabled else 'disabled'} from the dashboard.",
            metadata={"enabled": enabled},
        )
        context.database.log_event(event)
        _send_alert_best_effort(context, event)
        flash(f"Kill switch {'enabled' if enabled else 'disabled'}.", "warning" if enabled else "success")
        return redirect(url_for("controls"))

    @app.get("/export/leads.csv")
    def export_leads():
        context = get_context()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        export_path = context.settings.export_dir / f"lead_tracker_{timestamp}.csv"
        output_path = context.database.export_leads_to_csv(export_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_path.name,
            mimetype="text/csv",
        )

    return app


def run_server(host: str = "127.0.0.1", port: int = 8501) -> None:
    app = create_flask_app()
    app.run(host=host, port=port, debug=False)


def _send_alert_best_effort(context: AppContext, event: AlertEvent) -> None:
    try:
        context.notifier.send(event)
    except Exception as exc:
        context.logger.warning("Dashboard alert send failed: %s", exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Referral Draft Assistant dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args(argv)
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
