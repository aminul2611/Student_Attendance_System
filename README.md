# Smart Campus — Student Task & Attendance Management System

A beginner-friendly Flask + SQLite project for a class. Includes student registration/login, admin dashboard, tasks and deadlines, QR-based attendance, reports, charts, and CSV exports.

## Features

- Student registration and login (passwords are hashed).
- Admin account is created automatically on first run.
- Admin can create class tasks and assign them to all students or one student.
- Students can mark tasks complete.
- Admin creates a dated attendance session and displays a QR code.
- Students log in on their phones and scan the QR code to mark attendance.
- A student can only mark attendance once per session; QR scan only works on the session date.
- Attendance and task CSV downloads.
- Dashboard, due-date reminders, attendance summaries and simple bar charts.
- `/health` endpoint for deployment checks.

## Requirements

- Python 3.10 or newer
- Internet connection for installing Python packages

## Run on Windows

Open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

If PowerShell blocks activation, run this once in the current terminal:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
Then activate the environment again.

## Default admin login (LOCAL DEMO ONLY)

- Email: `admin@smartcampus.local`
- Password: `Admin123!`

Change these before any public deployment using environment variables:
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `SECRET_KEY` (use a long random secret)

The default credentials are for local demonstration only. Do not deploy publicly with them.

## First demo

1. Log in as the admin.
2. Open **Students** to see registered students.
3. Register one or more student accounts using another browser/incognito window.
4. As admin, open **Tasks** and create a task with a deadline.
5. Open **Attendance**, create a session dated today, and show the QR code.
6. On a student's phone, open the deployed/local URL, log in, and scan the QR code.
7. Open **Reports** to see attendance and download CSV files.

### QR attendance note
For phones to scan a QR code, the web app must be reachable from the phone. `127.0.0.1` on the phone means the phone itself, not your computer. For a local classroom demo, use your computer's LAN IP on the same Wi-Fi and allow the port through the firewall, or use a deployed HTTPS URL. QR attendance is a basic classroom demo, not a secure anti-fraud system: students could share the QR URL while it is active.

## Database

SQLite database file `smart_campus.db` is created automatically. Back it up regularly. SQLite is appropriate for a class demonstration, but a multi-user public deployment should use a managed persistent database.

## Cloud deployment and costs

This app uses Flask and can run on a cloud host that supports Python web apps. The included `Procfile` uses Gunicorn.

Before deploying:
1. Set a strong `SECRET_KEY`.
2. Set a strong `ADMIN_EMAIL` and `ADMIN_PASSWORD`.
3. Do not expose the default admin credentials.
4. Check whether the host's current free tier includes persistent storage and whether it sleeps when idle.
5. Verify current pricing before adding cloud databases, load balancers, NAT gateways, or other paid resources.

**Important:** AWS is not guaranteed to be free. EC2, Elastic Beanstalk and related infrastructure can create charges even if the application code is free. A local demo is completely free aside from your own computer and internet; public hosting may have limits or charges. SQLite files on ephemeral cloud disks can be lost when the service restarts or redeploys. Use a persistent disk or managed database if the host supports it, and back up data.

## Current project limitations / next steps

- QR attendance is date-checked and prevents duplicate marks, but does not prove the student is physically in the classroom.
- Email reminders are not sent automatically yet; upcoming tasks are displayed in the dashboard.
- Password reset, email verification, HTTPS configuration, audit logs, and production-grade CSRF protection should be added before real institutional use.
- CSV export is implemented; CSV files can be opened in Excel. Native `.xlsx` export can be added if required.
