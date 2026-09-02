import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from src.summary_formatter import format_calendar_summary, is_leave_or_ooo


class SummaryFormatterTests(unittest.TestCase):
    def setUp(self):
        self.target_date = dt.date(2026, 9, 2)

    def test_leave_keyword_detection(self):
        self.assertTrue(is_leave_or_ooo("John Doe - Annual Leave"))
        self.assertTrue(is_leave_or_ooo("Alice (MC)"))
        self.assertTrue(is_leave_or_ooo("Bob OOO"))
        self.assertTrue(is_leave_or_ooo("Charlie WFH"))
        self.assertFalse(is_leave_or_ooo("Project Kickoff Meeting"))
        self.assertFalse(is_leave_or_ooo("Team Standup"))

    def test_format_calendar_summary_with_events(self):
        events = [
            # Today all day leave
            {
                "summary": "Alice - Annual Leave",
                "start": {"date": "2026-09-02"},
                "end": {"date": "2026-09-03"},
            },
            # Today timed meeting
            {
                "summary": "Engineering Sync",
                "start": {"dateTime": "2026-09-02T10:00:00+08:00"},
                "end": {"dateTime": "2026-09-02T11:00:00+08:00"},
            },
            # Tomorrow timed meeting
            {
                "summary": "Product Review",
                "start": {"dateTime": "2026-09-03T14:30:00+08:00"},
                "end": {"dateTime": "2026-09-03T15:30:00+08:00"},
            },
            # Multi-day event spanning today and tomorrow
            {
                "summary": "Company Offsite",
                "start": {"date": "2026-09-02"},
                "end": {"date": "2026-09-04"},
            },
            # Outside range event (day after tomorrow)
            {
                "summary": "Future Planning",
                "start": {"dateTime": "2026-09-04T10:00:00+08:00"},
                "end": {"dateTime": "2026-09-04T11:00:00+08:00"},
            },
        ]

        text = format_calendar_summary(events, self.target_date, calendar_name="SW Leave & Events")

        self.assertIn("Team Calendar Summary: SW Leave & Events", text)
        self.assertIn("Today (Wed, 02 Sep 2026)", text)
        self.assertIn("Alice - Annual Leave", text)
        self.assertIn("Company Offsite", text)
        self.assertIn("10:00 AM - 11:00 AM*: Engineering Sync", text)
        self.assertIn("Tomorrow (Thu, 03 Sep 2026)", text)
        self.assertIn("02:30 PM - 03:30 PM*: Product Review", text)
        self.assertNotIn("Future Planning", text)

    def test_format_empty_days(self):
        text = format_calendar_summary([], self.target_date, calendar_name="SW Leave & Events")
        self.assertIn("No events scheduled", text)


if __name__ == "__main__":
    unittest.main()
