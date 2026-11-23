# tests/test_dates.py
import unittest

from expense_tracker_agent.dates import parse_csv_date


class TestParseCsvDate(unittest.TestCase):
    def test_iso_date_is_year_month_day(self):
        # pandas with dayfirst=True used to turn this into 2026-01-06
        self.assertEqual(parse_csv_date("2026-06-01"), "2026-06-01")

    def test_iso_date_with_ambiguous_month_and_day(self):
        self.assertEqual(parse_csv_date("2026-03-04"), "2026-03-04")

    def test_iso_date_with_unambiguous_day(self):
        self.assertEqual(parse_csv_date("2026-06-13"), "2026-06-13")

    def test_iso_datetime_drops_the_time(self):
        self.assertEqual(parse_csv_date("2026-06-01 10:30:00"), "2026-06-01")
        self.assertEqual(parse_csv_date("2026-06-01T10:30:00"), "2026-06-01")

    def test_year_first_with_slashes_or_dots(self):
        self.assertEqual(parse_csv_date("2026/06/01"), "2026-06-01")
        self.assertEqual(parse_csv_date("2026.06.01"), "2026-06-01")

    def test_compact_year_first(self):
        self.assertEqual(parse_csv_date("20260601"), "2026-06-01")
        self.assertEqual(parse_csv_date("20260102"), "2026-01-02")

    def test_day_first_slashes(self):
        self.assertEqual(parse_csv_date("03/04/2026"), "2026-04-03")  # 3 April
        self.assertEqual(parse_csv_date("13/06/2026"), "2026-06-13")

    def test_day_first_dots_and_single_digits(self):
        self.assertEqual(parse_csv_date("1.6.2026"), "2026-06-01")
        self.assertEqual(parse_csv_date("3-4-2026"), "2026-04-03")

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(parse_csv_date("  2026-06-01  "), "2026-06-01")
        self.assertEqual(parse_csv_date(" 03/04/2026 "), "2026-04-03")

    def test_textual_month(self):
        self.assertEqual(parse_csv_date("June 3, 2026"), "2026-06-03")

    def test_invalid_input_raises(self):
        for bad in ("not-a-date", "", "32/13/2026"):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    parse_csv_date(bad)

    def test_non_string_input_is_converted(self):
        # CSV cells read by pandas may not be str
        self.assertEqual(parse_csv_date(20260601), "2026-06-01")


if __name__ == "__main__":
    unittest.main()
