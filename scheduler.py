"""Scheduling algorithm for duty roster planning."""
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
import random
from database import Database


class Scheduler:
    def __init__(self, db: Database):
        self.db = db

    def get_days_in_month(self, year: int, month: int) -> List[date]:
        """Get all dates in a month."""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        start = date(year, month, 1)
        end = next_month - timedelta(days=1)

        days = []
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days

    def is_vacation_day(self, worker: Dict, day: date) -> bool:
        """Check if a worker is on vacation on a given day."""
        if not worker['on_vacation'] or not worker['vacation_start'] or not worker['vacation_end']:
            return False
        vacation_start = date.fromisoformat(worker['vacation_start'])
        vacation_end = date.fromisoformat(worker['vacation_end'])
        return vacation_start <= day <= vacation_end

    def get_vacation_off_days(self, worker: Dict, month_days: List[date]) -> List[date]:
        """Calculate mandatory off days before/after 5+ consecutive vacation days."""
        if not worker['on_vacation'] or not worker['vacation_start'] or not worker['vacation_end']:
            return []

        vacation_start = date.fromisoformat(worker['vacation_start'])
        vacation_end = date.fromisoformat(worker['vacation_end'])

        # Check if vacation is 5 or more consecutive days
        vacation_length = (vacation_end - vacation_start).days + 1
        if vacation_length < 5:
            return []

        # Add 2 days off before and after the vacation
        off_days = set()
        for i in range(1, 3):
            day_before = vacation_start - timedelta(days=i)
            day_after = vacation_end + timedelta(days=i)
            off_days.add(day_before)
            off_days.add(day_after)

        return list(off_days)

    def get_weekday_count(self, day: date, month_days: List[date]) -> int:
        """Count how many work days this week for a given date."""
        # Find Monday of this week
        week_start = day - timedelta(days=day.weekday())
        # Find Friday of this week
        week_end = week_start + timedelta(days=4)

        count = 0
        for d in month_days:
            if week_start <= d <= week_end:
                count += 1
        return count

    def generate_schedule(self, year: int, month: int) -> Dict[int, Dict]:
        """
        Generate schedule for the month.
        Returns dict of worker_id -> {status: 'ok'|'error', unassigned_days: int}
        """
        workers = self.db.get_workers()
        shifts = self.db.get_shifts()
        month_days = self.get_days_in_month(year, month)

        if not shifts:
            # Cannot schedule without shifts
            results = {}
            for worker in workers:
                results[worker['id']] = {'status': 'error', 'unassigned_days': len(month_days)}
            return results

        # Clear previous auto-generated schedule (keep user overrides)
        start_date = date(year, month, 1)
        end_date = month_days[-1]
        cursor = self.db.conn.cursor()
        cursor.execute('DELETE FROM schedule WHERE date >= ? AND date <= ? AND user_override = 0',
                       (start_date.isoformat(), end_date.isoformat()))
        self.db.conn.commit()

        # For each day, schedule workers
        for day in month_days:
            day_type = 'weekday' if day.weekday() < 5 else 'weekend'

            for worker in workers:
                worker_id = worker['id']
                date_str = day.isoformat()

                # Skip if already scheduled by user override
                cursor.execute('SELECT id, shift_id FROM schedule WHERE worker_id = ? AND date = ?',
                               (worker_id, date_str))
                row = cursor.fetchone()
                if row:
                    continue

                # Check vacation
                if self.is_vacation_day(worker, day):
                    self.db.set_schedule_entry(worker_id, date_str, None, 'vacation')
                    continue

                # Check vacation off days
                off_days = self.get_vacation_off_days(worker, month_days)
                if day in off_days:
                    self.db.set_schedule_entry(worker_id, date_str, None, 'off')
                    continue

                # Check consecutive work days (max 5 per week)
                week_start = day - timedelta(days=day.weekday())
                week_end = week_start + timedelta(days=4)

                cursor.execute('''
                    SELECT COUNT(*) FROM schedule
                    WHERE worker_id = ? AND date >= ? AND date <= ? AND status = 'working'
                ''', (worker_id, week_start.isoformat(), week_end.isoformat()))
                work_days_this_week = cursor.fetchone()[0]

                if work_days_this_week >= 5:
                    # Worker already worked 5 days this week
                    self.db.set_schedule_entry(worker_id, date_str, None, 'off')
                    continue

                # Check if worker prefers to be off (based on work_days_per_month)
                # This is a simplified heuristic
                days_worked_this_month = 0
                cursor.execute('''
                    SELECT COUNT(*) FROM schedule
                    WHERE worker_id = ? AND date >= ? AND date <= ? AND status = 'working'
                ''', (worker_id, start_date.isoformat(), day.isoformat()))
                days_worked_this_month = cursor.fetchone()[0]

                # Target days per week based on monthly target
                target_weekly = (worker['work_days_per_month'] or 20) / 4.33

                # Assign shift based on preference or random
                shift_id = None
                if worker['shift_preference']:
                    cursor.execute('SELECT id FROM shifts WHERE name = ?', (worker['shift_preference'],))
                    shift_row = cursor.fetchone()
                    if shift_row:
                        shift_id = shift_row['id']

                if not shift_id:
                    # Pick a shift (round-robin or random)
                    shift_id = random.choice(shifts)['id']

                if shift_id:
                    self.db.set_schedule_entry(worker_id, date_str, shift_id, 'working')

        # Validate and report
        return self.validate_schedule(year, month)

    def validate_schedule(self, year: int, month: int) -> Dict[int, Dict]:
        """Validate the current schedule and return status for each worker."""
        workers = self.db.get_workers()
        month_days = self.get_days_in_month(year, month)
        schedule = self.db.get_schedule(year, month)
        results = {}

        for worker in workers:
            worker_id = worker['id']
            worker_schedule = schedule.get(worker_id, {})

            unassigned = 0
            for day in month_days:
                date_str = day.isoformat()
                if date_str not in worker_schedule:
                    unassigned += 1

            if unassigned > 0:
                results[worker_id] = {'status': 'error', 'unassigned_days': unassigned}
            else:
                results[worker_id] = {'status': 'ok', 'unassigned_days': 0}

        return results