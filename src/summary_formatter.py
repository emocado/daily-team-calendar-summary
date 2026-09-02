from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

LEAVE_PATTERN = re.compile(
    r"\b(leave|annual\s+leave|al|mc|off|ooo|out\s+of\s+office|vacation|holiday|wfh|wfo|half\s+day|absent|unwell|medical|childcare|hospital)\b",
    re.IGNORECASE,
)


def _parse_event_datetime(raw: dict[str, Any], tz: ZoneInfo) -> tuple[dt.datetime | dt.date, bool]:
    """Parse start/end event dictionary. Returns (date_or_datetime, is_all_day)."""
    if "date" in raw:
        return dt.date.fromisoformat(raw["date"]), True
    if "dateTime" in raw:
        dt_val = dt.datetime.fromisoformat(raw["dateTime"])
        return dt_val.astimezone(tz), False
    raise ValueError(f"Unrecognized date format: {raw}")


def is_leave_or_ooo(summary: str) -> bool:
    """Detect if an event summary looks like a leave / out-of-office entry."""
    return bool(LEAVE_PATTERN.search(summary))


def format_calendar_summary(
    events: list[dict[str, Any]],
    target_date: dt.date,
    timezone_name: str = "Asia/Singapore",
    calendar_name: str = "Team Leave & Events",
) -> str:
    """Format events for target_date (today) and target_date + 1 day (tomorrow) into WhatsApp markdown."""
    tz = ZoneInfo(timezone_name)
    today = target_date
    tomorrow = target_date + dt.timedelta(days=1)

    today_events: list[dict[str, Any]] = []
    tomorrow_events: list[dict[str, Any]] = []

    for event in events:
        start_raw = event.get("start", {})
        end_raw = event.get("end", {})
        if not start_raw:
            continue

        start_val, is_all_day = _parse_event_datetime(start_raw, tz)

        # For all-day events, Google Calendar end date is exclusive
        if is_all_day:
            start_d = start_val if isinstance(start_val, dt.date) else start_val.date()
            if "date" in end_raw:
                end_d = dt.date.fromisoformat(end_raw["date"])
            else:
                end_d = start_d + dt.timedelta(days=1)

            # Check overlap with today
            if start_d <= today < end_d:
                today_events.append({"event": event, "all_day": True, "time_str": "All day"})
            # Check overlap with tomorrow
            if start_d <= tomorrow < end_d:
                tomorrow_events.append({"event": event, "all_day": True, "time_str": "All day"})
        else:
            start_dt = start_val if isinstance(start_val, dt.datetime) else dt.datetime.combine(start_val, dt.time.min, tz)
            start_d = start_dt.date()
            time_str = start_dt.strftime("%I:%M %p")
            if "dateTime" in end_raw:
                end_dt = dt.datetime.fromisoformat(end_raw["dateTime"]).astimezone(tz)
                time_str += f" - {end_dt.strftime('%I:%M %p')}"

            if start_d == today:
                today_events.append({"event": event, "all_day": False, "time_str": time_str, "dt": start_dt})
            elif start_d == tomorrow:
                tomorrow_events.append({"event": event, "all_day": False, "time_str": time_str, "dt": start_dt})

    def render_day_section(day_label: str, day_date: dt.date, day_items: list[dict[str, Any]]) -> list[str]:
        date_header = day_date.strftime("%a, %d %b %Y")
        lines = [f"📌 *{day_label} ({date_header})*"]

        if not day_items:
            lines.append("  • _No events scheduled_")
            return lines

        leaves: list[str] = []
        timed: list[str] = []

        # Sort timed events by start datetime
        sorted_items = sorted(day_items, key=lambda x: (not x["all_day"], x.get("dt", dt.datetime.min)))

        for item in sorted_items:
            ev = item["event"]
            title = ev.get("summary", "Untitled Event").strip()
            if item["all_day"] or is_leave_or_ooo(title):
                leaves.append(f"  • {title}")
            else:
                lines_time = item["time_str"]
                timed.append(f"  • *{lines_time}*: {title}")

        if leaves:
            lines.append("🏖️ *Leave / All-Day:*")
            lines.extend(leaves)
        if timed:
            lines.append("⏰ *Schedule / Meetings:*")
            lines.extend(timed)

        if not leaves and not timed:
            lines.append("  • _No events scheduled_")

        return lines

    date_range_str = f"{today.strftime('%d %b %Y')} – {tomorrow.strftime('%d %b %Y')}"
    header = [
        f"📅 *Team Calendar Summary: {calendar_name}*",
        f"🗓️ *{date_range_str}*",
        "",
    ]

    today_lines = render_day_section("Today", today, today_events)
    tomorrow_lines = render_day_section("Tomorrow", tomorrow, tomorrow_events)

    now_str = dt.datetime.now(tz).strftime("%d %b %Y, %I:%M %p")
    footer = ["", f"_Summary generated on {now_str} (SGT)_"]

    return "\n".join(header + today_lines + [""] + tomorrow_lines + footer)
