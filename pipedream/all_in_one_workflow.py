# pipedream/all_in_one_workflow.py
#
# All-in-One Pipedream Python Step:
# Fetches "SW Leave & Events", formats summary, and sends to WhatsApp via Green API.
#
# Instructions:
# 1. In your Pipedream workflow, add a Python step.
# 2. In the step configuration under "Connected Accounts", select "Google Calendar".
# 3. Paste this complete code and click Test / Deploy!

import datetime as dt
import hashlib
import json
import re
from typing import Any
from urllib import request, error
from zoneinfo import ZoneInfo

# Target Calendar & Green API Configuration
CALENDAR_ID = "1416ccaf3075caf17169d81fa4f6e65a10634383b9301c50ee1ca4781659ccfb@group.calendar.google.com"
CALENDAR_DISPLAY_NAME = "SW Leave & Events"
TIMEZONE_NAME = "Asia/Singapore"

GREEN_API_ID_INSTANCE = "710522727682"
GREEN_API_TOKEN_INSTANCE = "1bbfcf04c5d542a2afcae69adaa47d7338282986e1b342c6a9"
GREEN_API_BASE_URL = "https://api.green-api.com"

# Target WhatsApp Group: "CFMS / SW Team" (or "120363427869267873@g.us" for testing)
TARGET_GROUP_JID = "120363023046007972@g.us"

LEAVE_PATTERN = re.compile(
    r"\b(leave|annual\s+leave|al|mc|off|ooo|out\s+of\s+office|vacation|holiday|wfh|wfo|half\s+day|absent|unwell|medical|childcare|hospital)\b",
    re.IGNORECASE,
)


def _parse_event_datetime(raw: dict[str, Any], tz: ZoneInfo) -> tuple[dt.datetime | dt.date, bool]:
    if "date" in raw:
        return dt.date.fromisoformat(raw["date"]), True
    if "dateTime" in raw:
        dt_val = dt.datetime.fromisoformat(raw["dateTime"])
        return dt_val.astimezone(tz), False
    raise ValueError(f"Unrecognized date format: {raw}")


def is_leave_or_ooo(summary: str) -> bool:
    return bool(LEAVE_PATTERN.search(summary))


def fetch_google_calendar_events(access_token: str, calendar_id: str, tz: ZoneInfo, today: dt.date) -> list[dict[str, Any]]:
    start_dt = dt.datetime.combine(today, dt.time.min, tzinfo=tz)
    end_dt = dt.datetime.combine(today + dt.timedelta(days=2), dt.time.min, tzinfo=tz)

    # Encode calendar ID for URL
    encoded_id = request.quote(calendar_id, safe="")
    time_min = request.quote(start_dt.isoformat())
    time_max = request.quote(end_dt.isoformat())

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events"
        f"?timeMin={time_min}&timeMax={time_max}&singleEvents=true&orderBy=startTime"
    )
    req = request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("items", [])
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Calendar API returned error {exc.code}: {body}") from exc


def format_calendar_summary(
    events: list[dict[str, Any]],
    target_date: dt.date,
    timezone_name: str = TIMEZONE_NAME,
    calendar_name: str = CALENDAR_DISPLAY_NAME,
) -> str:
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

        try:
            start_val, is_all_day = _parse_event_datetime(start_raw, tz)
        except Exception:
            continue

        if is_all_day:
            start_d = start_val if isinstance(start_val, dt.date) else start_val.date()
            end_d = dt.date.fromisoformat(end_raw["date"]) if "date" in end_raw else start_d + dt.timedelta(days=1)

            if start_d <= today < end_d:
                today_events.append({"event": event, "all_day": True, "time_str": "All day"})
            if start_d <= tomorrow < end_d:
                tomorrow_events.append({"event": event, "all_day": True, "time_str": "All day"})
        else:
            start_dt = start_val if isinstance(start_val, dt.datetime) else dt.datetime.combine(start_val, dt.time.min, tz)
            start_d = start_dt.date()
            time_str = start_dt.strftime("%I:%M %p")
            if "dateTime" in end_raw:
                try:
                    end_dt = dt.datetime.fromisoformat(end_raw["dateTime"]).astimezone(tz)
                    time_str += f" - {end_dt.strftime('%I:%M %p')}"
                except Exception:
                    pass

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


def send_to_green_api(chat_id: str, message: str) -> dict[str, Any]:
    url = f"{GREEN_API_BASE_URL.rstrip('/')}/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_TOKEN_INSTANCE}"
    payload = json.dumps({"chatId": chat_id, "message": message}).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def handler(pd: "pipedream") -> dict[str, Any]:
    tz = ZoneInfo(TIMEZONE_NAME)
    today = dt.datetime.now(tz).date()
    today_str = today.isoformat()

    # Extract OAuth token from connected Google Calendar account
    gcal_auth = pd.inputs.get("google_calendar", {}).get("$auth", {})
    access_token = gcal_auth.get("oauth_access_token")
    if not access_token:
        raise RuntimeError("Please connect your Google Calendar account in this step under 'Connected Accounts'.")

    # Fetch events directly from the shared calendar
    events = fetch_google_calendar_events(access_token, CALENDAR_ID, tz, today)
    print(f"Retrieved {len(events)} event(s) from '{CALENDAR_DISPLAY_NAME}'.")

    # Format the summary message
    summary_text = format_calendar_summary(events, today, TIMEZONE_NAME, CALENDAR_DISPLAY_NAME)
    print("--- Generated Summary ---")
    print(summary_text)

    # Deliver via Green API
    result = send_to_green_api(TARGET_GROUP_JID, summary_text)
    print(f"Delivery result: {result}")

    return {
        "status": "sent",
        "date": today_str,
        "recipient": TARGET_GROUP_JID,
        "events_count": len(events),
        "result": result,
    }
