import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src.calendar_service import GoogleCalendarService, CalendarServiceError


class CalendarServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "runtime").mkdir()

        self.config_data = {
            "timezone": "Asia/Singapore",
            "calendar": {
                "display_name": "Team Leave & Events",
                "calendar_id": "PIN_AFTER_GOOGLE_OAUTH",
            },
        }
        self.config_path = self.root / "config" / "workflow.json"
        self.config_path.write_text(json.dumps(self.config_data), encoding="utf-8")
        self.service = GoogleCalendarService(self.config_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_resolve_calendar_id_finds_exact_name(self):
        mock_client = mock.MagicMock()
        mock_client.calendarList().list().execute.return_value = {
            "items": [
                {"id": "primary", "summary": "Personal"},
                {"id": "team_cal_id_123", "summary": "Team Leave & Events"},
            ]
        }
        resolved = self.service.resolve_calendar_id(client=mock_client)
        self.assertEqual("team_cal_id_123", resolved)

    def test_resolve_calendar_id_not_found(self):
        mock_client = mock.MagicMock()
        mock_client.calendarList().list().execute.return_value = {
            "items": [{"id": "primary", "summary": "Personal"}]
        }
        with self.assertRaisesRegex(CalendarServiceError, "Could not find Google Calendar"):
            self.service.resolve_calendar_id(client=mock_client)

    def test_pin_calendar(self):
        mock_client = mock.MagicMock()
        mock_client.calendarList().list().execute.return_value = {
            "items": [{"id": "team_cal_id_123", "summary": "Team Leave & Events"}]
        }
        pinned = self.service.pin_calendar(client=mock_client)
        self.assertEqual("team_cal_id_123", pinned)

        # Check file was updated
        updated_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual("team_cal_id_123", updated_config["calendar"]["calendar_id"])

    def test_get_events_for_range(self):
        mock_client = mock.MagicMock()
        self.service.cal_config["calendar_id"] = "team_cal_id_123"
        mock_events = [{"id": "ev1", "summary": "Team Offsite"}]
        mock_client.events().list().execute.return_value = {"items": mock_events}

        events = self.service.get_events_for_range(
            start_date=dt.date(2026, 9, 2),
            days=2,
            client=mock_client,
        )
        self.assertEqual(mock_events, events)
        mock_client.events().list.assert_called_with(
            calendarId="team_cal_id_123",
            timeMin="2026-09-02T00:00:00+08:00",
            timeMax="2026-09-04T00:00:00+08:00",
            singleEvents=True,
            orderBy="startTime",
        )


if __name__ == "__main__":
    unittest.main()
