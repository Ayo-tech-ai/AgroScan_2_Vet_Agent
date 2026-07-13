"""
Farm records tools -- SQLite-backed daily production record book.

Requires data/agroscan.db to already exist (built from your farm records
Excel file via the same import process you used in Colab). This module does
NOT create or seed the table -- it assumes the database already has the
farm_records table populated.
"""

import sqlite3
from datetime import date
from typing import Optional

from google.adk.tools import FunctionTool

DATABASE_NAME = "data/agroscan.db"


class FarmRecordService:

    CRATE_PRICE = 3500

    def __init__(self, database_name):
        self.database_name = database_name

    def get_connection(self):
        return sqlite3.connect(self.database_name)

    def get_total_records(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM farm_records")
        total = cursor.fetchone()[0]
        connection.close()
        return total

    def record_exists(self, record_date):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM farm_records WHERE record_date=?",
            (record_date,)
        )
        exists = cursor.fetchone()[0] > 0
        connection.close()
        return exists

    def get_record_by_date(self, record_date):
        connection = self.get_connection()
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM farm_records WHERE record_date=?",
            (record_date,)
        )
        row = cursor.fetchone()
        connection.close()
        return dict(row) if row else None

    def get_previous_record(self, record_date):
        connection = self.get_connection()
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT * FROM farm_records
            WHERE record_date < ?
            ORDER BY record_date DESC
            LIMIT 1
            """,
            (record_date,)
        )
        row = cursor.fetchone()
        connection.close()
        return dict(row) if row else None

    def get_most_recent_record(self):
        connection = self.get_connection()
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT * FROM farm_records
            ORDER BY record_date DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        connection.close()
        return dict(row) if row else None

    def get_summary(self, start_date, end_date):
        connection = self.get_connection()
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(*) AS days_recorded,
                COALESCE(SUM(crates_collected), 0) AS total_crates,
                COALESCE(SUM(feed_consumed_kg), 0) AS total_feed_kg,
                COALESCE(SUM(revenue), 0) AS total_revenue,
                COALESCE(SUM(expenses), 0) AS total_expenses
            FROM farm_records
            WHERE record_date BETWEEN ? AND ?
            """,
            (start_date, end_date)
        )

        row = cursor.fetchone()
        connection.close()

        result = dict(row)
        result["net_profit"] = result["total_revenue"] - result["total_expenses"]
        result["start_date"] = start_date
        result["end_date"] = end_date

        return result

    def get_all_records(self):
        connection = self.get_connection()
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM farm_records ORDER BY record_date")
        rows = cursor.fetchall()
        connection.close()
        return [dict(row) for row in rows]

    def validate_daily_record(self, bird_count, crates_collected):
        eggs = crates_collected * 30
        maximum_eggs = bird_count * 0.95
        if eggs > maximum_eggs:
            return (
                False,
                f"{crates_collected} crates ({eggs} eggs) appears "
                f"unrealistic for {bird_count} birds."
            )
        return True, "Validation passed."

    def record_daily_farm_data(
        self, crates_collected=None, bird_count=None,
        feed_consumed_kg=None, expenses=None,
        notes=None, record_date=None
    ):
        if record_date is None:
            record_date = date.today().isoformat()

        existing_record = self.get_record_by_date(record_date)
        previous_day_record = self.get_previous_record(record_date)

        reference_record = existing_record or previous_day_record

        if reference_record:
            if crates_collected is None:
                crates_collected = reference_record["crates_collected"]
            if bird_count is None:
                bird_count = reference_record["bird_count"]
            if feed_consumed_kg is None:
                feed_consumed_kg = reference_record["feed_consumed_kg"]
            if expenses is None:
                expenses = reference_record["expenses"]
            if notes is None:
                notes = reference_record["notes"]
        else:
            if crates_collected is None:
                raise ValueError("crates_collected is required for the first record.")
            if bird_count is None:
                raise ValueError("bird_count is required for the first record.")
            if feed_consumed_kg is None:
                raise ValueError("feed_consumed_kg is required for the first record.")
            if expenses is None:
                raise ValueError("expenses is required for the first record.")

        revenue = crates_collected * self.CRATE_PRICE

        valid, message = self.validate_daily_record(bird_count, crates_collected)
        if not valid:
            return {"success": False, "message": message}

        connection = self.get_connection()
        cursor = connection.cursor()

        if existing_record:
            cursor.execute(
                """
                UPDATE farm_records
                SET bird_count=?, crates_collected=?, feed_consumed_kg=?,
                    revenue=?, expenses=?, notes=?
                WHERE record_date=?
                """,
                (bird_count, crates_collected, feed_consumed_kg,
                 revenue, expenses, notes, record_date)
            )
            action = "updated"
        else:
            cursor.execute(
                """
                INSERT INTO farm_records(
                    record_date, bird_count, crates_collected,
                    feed_consumed_kg, revenue, expenses, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (record_date, bird_count, crates_collected,
                 feed_consumed_kg, revenue, expenses, notes)
            )
            action = "recorded"

        connection.commit()
        connection.close()

        return {
            "success": True,
            "action": action,
            "record_date": record_date,
            "previous_values": existing_record,
            "bird_count": bird_count,
            "crates_collected": crates_collected,
            "feed_consumed_kg": feed_consumed_kg,
            "revenue": revenue,
            "expenses": expenses,
            "notes": notes,
            "message": f"Farm record successfully {action}.",
        }


farm_service = FarmRecordService(DATABASE_NAME)


def _to_int(value, field_name):
    """Safely converts a value to int, tolerating string input from
    models that stringify arguments (e.g. some Groq models)."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("", "null", "none"):
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            raise ValueError(f"Could not interpret '{value}' as a whole number for {field_name}.")
    return int(value)


def _to_float(value, field_name):
    """Safely converts a value to float, same tolerance as _to_int."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("", "null", "none"):
            return None
        try:
            return float(cleaned)
        except ValueError:
            raise ValueError(f"Could not interpret '{value}' as a number for {field_name}.")
    return float(value)


def record_daily_farm_data(
    crates_collected: Optional[str] = None,
    bird_count: Optional[str] = None,
    feed_consumed_kg: Optional[str] = None,
    expenses: Optional[str] = None,
    notes: Optional[str] = None,
    record_date: Optional[str] = None,
):
    """
    Record or update daily poultry farm production.

    Use this action whenever the farmer provides
    daily production information.

    NOTE: All numeric fields are accepted as text and converted
    internally to numbers, to tolerate models that pass numeric
    values as strings.

    If record_date is not provided, it defaults to today's date
    automatically — do not ask the farmer for the date unless
    they are referring to a specific past day.

    Business Rules

    - If a record already exists for the date, it is updated —
      only the fields provided are changed; all other fields,
      including crates_collected, keep their current values.
    - If no record exists yet for the date, missing fields are
      inherited from the most recent prior record. The very
      first record ever created requires all fields.
    - Revenue is calculated automatically.
    - The result includes 'previous_values' (the record's state
      before this call, or None if this created a new record).
    """
    parsed_crates = _to_int(crates_collected, "crates_collected")
    parsed_bird_count = _to_int(bird_count, "bird_count")
    parsed_feed = _to_float(feed_consumed_kg, "feed_consumed_kg")
    parsed_expenses = _to_float(expenses, "expenses")

    return farm_service.record_daily_farm_data(
        crates_collected=parsed_crates,
        bird_count=parsed_bird_count,
        feed_consumed_kg=parsed_feed,
        expenses=parsed_expenses,
        notes=notes,
        record_date=record_date,
    )


def get_farm_record(record_date: str):
    """
    Retrieve the farm record for one exact calendar date.

    Use this when the farmer asks about a SPECIFIC date — including
    relative terms like "yesterday" or "last Tuesday" that you have
    already converted into an exact date (YYYY-MM-DD) before calling
    this tool.

    This performs an EXACT match only. If no record exists for that
    exact date, it returns a clear "no record found" result — it does
    NOT fall back to the nearest available date. Do not guess or
    substitute a different date's data if this returns no record.

    Args:
        record_date: The exact date to look up, in YYYY-MM-DD format.
    """
    record = farm_service.get_record_by_date(record_date)

    if record is None:
        return {
            "found": False,
            "record_date": record_date,
            "message": f"No farm record was found for {record_date}.",
        }

    return {
        "found": True,
        "record_date": record_date,
        "record": record,
    }


def get_most_recent_farm_record():
    """
    Retrieve the single most recent farm record in the entire record
    book, regardless of how many days ago it was.

    Use this when the farmer asks something like "what's my last
    record?", "when did I last record data?", or "show me my most
    recent entry" — situations where they want the latest available
    data, not a specific date.

    This is DIFFERENT from get_farm_record: that tool looks up one
    exact date and reports "no record" if nothing exists for it. This
    tool always returns the latest entry that exists, whatever date
    that happens to be.
    """
    record = farm_service.get_most_recent_record()

    if record is None:
        return {
            "found": False,
            "message": "No farm records exist yet.",
        }

    return {
        "found": True,
        "record": record,
    }


def get_farm_summary(start_date: str, end_date: str):
    """
    Get a summary of farm performance over a date range (inclusive
    of both start_date and end_date).

    Use this when the farmer asks about totals or profit/loss over
    a period — e.g. "how did I do this month?", "what was my profit
    last week?", "total crates sold in June". Convert relative period
    references into exact YYYY-MM-DD start and end dates BEFORE
    calling this tool.

    Returns total crates collected, total feed consumed, total
    revenue, total expenses, net profit (revenue minus expenses),
    and how many days in that range actually have a record
    ("days_recorded"). If days_recorded is 0, no data exists for
    that range at all — report that honestly rather than implying
    a loss or zero performance.

    Args:
        start_date: Start of the range, in YYYY-MM-DD format.
        end_date: End of the range, in YYYY-MM-DD format.
    """
    return farm_service.get_summary(start_date, end_date)


farm_record_tool = FunctionTool(record_daily_farm_data)
farm_record_lookup_tool = FunctionTool(get_farm_record)
most_recent_record_tool = FunctionTool(get_most_recent_farm_record)
farm_summary_tool = FunctionTool(get_farm_summary)
