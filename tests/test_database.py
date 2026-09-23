import sqlite3

import pytest

from src.database import get_connection, initialize_database

EXPECTED_TABLES = {
    "roles",
    "staff",
    "staff_weekday_availability",
    "staff_monthly_conditions",
    "staff_day_preferences",
    "daily_requirements",
    "daily_role_requirements",
    "schedule_months",
    "schedule_assignments",
}


@pytest.fixture()
def conn():
    c = get_connection(":memory:")
    initialize_database(c)
    yield c
    c.close()


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_all_tables_created(conn):
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert EXPECTED_TABLES <= tables


def test_staff_columns(conn):
    cols = _columns(conn, "staff")
    assert cols == [
        "staff_id",
        "staff_name",
        "role_id",
        "daily_work_minutes",
        "max_consecutive_days",
        "active",
    ]


def test_weekday_availability_columns(conn):
    assert _columns(conn, "staff_weekday_availability") == [
        "staff_id",
        "weekday",
        "is_available",
    ]


def test_monthly_conditions_columns(conn):
    assert _columns(conn, "staff_monthly_conditions") == [
        "staff_id",
        "year_month",
        "target_monthly_minutes",
        "min_monthly_minutes",
        "max_monthly_minutes",
        "carryover_consecutive_days",
    ]


def test_day_preferences_columns(conn):
    assert _columns(conn, "staff_day_preferences") == [
        "staff_id",
        "work_date",
        "preference_type",
    ]


def test_daily_requirements_columns(conn):
    assert _columns(conn, "daily_requirements") == [
        "work_date",
        "occupancy_rate",
        "required_total_staff",
        "max_total_staff",
        "note",
    ]


def test_daily_role_requirements_columns(conn):
    assert _columns(conn, "daily_role_requirements") == [
        "work_date",
        "role_id",
        "required_count",
    ]


def test_schedule_months_columns(conn):
    assert _columns(conn, "schedule_months") == [
        "year_month",
        "status",
        "solver_status",
        "objective_overstaff",
        "objective_target_deviation",
        "objective_prefer_off",
        "objective_prefer_work",
        "generated_at",
        "confirmed_at",
    ]


def test_schedule_assignments_columns(conn):
    assert _columns(conn, "schedule_assignments") == [
        "staff_id",
        "work_date",
        "is_working",
        "is_locked",
        "source",
    ]


def test_initialize_is_idempotent(conn):
    # 2回目の初期化でエラーなし、rolesは重複しない
    initialize_database(conn)
    rows = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    assert rows == 3


def test_roles_seeded(conn):
    rows = conn.execute(
        "SELECT role_id, role_code, role_name FROM roles ORDER BY role_id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (1, "LEADER", "リーダー"),
        (2, "CHECKER", "チェッカー"),
        (3, "CLEANER", "クリーナー"),
    ]


def test_foreign_key_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
                "max_consecutive_days) VALUES (?, ?, ?, ?)",
                ("test", 999, 480, 5),
            )


def test_check_weekday_range(conn):
    with conn:
        conn.execute(
            "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
            "max_consecutive_days) VALUES ('a', 1, 480, 5)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO staff_weekday_availability (staff_id, weekday, "
                "is_available) VALUES (1, 7, 1)"
            )


def test_check_boolean_columns(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
                "max_consecutive_days, active) VALUES ('a', 1, 480, 5, 2)"
            )


def test_check_preference_type(conn):
    with conn:
        conn.execute(
            "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
            "max_consecutive_days) VALUES ('a', 1, 480, 5)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO staff_day_preferences (staff_id, work_date, "
                "preference_type) VALUES (1, '2026-10-01', 'HOLIDAY')"
            )


def test_check_schedule_status(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO schedule_months (year_month, status) "
                "VALUES ('2026-10', 'PENDING')"
            )


def test_check_source_type(conn):
    with conn:
        conn.execute(
            "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
            "max_consecutive_days) VALUES ('a', 1, 480, 5)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO schedule_assignments (staff_id, work_date, "
                "is_working, source) VALUES (1, '2026-10-01', 1, 'AI')"
            )


def test_primary_key_uniqueness(conn):
    with conn:
        conn.execute(
            "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
            "max_consecutive_days) VALUES ('a', 1, 480, 5)"
        )
        conn.execute(
            "INSERT INTO staff_weekday_availability (staff_id, weekday, "
            "is_available) VALUES (1, 0, 1)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO staff_weekday_availability (staff_id, weekday, "
                "is_available) VALUES (1, 0, 0)"
            )


def test_nullable_columns_accept_null(conn):
    with conn:
        conn.execute(
            "INSERT INTO staff (staff_name, role_id, daily_work_minutes, "
            "max_consecutive_days) VALUES ('a', 1, 480, 5)"
        )
        conn.execute(
            "INSERT INTO staff_monthly_conditions (staff_id, year_month, "
            "target_monthly_minutes, min_monthly_minutes, max_monthly_minutes) "
            "VALUES (1, '2026-10', 9600, NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO daily_requirements (work_date, required_total_staff, "
            "max_total_staff, occupancy_rate, note) "
            "VALUES ('2026-10-01', 5, NULL, NULL, NULL)"
        )
    row = conn.execute(
        "SELECT min_monthly_minutes, max_monthly_minutes FROM "
        "staff_monthly_conditions WHERE staff_id=1"
    ).fetchone()
    assert row[0] is None and row[1] is None


def test_get_connection_memory_row_factory():
    conn = get_connection(":memory:")
    initialize_database(conn)
    row = conn.execute("SELECT role_id, role_code FROM roles WHERE role_id=1").fetchone()
    assert row["role_code"] == "LEADER"
    conn.close()


def test_get_connection_tmp_path(tmp_path):
    db_path = tmp_path / "sub" / "app.db"
    conn = get_connection(db_path)
    initialize_database(conn)
    assert db_path.exists()
    conn.close()
