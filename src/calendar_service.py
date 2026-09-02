from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]


class CalendarServiceError(RuntimeError):
    pass


class GoogleCalendarService:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.root = self.config_path.parent.parent
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.timezone_name = self.config.get("timezone", "Asia/Singapore")
        self.timezone = ZoneInfo(self.timezone_name)
        self.cal_config = self.config.get("calendar", {})

        self.credentials_path = self.root / "runtime" / "credentials.json"
        self.token_path = self.root / "runtime" / "google-token.json"

    def get_credentials(self, interactive: bool = False) -> Credentials:
        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as exc:
                creds = None

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self.token_path.write_text(creds.to_json(), encoding="utf-8")
                return creds
            except Exception as exc:
                if not interactive:
                    raise CalendarServiceError(f"Failed to refresh Google credentials: {exc}") from exc

        if not interactive:
            raise CalendarServiceError(
                f"Google Calendar credentials not found or expired at {self.token_path}. Run authentication first."
            )

        if not self.credentials_path.exists():
            raise CalendarServiceError(
                f"Google OAuth client credentials file not found at {self.credentials_path}. "
                "Please download OAuth Client ID credentials (credentials.json) from Google Cloud Console."
            )

        flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def get_client(self, interactive: bool = False) -> Any:
        creds = self.get_credentials(interactive=interactive)
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_calendars(self, client: Any | None = None) -> list[dict[str, Any]]:
        service = client or self.get_client()
        calendar_list = service.calendarList().list().execute()
        return calendar_list.get("items", [])

    def resolve_calendar_id(self, client: Any | None = None) -> str:
        target_name = self.cal_config.get("display_name", "SW Leave & Events")
        calendars = self.list_calendars(client=client)
        matched = [c for c in calendars if c.get("summary", "").strip() == target_name.strip()]
        if not matched:
            # Check case-insensitive match
            matched = [c for c in calendars if c.get("summary", "").strip().lower() == target_name.strip().lower()]

        if not matched:
            available = [c.get("summary", "<unnamed>") for c in calendars]
            raise CalendarServiceError(
                f"Could not find Google Calendar named '{target_name}'. Available calendars: {available}"
            )
        if len(matched) > 1:
            raise CalendarServiceError(
                f"Found multiple Google Calendars matching '{target_name}'. IDs: {[c['id'] for c in matched]}"
            )
        return matched[0]["id"]

    def pin_calendar(self, client: Any | None = None) -> str:
        cal_id = self.resolve_calendar_id(client=client)
        self.config["calendar"]["calendar_id"] = cal_id
        self.config_path.write_text(json.dumps(self.config, indent=2) + "\n", encoding="utf-8")
        self.cal_config["calendar_id"] = cal_id
        return cal_id

    def get_events_for_range(
        self,
        start_date: dt.date,
        days: int = 2,
        client: Any | None = None,
    ) -> list[dict[str, Any]]:
        service = client or self.get_client()
        cal_id = self.cal_config.get("calendar_id")
        if not cal_id or cal_id == "PIN_AFTER_GOOGLE_OAUTH":
            cal_id = self.resolve_calendar_id(client=service)

        # Time min: start_date 00:00:00 SGT
        start_dt = dt.datetime.combine(start_date, dt.time.min, tzinfo=self.timezone)
        # Time max: start_date + days at 00:00:00 SGT (i.e. covers start_date and start_date + days - 1)
        end_dt = dt.datetime.combine(start_date + dt.timedelta(days=days), dt.time.min, tzinfo=self.timezone)

        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])
