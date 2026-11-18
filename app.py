#!/usr/bin/python3
"""Duty Roster Planning Application."""
import json
import argparse
import os
from datetime import date
from functools import wraps
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
import calendar
from auth import hash_password, verify_password, generate_session_token
from database import Database
from scheduler import Scheduler

# Load configuration
def load_config(config_file: str) -> dict:
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def parse_args(config: dict):
    """Parse command line arguments with config overrides."""
    parser = argparse.ArgumentParser(description='Duty Roster Planning Server')
    parser.add_argument('--port', type=int, default=config.get('server', {}).get('port', 5000),
                        help='HTTP port to listen on')
    parser.add_argument('--host', type=str, default=config.get('server', {}).get('host', '0.0.0.0'),
                        help='HTTP host to listen on')
    parser.add_argument('--ssl-cert', type=str, default=config.get('server', {}).get('ssl_cert'),
                        help='SSL certificate file path')
    parser.add_argument('--ssl-key', type=str, default=config.get('server', {}).get('ssl_key'),
                        help='SSL private key file path')
    parser.add_argument('--db', type=str, default=config.get('database', {}).get('path', 'roster.db'),
                        help='SQLite database file path')
    return parser.parse_args()


# Initialize app
config = load_config('config.json')
load_dotenv()
#args = parse_args(config)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0
)

# Initialize database and scheduler
#db = Database(args.db)
db = Database("roster.db")
scheduler = Scheduler(db)

# Initialize default data
def init_default_data():
    """Create default users, shifts, and categories if not exists."""
    # Default admin user
    if not db.get_user('bakbak'):
        db.create_user('bakbak', hash_password('2857atjpAAA'), is_admin=True)
    if not db.get_user("christian hammer"):
        db.create_user("christian hammer", hash_password("christian_not?_"), is_admin=True)

    # Default shifts
    shifts = db.get_shifts()
    if not shifts and config.get('default_shifts'):
        for shift in config['default_shifts']:
            db.create_shift(shift['name'], shift['start'], shift['end'])

    # Default working hours
    working_hours = db.get_working_hours()
    if not working_hours and config.get('working_hours'):
        for day_type, hours in config['working_hours'].items():
            db.set_working_hours(day_type, hours['start'], hours['end'])

init_default_data()


# Template helper functions
def get_weekday(year, month, day):
    """Get weekday abbreviation for a date."""
    return calendar.day_abbr[date(year, month, day).weekday()]


def get_cell(worker, day, year, month, schedule):
    """Get schedule cell for a worker on a given day."""
    worker_schedule = schedule.get(worker['id'], {})
    date_str = date(year, month, day).isoformat()
    return worker_schedule.get(date_str)


def get_cell_status(worker, day, year, month, schedule):
    """Get status class for a schedule cell."""
    cell = get_cell(worker, day, year, month, schedule)
    if cell:
        return cell['status']

    # Check vacation
    if scheduler.is_vacation_day(worker, date(year, month, day)):
        return 'vacation'

    return ''


# Register helper functions with Jinja2
app.jinja_env.globals['get_weekday'] = get_weekday
app.jinja_env.globals['get_cell'] = get_cell
app.jinja_env.globals['get_cell_status'] = get_cell_status


# Authentication helpers
def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = db.get_user(username)
        if user and verify_password(password, user['password_hash']):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            session['token'] = generate_session_token()
            session.permanent = True
            return redirect(url_for('roster'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def roster():
    """Main roster view - Excel-like interface."""
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    workers = db.get_workers()
    schedule = db.get_schedule(year, month)
    shifts = db.get_shifts()

    # Calculate validation status
    validation = scheduler.validate_schedule(year, month)

    # Calculate days in month
    _, days_in_month = calendar.monthrange(year, month)

    return render_template('roster.html',
                           workers=workers,
                           schedule=schedule,
                           year=year,
                           month=month,
                           validation=validation,
                           days_in_month=days_in_month,
                           shifts=shifts,
                           today=date.today())


@app.route('/api/workers', methods=['GET'])
@login_required
def get_workers_api():
    workers = db.get_workers()
    return jsonify(workers)


@app.route('/api/workers', methods=['POST'])
@login_required
def create_worker_api():
    data = request.json
    worker_id = db.create_worker(
        name=data['name'],
        shift_preference=data.get('shift_preference'),
        work_days_per_month=data.get('work_days_per_month', 20),
        category_id=data.get('category_id')
    )
    return jsonify({'id': worker_id}), 201


@app.route('/api/workers/<int:worker_id>', methods=['PUT'])
@login_required
def update_worker_api(worker_id):
    data = request.json
    db.update_worker(worker_id, **data)
    return jsonify({'success': True})


@app.route('/api/workers/<int:worker_id>/vacation', methods=['POST'])
@login_required
def set_vacation_api(worker_id):
    data = request.json
    db.update_worker(
        worker_id,
        on_vacation=data.get('on_vacation', 0),
        vacation_start=data.get('vacation_start'),
        vacation_end=data.get('vacation_end')
    )
    return jsonify({'success': True})


@app.route('/api/schedule', methods=['POST'])
@login_required
def set_schedule_api():
    data = request.json
    db.set_schedule_entry(
        worker_id=data['worker_id'],
        date_str=data['date'],
        shift_id=data.get('shift_id'),
        status=data.get('status', 'working'),
        user_override=data.get('user_override', False)
    )
    return jsonify({'success': True})


@app.route('/api/schedule/calculate', methods=['POST'])
@login_required
def calculate_schedule_api():
    data = request.json
    year = data.get('year', date.today().year)
    month = data.get('month', date.today().month)

    results = scheduler.generate_schedule(year, month)

    # Convert to serializable format
    results_serializable = {str(k): v for k, v in results.items()}

    return jsonify({'results': results_serializable})


@app.route('/api/shifts', methods=['GET'])
@login_required
def get_shifts_api():
    shifts = db.get_shifts()
    return jsonify(shifts)


@app.route('/api/shifts', methods=['POST'])
@login_required
def create_shift_api():
    data = request.json
    shift_id = db.create_shift(data['name'], data['start_time'], data['end_time'])
    return jsonify({'id': shift_id}), 201


@app.route('/api/shifts/<int:shift_id>', methods=['PUT'])
@login_required
def update_shift_api(shift_id):
    data = request.json
    db.update_shift(shift_id, data['name'], data['start_time'], data['end_time'])
    return jsonify({'success': True})


@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories_api():
    categories = db.get_categories()
    return jsonify(categories)


@app.route('/api/categories', methods=['POST'])
@login_required
def create_category_api():
    data = request.json
    category_id = db.create_category(data['name'], data.get('hours_per_week', 40))
    return jsonify({'id': category_id}), 201


@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@login_required
def update_category_api(category_id):
    data = request.json
    db.update_category(category_id, data['name'], data['hours_per_week'])
    return jsonify({'success': True})


@app.route('/api/staffing', methods=['GET'])
@login_required
def get_staffing_api():
    requirements = db.get_staffing_requirements()
    return jsonify(requirements)


@app.route('/api/staffing', methods=['POST'])
@login_required
def set_staffing_api():
    data = request.json
    db.set_staffing_requirement(data['day_type'], data['hour'], data['workers_needed'])
    return jsonify({'success': True})


@app.route('/api/working-hours', methods=['POST'])
@login_required
def set_working_hours_api():
    data = request.json
    db.set_working_hours(data['day_type'], data['start_time'], data['end_time'])
    return jsonify({'success': True})


@app.route('/workers')
@login_required
def workers():
    """Worker management page."""
    workers_list = db.get_workers()
    shifts = db.get_shifts()
    categories = db.get_categories()

    return render_template('workers.html',
                           workers=workers_list,
                           shifts=shifts,
                           categories=categories)


@app.route('/settings')
@login_required
def settings():
    """Settings page for shifts, categories, and staffing requirements."""
    shifts = db.get_shifts()
    categories = db.get_categories()
    staffing = db.get_staffing_requirements()
    working_hours = db.get_working_hours()

    return render_template('settings.html',
                           shifts=shifts,
                           categories=categories,
                           staffing=staffing,
                           working_hours=working_hours)

#TODO: temp; remove eventually
@app.route("/debug/session")
def debug_session():
    return {
        "scheme": request.scheme,
        "is_secure": request.is_secure,
        "host": request.host,
        "cookie_secure": app.config["SESSION_COOKIE_SECURE"],
        "cookie": session.get("token")
    }

#TODO: temp; remove eventually
@app.before_request
def debug_auth():
    app.logger.warning(
        "PATH=%s SECURE=%s USER_ID=%s TOKEN_EXISTS=%s",
        request.path,
        request.is_secure,
        session.get("user_id"),
        bool(session.get("token"))
    )


def create_app():
    ssl_context = None
    #if args.ssl_cert and args.ssl_key:
    #    ssl_context = (args.ssl_cert, args.ssl_key)

    app.run(
        host="127.0.0.1",
        port=8000,
        ssl_context=ssl_context,
        debug=False
    )
