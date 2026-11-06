"""Database models and operations using SQLite."""
import sqlite3
import os
from datetime import date, datetime
from typing import List, Dict, Optional, Any


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_tables()

    def init_tables(self):
        """Create all tables if they don't exist."""
        cursor = self.conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Workers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                shift_preference TEXT,
                work_days_per_month INTEGER DEFAULT 20,
                category_id INTEGER,
                on_vacation INTEGER DEFAULT 0,
                vacation_start DATE,
                vacation_end DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')

        # Categories table (hours-per-week groups)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hours_per_week REAL DEFAULT 40,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Shifts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Schedule table (worker-day-shift assignments)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                date DATE NOT NULL,
                shift_id INTEGER,
                status TEXT DEFAULT 'working',
                user_override INTEGER DEFAULT 0,
                UNIQUE(worker_id, date),
                FOREIGN KEY (worker_id) REFERENCES workers(id),
                FOREIGN KEY (shift_id) REFERENCES shifts(id)
            )
        ''')

        # Staffing requirements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS staffing_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_type TEXT NOT NULL,
                hour INTEGER NOT NULL,
                workers_needed INTEGER NOT NULL,
                UNIQUE(day_type, hour)
            )
        ''')

        # Working hours configuration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS working_hours (
                day_type TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            )
        ''')

        self.conn.commit()

    # User operations
    def create_user(self, username: str, password_hash: str, is_admin: bool = False) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, 1 if is_admin else 0)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_user(self, username: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # Worker operations
    def get_workers(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT w.*, c.name as category_name, c.hours_per_week
            FROM workers w
            LEFT JOIN categories c ON w.category_id = c.id
            ORDER BY w.name
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def get_worker(self, worker_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_worker(self, name: str, shift_preference: str = None,
                      work_days_per_month: int = 20, category_id: int = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO workers (name, shift_preference, work_days_per_month, category_id)
            VALUES (?, ?, ?, ?)
        ''', (name, shift_preference, work_days_per_month, category_id))
        self.conn.commit()
        return cursor.lastrowid

    def update_worker(self, worker_id: int, **kwargs):
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ('name', 'shift_preference', 'work_days_per_month', 'category_id',
                       'on_vacation', 'vacation_start', 'vacation_end'):
                fields.append(f"{key} = ?")
                values.append(value)
        if not fields:
            return
        values.append(worker_id)
        cursor = self.conn.cursor()
        cursor.execute(f"UPDATE workers SET {', '.join(fields)} WHERE id = ?", values)
        self.conn.commit()

    # Category operations
    def get_categories(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def create_category(self, name: str, hours_per_week: float = 40.0) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO categories (name, hours_per_week) VALUES (?, ?)",
            (name, hours_per_week)
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_category(self, category_id: int, name: str, hours_per_week: float):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE categories SET name = ?, hours_per_week = ? WHERE id = ?",
            (name, hours_per_week, category_id)
        )
        self.conn.commit()

    # Shift operations
    def get_shifts(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM shifts WHERE is_active = 1 ORDER BY start_time")
        return [dict(row) for row in cursor.fetchall()]

    def create_shift(self, name: str, start_time: str, end_time: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO shifts (name, start_time, end_time) VALUES (?, ?, ?)",
            (name, start_time, end_time)
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_shift(self, shift_id: int, name: str, start_time: str, end_time: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE shifts SET name = ?, start_time = ?, end_time = ? WHERE id = ?",
            (name, start_time, end_time, shift_id)
        )
        self.conn.commit()

    # Schedule operations
    def get_schedule(self, year: int, month: int) -> Dict[int, Dict[str, Any]]:
        """Get schedule for a month, organized by worker_id -> {date: schedule_entry}."""
        start_date = date(year, month, 1)
        days_in_month = (start_date.replace(month=month % 12 + 1, day=1) - start_date).days - 1
        end_date = start_date.replace(day=days_in_month)

        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT s.*, w.name as worker_name, sh.name as shift_name,
                   sh.start_time as shift_start, sh.end_time as shift_end
            FROM schedule s
            JOIN workers w ON s.worker_id = w.id
            LEFT JOIN shifts sh ON s.shift_id = sh.id
            WHERE s.date >= ? AND s.date <= ?
            ORDER BY s.date, w.name
        ''', (start_date.isoformat(), end_date.isoformat()))

        schedule = {}
        for row in cursor.fetchall():
            worker_id = row['worker_id']
            if worker_id not in schedule:
                schedule[worker_id] = {}
            schedule[worker_id][row['date']] = dict(row)

        return schedule

    def set_schedule_entry(self, worker_id: int, date_str: str, shift_id: int,
                           status: str = 'working', user_override: bool = False):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO schedule (worker_id, date, shift_id, status, user_override)
            VALUES (?, ?, ?, ?, ?)
        ''', (worker_id, date_str, shift_id, status, 1 if user_override else 0))
        self.conn.commit()

    def clear_schedule(self, year: int, month: int):
        start_date = date(year, month, 1)
        days_in_month = (start_date.replace(month=month % 12 + 1, day=1) - start_date).days - 1
        end_date = start_date.replace(day=days_in_month)
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM schedule WHERE date >= ? AND date <= ?",
            (start_date.isoformat(), end_date.isoformat())
        )
        self.conn.commit()

    # Staffing requirements
    def get_staffing_requirements(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM staffing_requirements ORDER BY day_type, hour")
        return [dict(row) for row in cursor.fetchall()]

    def set_staffing_requirement(self, day_type: str, hour: int, workers_needed: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO staffing_requirements (day_type, hour, workers_needed)
            VALUES (?, ?, ?)
        ''', (day_type, hour, workers_needed))
        self.conn.commit()

    # Working hours
    def set_working_hours(self, day_type: str, start_time: str, end_time: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO working_hours (day_type, start_time, end_time)
            VALUES (?, ?, ?)
        ''', (day_type, start_time, end_time))
        self.conn.commit()

    def get_working_hours(self) -> Dict[str, Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM working_hours")
        result = {}
        for row in cursor.fetchall():
            result[row['day_type']] = {
                'start': row['start_time'],
                'end': row['end_time']
            }
        return result

    def close(self):
        self.conn.close()