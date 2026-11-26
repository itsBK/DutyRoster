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

    def updateShift(self, shiftId: int, newName: str, startTime: str, endTime: str, shiftType: ShiftType, dayType: ShiftDayType) -> bool:
        ''':return: True on success'''
        cursor = self.conn.cursor()
        result = cursor.execute(
            """UPDATE shifts
            SET name = ?, startTime = ?, endTime = ?, shiftType = ?, dayType = ?
            WHERE id = ?""",
            (newName, startTime, endTime, shiftType, dayType, shiftId)
        )
        self.conn.commit()
        return True if result.rowcount > 0 else False

    # Schedule operations
    def getSchedule(self, year: int, month: int) -> Dict[int, Dict[str, Any]]:
        """Get schedule for a month, organized by worker_id -> {date: schedule_entry}."""
        startDate = date(year, month, 1)
        _, days_in_month = monthrange(year, month)
        endDate = date(year, month, days_in_month)

        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT scd.*,
                w.name as workerName, w.employeeNumber as employeeNumber, w.workerCategoryId,
                sh.name as shiftName, sh.startTime as shiftStart, sh.endTime as shiftEnd,
                wCtg.name as categoryName, wCtg.hours as categoryHoues, wCtg.perWeek as isHoursPerWeek
            FROM schedule scd
            JOIN workers w ON scd.workerId = w.id
            LEFT JOIN shifts sh ON scd.shiftId = sh.id
            LEFT JOIN workerCategories wCtg ON w.workerCategoryId = wCtg.id
            WHERE scd.date >= ? AND scd.date <= ?
            ORDER BY scd.date, workerGroupId, w.name
        ''', (startDate.isoformat(), endDate.isoformat()))

        schedule = {}
        for entry in cursor.fetchall():
            workerId = entry['workerId']
            if workerId not in schedule:
                schedule[workerId] = {}
            schedule[workerId][entry['date']] = dict(entry)

        return schedule

    def setScheduleEntry(self, workerId: int, dateStr: str, type: DayType,
                         shiftId: int, userOverride: bool) -> bool:
        ''':return: True on success'''
        cursor = self.conn.cursor()
        result = cursor.execute('''
            INSERT OR REPLACE INTO schedule (workerId, date, type, shiftId, userOverride)
            VALUES (?, ?, ?, ?, ?)''',
            (workerId, dateStr, type, shiftId, 1 if userOverride else 0)
        )
        self.conn.commit()
        return True if result.rowcount > 0 else False

    # Staffing requirements
    def getStaffingRequirements(self) -> List[Dict]:
        cursor = self.conn.cursor()
        result = cursor.execute("SELECT * FROM staffingRequirements ORDER BY shiftType, workersNeeded")
        return [dict(row) for row in cursor.fetchall()]

    def setStaffingRequirement(self, shiftType: ShiftType, workersNeeded: int) -> bool:
        cursor = self.conn.cursor()
        result = cursor.execute('''
            INSERT OR REPLACE INTO staffingRequirements (shiftType, workersNeeded)
            VALUES (?, ?)
        ''', (shiftType, workersNeeded))
        self.conn.commit()
        return True if result.rowcount > 0 else False

    def close(self):
        self.conn.close()
