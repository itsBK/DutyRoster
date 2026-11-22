"""Database models and operations using SQLite."""
from enum import IntEnum
import sqlite3
from datetime import date
from calendar import monthrange
from typing import List, Dict, Optional, Any


class UserType(IntEnum):
    NORMAL = 0
    MODERATOR = 1
    ADMIN = 2

class ShiftType(IntEnum):
    UNDEFINED = 0
    EARLY = 1
    MIDDLE = 2
    LATE = 3
    SPECIAL = 4

class ShiftDayType(IntEnum):
    UNDEFINED = 0
    WEEKDAY = 1
    WEEKEND = 2
    BOTH = 3

class DayType(IntEnum):
    OFF = 0
    WORKING = 1
    SICK = 2
    VACATION = 3
    SPECIAL_VACATION = 4

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
                passwordHash TEXT NOT NULL,
                type INTEGER DEFAULT 0,           -- 0:normal, 1:moderator, 2:admin
                initPasswordChanged INTEGER DEFAULT 0,  -- boolean
                createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Workers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employeeNumber INTEGER DEFAULT 0,
                name TEXT NOT NULL,
                workerCategoryId INTEGER NOT NULL,
                createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(workerCategoryId) REFERENCES workerCategories(id)
            )
        ''')

        # Linking users to workers
        # a worker could be a user but doesn't have to and the opposite is also true
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS userWorkerLink (
                userId INTEGER UNIQUE,
                workerId INTEGER UNIQUE,

                PRIMARY KEY(userId, workerId),
                FOREIGN KEY(userId) REFERENCES users(id),
                FOREIGN KEY(workerId) REFERENCES workers(id)
            )
        ''')

        # worker categories table (hours-per-week/month worker groups)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workerCategories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hours INTEGER NOT NULL,
                perWeek INTEGER DEFAULT 1           -- boolean: 1:week, 0:month
            )
        ''')

        # Shifts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                startTime TEXT NOT NULL,
                endTime TEXT NOT NULL,
                shiftType INTEGER NOT NULL,         -- 0:undefined, 1:early, 2:middle, 3:late, 4:special
                dayType INTEGER NOT NULL            -- 0:undefined, 1:weekday, 2:weekend, 3:both
            )
        ''')

        # Shifts preferences table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workerShifts (
                workerId INTEGER NOT NULL,
                shiftId INTEGER NOT NULL,
                force INTEGER DEFAULT 0,            -- boolean, true when the admin forces this shift to be assigned (when appicable)
                preferred INTEGER DEFAULT 0,        -- boolean, true when the worker desires this shift

                PRIMARY KEY(workerId, shiftId),
                FOREIGN KEY(workerId) REFERENCES workers(id),
                FOREIGN KEY(shiftId) REFERENCES shifts(id)
            )
        ''')

        # Schedule table (worker-day-shift assignments)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workerId INTEGER NOT NULL,
                date DATE NOT NULL,
                type INTEGER DEFAULT 0,             -- 0:off, 1:working, 2:sick, 3:vacation, 4:specialVacation
                shiftId INTEGER DEFAULT NULL,

                userOverride INTEGER DEFAULT 0,     -- boolean

                UNIQUE(workerId, date),
                FOREIGN KEY(workerId) REFERENCES workers(id),
                FOREIGN KEY(shiftId) REFERENCES shifts(id)
            )
        ''')

        # Staffing requirements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS staffingRequirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shiftType INTEGER DEFAULT 0,        -- 0:undefined, 1:early, 2:middle, 3:late, 4:special
                workersNeeded INTEGER NOT NULL,

                UNIQUE(shiftType, workersNeeded)
            )
        ''')

        # Working hours configuration
        # cursor.execute('''
        #     CREATE TABLE IF NOT EXISTS workingHours (
        #         dayType TEXT PRIMARY KEY,
        #         startTime TEXT NOT NULL,
        #         endTime TEXT NOT NULL
        #     )
        # ''')

        self.conn.commit()

    # User operations
    def createUser(self, username: str, password_hash: str, userType: UserType = UserType.NORMAL) -> Optional[int]:
        cursor = self.conn.cursor()
        row = cursor.execute(
            "INSERT OR IGNORE INTO users (username, passwordHash, type) VALUES (?, ?, ?) RETURNING id",
            (username, password_hash, userType)
        ).fetchone()
        self.conn.commit()

        return row['id'] if row else None

    def changeUserPassword(self, userId: int, newPasswordHash: str) -> bool:
        ''':returns: True on success'''
        cursor = self.conn.cursor()
        result = cursor.execute(
            "UPDATE users SET passwordHash = ?, initPasswordChanged = ? WHERE id = ?",
            (newPasswordHash, 1, userId))
        self.conn.commit()

        return True if result.rowcount > 0 else False


    def getUser(self, username: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def getUserById(self, userId: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (userId,))
        row = cursor.fetchone()
        return dict(row) if row else None


    # Worker operations
    def getWorkers(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT w.*, c.name as categoryName, c.hours, c.perWeek
            FROM workers w
            LEFT JOIN workerCategories c ON w.workerCategoryId = c.id
            ORDER BY w.name
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def getWorker(self, worker_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def createWorker(self, employeeNumber: int, name: str, workerCategoryId: int) -> Optional[int]:
        cursor = self.conn.cursor()
        row = cursor.execute('''
            INSERT INTO workers (employeeNumber, name, workerCategoryId)
            VALUES (?, ?, ?) RETURNING id
        ''', (employeeNumber, name, workerCategoryId)).fetchone()
        self.conn.commit()
        return row["id"] if row else None

    #TODO: check this function
    def updateWorker(self, worker_id: int, **kwargs):
        '''WARNING: needs checking'''
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
    def getCategories(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM workerCategories ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    def createCategory(self, name: str, hours: int, perWeek: bool) -> Optional[int]:
        ''':param perWeek: hours goal per week or per month'''
        cursor = self.conn.cursor()
        row = cursor.execute(
            "INSERT INTO workerCategories (name, hours, perWeek) VALUES (?, ?, ?) RETURNING id",
            (name, hours, 1 if perWeek else 0)
        ).fetchone()
        self.conn.commit()
        return row["id"] if row else None

    def updateCategory(self, categoryId: int, newName: str, newHours: int, perWeek: bool) -> bool:
        ''':return: True on success'''
        cursor = self.conn.cursor()
        result = cursor.execute(
            "UPDATE workerCategories SET name = ?, hours = ?, perWeek = ? WHERE id = ?",
            (newName, newHours, 1 if perWeek else 0, categoryId)
        )
        self.conn.commit()

        return True if result.rowcount > 0 else False

    # Shift operations
    def getShifts(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM shifts ORDER BY startTime")
        return [dict(row) for row in cursor.fetchall()]

    def createShift(self, name: str, startTime: str, endTime: str, shiftType: ShiftType, dayType: ShiftDayType) -> Optional[int]:
        cursor = self.conn.cursor()
        row = cursor.execute("""
            INSERT INTO shifts (name, startTime, endTime, shiftType, dayType)
            VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (name, startTime, endTime, shiftType, dayType)
        ).fetchone()
        self.conn.commit()
        return row["id"] if row else None

    #TODO: continue here
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
        _, days_in_month = monthrange(year, month)
        end_date = date(year, month, days_in_month)

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