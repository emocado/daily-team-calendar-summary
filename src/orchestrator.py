from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

# Ensure repository root is on sys.path for direct script invocations
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.calendar_service import GoogleCalendarService, CalendarServiceError
from src.safe_whatsapp_mcp import SafeWhatsappService, WorkflowError
from src.summary_formatter import format_calendar_summary


class Orchestrator:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.root = self.config_path.parent.parent
        self.cal_service = GoogleCalendarService(self.config_path)
        self.wa_service = SafeWhatsappService(self.config_path)
        self.timezone_name = self.cal_service.timezone_name
        self.timezone = ZoneInfo(self.timezone_name)

    def run_daily_workflow(self, dry_run: bool = False, force_date: str | None = None) -> dict[str, Any]:
        """Fetch today + tomorrow calendar events, format summary, and send to WhatsApp."""
        if force_date:
            target_date = dt.date.fromisoformat(force_date)
        else:
            target_date = dt.datetime.now(self.timezone).date()

        date_str = target_date.isoformat()
        print(f"[*] Running daily summary workflow for {date_str} (Timezone: {self.timezone_name})")

        cal_name = self.cal_service.cal_config.get("display_name", "Team Leave & Events")

        try:
            events = self.cal_service.get_events_for_range(start_date=target_date, days=2)
            print(f"[+] Retrieved {len(events)} event(s) from calendar '{cal_name}'.")
        except Exception as exc:
            print(f"[-] Failed to fetch calendar events: {exc}")
            raise

        summary_text = format_calendar_summary(
            events=events,
            target_date=target_date,
            timezone_name=self.timezone_name,
            calendar_name=cal_name,
        )

        print("\n--- GENERATED SUMMARY ---")
        print(summary_text)
        print("-------------------------\n")

        if dry_run:
            print("[*] Dry run enabled; skipping WhatsApp send.")
            return {"status": "dry_run", "summary": summary_text}

        print(f"[*] Sending daily summary to pinned WhatsApp group '{self.wa_service.wa.get('group_name')}'...")
        result = self.wa_service.send_daily_summary(run_date=date_str, message=summary_text)
        print(f"[+] WhatsApp result: {result}")
        return {"status": "sent", "result": result, "summary": summary_text}

    def test_send(self, custom_message: str | None = None) -> dict[str, Any]:
        """Send a test message immediately to verify WhatsApp connectivity."""
        target_date = dt.datetime.now(self.timezone).date()
        date_str = target_date.isoformat()

        if custom_message:
            message = custom_message
        else:
            message = (
                f"🧪 *Test Automation Summary*\n"
                f"📅 Target Calendar: {self.cal_service.cal_config.get('display_name', 'Team Leave & Events')}\n"
                f"⏰ Sent at: {dt.datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S')} SGT\n"
                f"✅ WhatsApp destination locking and bridge connection active."
            )

        print(f"[*] Sending test message to WhatsApp group '{self.wa_service.wa.get('group_name')}'...")
        result = self.wa_service.send_daily_summary(run_date=date_str, message=message)
        print(f"[+] Send result: {result}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Team Calendar Summary Orchestrator")
    parser.add_argument("--config", type=Path, default=Path("runtime/workflow.json"), help="Path to workflow.json")
    parser.add_argument("--auth-google", action="store_true", help="Authenticate Google Calendar OAuth")
    parser.add_argument("--pin-calendar", action="store_true", help="Resolve and pin Google Calendar ID")
    parser.add_argument("--resolve-group", action="store_true", help="Resolve WhatsApp group JID")
    parser.add_argument("--pin-whatsapp", action="store_true", help="Pin WhatsApp group JID")
    parser.add_argument("--status", action="store_true", help="Check status of Google and WhatsApp connections")
    parser.add_argument("--dry-run", action="store_true", help="Generate summary preview without sending")
    parser.add_argument("--test-send", action="store_true", help="Send a test message to the pinned WhatsApp group")
    parser.add_argument("--run", action="store_true", help="Execute the complete daily summary send")

    args = parser.parse_args()
    config_path = args.config.resolve()
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        return 1

    orchestrator = Orchestrator(config_path)

    if args.status:
        wa_status = orchestrator.wa_service.status()
        print("=== WhatsApp Status ===")
        print(json.dumps(wa_status, indent=2))

        print("\n=== Google Calendar Status ===")
        print(f"Configured Calendar Name: {orchestrator.cal_service.cal_config.get('display_name')}")
        print(f"Pinned Calendar ID: {orchestrator.cal_service.cal_config.get('calendar_id')}")
        print(f"Credentials JSON present: {orchestrator.cal_service.credentials_path.exists()}")
        print(f"Token JSON present: {orchestrator.cal_service.token_path.exists()}")
        return 0

    if args.auth_google:
        print("[*] Starting Google OAuth flow...")
        orchestrator.cal_service.get_credentials(interactive=True)
        cal_id = orchestrator.cal_service.pin_calendar()
        print(f"[+] Google Calendar authenticated! Pinned Calendar ID: {cal_id}")
        return 0

    if args.pin_calendar:
        cal_id = orchestrator.cal_service.pin_calendar()
        print(f"[+] Pinned Calendar ID: {cal_id}")
        return 0

    if args.resolve_group:
        jid = orchestrator.wa_service.resolve_group()
        print(f"[+] Resolved Group JID: {jid}")
        return 0

    if args.pin_whatsapp:
        jid = orchestrator.wa_service.pin_group()
        print(f"[+] Pinned Group JID: {jid}")
        return 0

    if args.dry_run:
        orchestrator.run_daily_workflow(dry_run=True)
        return 0

    if args.test_send:
        orchestrator.test_send()
        return 0

    if args.run:
        orchestrator.run_daily_workflow(dry_run=False)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
