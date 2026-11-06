# Duty Roster Planner

A web-based duty roster planning application for scheduling 40-50 workers across shifts.

## Features

- Excel-like grid interface for scheduling
- User authentication with bcrypt password hashing
- Configurable shifts, worker categories, and staffing requirements
- Vacation and sick day management
- Automatic schedule calculation with constraint satisfaction
- Visual validation indicators (green check / red X)
- User override support

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py

# Or with custom port
python app.py --port 8080

# With SSL
python app.py --ssl-cert cert.pem --ssl-key key.pem
```

## Default Credentials

- Username: `admin`
- Password: `admin`

## Configuration

Edit `config.json` for server settings, or use command-line arguments. Command-line arguments override config file values.

## Database

SQLite database (`roster.db`) stores:
- Users and passwords (hashed)
- Worker profiles and shift preferences
- Schedule assignments
- Shift definitions
- Staffing requirements
- Working hours configuration