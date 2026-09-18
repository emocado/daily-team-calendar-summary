# pipedream/format_and_send.py
#
# Pipedream Python Step: Daily Team Calendar Summary Formatter & Green API Sender
#
# Inputs in Pipedream:
# - Connect a Data Store (optional, for idempotency across runs)
# - Reference the Google Calendar step output (e.g. pd.inputs["events"])
#

import datetime as dt
import hashlib
import json
import os
import random
import re
import time
from typing import Any
from urllib import request, error
from zoneinfo import ZoneInfo

# Green API configuration (configurable via environment variables)
GREEN_API_ID_INSTANCE = os.environ.get("GREEN_API_ID_INSTANCE", "YOUR_GREEN_API_ID_INSTANCE")
GREEN_API_TOKEN_INSTANCE = os.environ.get("GREEN_API_TOKEN_INSTANCE", "YOUR_GREEN_API_TOKEN_INSTANCE")
GREEN_API_BASE_URL = os.environ.get("GREEN_API_BASE_URL", "https://api.green-api.com")

# Target WhatsApp Group JID
TARGET_GROUP_JID = os.environ.get("TARGET_GROUP_JID", "120363000000000000@g.us")
CALENDAR_DISPLAY_NAME = os.environ.get("CALENDAR_DISPLAY_NAME", "Team Leave & Events")
TIMEZONE_NAME = os.environ.get("TIMEZONE_NAME", "Asia/Singapore")

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
            if "date" in end_raw:
                end_d = dt.date.fromisoformat(end_raw["date"])
            else:
                end_d = start_d + dt.timedelta(days=1)

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


def send_to_green_api(chat_id: str, message: str, max_retries: int = 4, initial_delay: float = 2.0) -> dict[str, Any]:
    url = f"{GREEN_API_BASE_URL.rstrip('/')}/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_TOKEN_INSTANCE}"
    payload = json.dumps({"chatId": chat_id, "message": message}).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            with request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # Retry only on server errors (5xx) or rate limits (429)
            if attempt < max_retries and (exc.code >= 500 or exc.code == 429):
                wait_time = delay + random.uniform(0.1, 0.5)
                print(f"[Attempt {attempt}/{max_retries}] Green API HTTP {exc.code}: {body}. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)
                delay *= 2
                continue
            raise RuntimeError(f"Green API request failed with status {exc.code}: {body}") from exc
        except (error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            # Network timeouts or connection issues (such as Errno 110 Connection timed out)
            if attempt < max_retries:
                wait_time = delay + random.uniform(0.1, 0.5)
                print(f"[Attempt {attempt}/{max_retries}] Green API network error: {exc}. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)
                delay *= 2
                continue
            raise RuntimeError(f"Green API request error after {max_retries} attempts: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Green API request error: {exc}") from exc
    raise RuntimeError(f"Green API request failed after {max_retries} attempts")


def handler(pd: "pipedream") -> dict[str, Any]:
    """Pipedream step entrypoint."""
    tz = ZoneInfo(TIMEZONE_NAME)
    today = dt.datetime.now(tz).date()
    today_str = today.isoformat()

    # Retrieve events passed from previous Google Calendar step
    raw_events = pd.steps.get("get_events", {}).get("$return_value", [])
    if not isinstance(raw_events, list):
        if isinstance(raw_events, dict) and "items" in raw_events:
            raw_events = raw_events["items"]
        else:
            raw_events = []

    print(f"Retrieved {len(raw_events)} event(s) for formatting.")

    # Format the message
    summary_text = format_calendar_summary(
        events=raw_events,
        target_date=today,
        timezone_name=TIMEZONE_NAME,
        calendar_name=CALENDAR_DISPLAY_NAME,
    )
    print("--- Generated Summary ---")
    print(summary_text)

    # Calculate digest for idempotency
    digest = hashlib.sha256(summary_text.encode("utf-8")).hexdigest()

    # Check Pipedream Data Store if connected (keyed by date AND destination group)
    data_store = getattr(pd.inputs, "data_store", None) or pd.inputs.get("data_store")
    store_key = f"summary_{today_str}_{TARGET_GROUP_JID}"
    if data_store:
        prior_hash = data_store.get(store_key)
        if prior_hash == digest:
            print(f"Summary for {today_str} was already sent to {TARGET_GROUP_JID}. Skipping duplicate send.")
            return {"status": "already_sent", "date": today_str, "recipient": TARGET_GROUP_JID, "summary": summary_text}

    # Send to Green API
    result = send_to_green_api(chat_id=TARGET_GROUP_JID, message=summary_text)
    print(f"Sent successfully to {TARGET_GROUP_JID}: {result}")

    # Record in Data Store
    if data_store:
        data_store.set(store_key, digest)

    return {
        "status": "sent",
        "date": today_str,
        "recipient": TARGET_GROUP_JID,
        "green_api_result": result,
        "summary": summary_text,
    }
