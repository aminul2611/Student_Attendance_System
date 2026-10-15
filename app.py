import os
import io
import csv
import base64
import secrets
import sqlite3
import time

from datetime import datetime, date
from functools import wraps
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import qrcode

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    g,
    abort,
    send_file,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


# --------------------------------------------------
# Application settings
# --------------------------------------------------

APP_DIR = os.path.abspath(os.path.dirname(__file__))

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(APP_DIR, "smart_campus.db"),
)

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32),
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

CAMPUS_TZ = ZoneInfo(
    os.environ.get("CAMPUS_TIMEZONE", "Asia/Shanghai")
)


def today_iso():
    return datetime.now(CAMPUS_TZ).date().isoformat()


def safe_next(value):
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
    ):
        return url_for("dashboard")

    parts = urlsplit(value)

    if (
        parts.netloc
        or parts.scheme
        or any(ord(character) < 32 for character in value)
    ):
        return url_for("dashboard")

    return value


# --------------------------------------------------
# Form protection
# --------------------------------------------------

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_forms():
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        saved_token = session.get("csrf_token", "")

        if (
            not submitted_token
            or not secrets.compare_digest(
                submitted_token,
                saved_token,
            )
        ):
            abort(
                400,
                description="Form expired. Reload the page and try again.",
            )


# --------------------------------------------------
# Database
# --------------------------------------------------

def connect_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    # Back up the old database before upgrading its schema.
    if os.path.isfile(DATABASE):
        with connect_db() as existing:
            columns = {
                row[1]
                for row in existing.execute(
                    "PRAGMA table_info(attendance_sessions)"
                )
            }

            if columns and "expires_at" not in columns:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = (
                    DATABASE + ".pre_upgrade_" + timestamp + ".bak"
                )

                with sqlite3.connect(backup_path) as backup:
                    existing.backup(backup)

    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student'
                    CHECK(role IN ('admin', 'student')),
                student_no TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT 'Medium',
                created_by INTEGER,
                assigned_to INTEGER,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by)
                    REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(assigned_to)
                    REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course TEXT NOT NULL,
                session_date TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by)
                    REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Present',
                marked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, student_id),
                FOREIGN KEY(session_id)
                    REFERENCES attendance_sessions(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(student_id)
                    REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        user_columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(users)")
        }

        if "active" not in user_columns:
            db.execute(
                """
                ALTER TABLE users
                ADD COLUMN active INTEGER NOT NULL DEFAULT 1
                """
            )

        attendance_columns = {
            row[1]
            for row in db.execute(
                "PRAGMA table_info(attendance_sessions)"
            )
        }

        if "expires_at" not in attendance_columns:
            db.execute(
                """
                ALTER TABLE attendance_sessions
                ADD COLUMN expires_at INTEGER NOT NULL DEFAULT 0
                """
            )

            db.execute(
                "UPDATE attendance_sessions SET active = 0"
            )

        # Convert legacy class-wide tasks into individual assignments.
        shared_tasks = db.execute(
            "SELECT * FROM tasks WHERE assigned_to IS NULL"
        ).fetchall()

        for task in shared_tasks:
            targets = db.execute(
                """
                SELECT id
                FROM users
                WHERE role = 'student' AND active = 1
                """
            ).fetchall()

            if not targets:
                continue

            for student in targets:
                db.execute(
                    """
                    INSERT INTO tasks(
                        title,
                        description,
                        due_date,
                        priority,
                        created_by,
                        assigned_to,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task["title"],
                        task["description"],
                        task["due_date"],
                        task["priority"],
                        task["created_by"],
                        student["id"],
                        "Pending",
                    ),
                )

            db.execute(
                "DELETE FROM tasks WHERE id = ?",
                (task["id"],),
            )

        admin_email = os.environ.get(
            "ADMIN_EMAIL",
            "admin@smartcampus.local",
        ).strip().lower()

        admin_password = os.environ.get("ADMIN_PASSWORD")

        admin = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (admin_email,),
        ).fetchone()

        if not admin:
            if not admin_password or len(admin_password) < 7:
                raise RuntimeError(
                    "Set ADMIN_PASSWORD to at least 12 characters "
                    "before first startup."
                )

            db.execute(
                """
                INSERT INTO users(
                    name,
                    email,
                    password_hash,
                    role,
                    student_no
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Smart Campus Admin",
                    admin_email,
                    generate_password_hash(admin_password),
                    "admin",
                    None,
                ),
            )


# --------------------------------------------------
# Authentication helpers
# --------------------------------------------------

@app.before_request
def load_user():
    g.user = None

    if session.get("user_id"):
        with connect_db() as db:
            g.user = db.execute(
                """
                SELECT *
                FROM users
                WHERE id = ? AND active = 1
                """,
                (session["user_id"],),
            ).fetchone()

        if not g.user:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please log in to continue.", "warning")

            return redirect(
                url_for("login", next=request.path)
            )

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(
                url_for(
                    "login",
                    role="admin",
                    next=request.path,
                )
            )

        if g.user["role"] != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {
        "today": today_iso(),
        "now_ts": int(time.time()),
        "developer_name": os.environ.get(
            "DEVELOPER_NAME",
            "Aminul  Islam ",
        ),
    }


# --------------------------------------------------
# Home and accounts
# --------------------------------------------------

@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))

    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        student_no = request.form.get("student_no", "").strip()
        password = request.form.get("password", "")

        if (
            not name
            or not email
            or not student_no
            or len(password) < 8
        ):
            flash(
                "Fill in all fields. Password must be at least "
                "8 characters.",
                "danger",
            )

            return render_template("register.html")

        try:
            with connect_db() as db:
                db.execute(
                    """
                    INSERT INTO users(
                        name,
                        email,
                        password_hash,
                        role,
                        student_no
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        "student",
                        student_no,
                    ),
                )

            flash(
                "Registration successful. You can now log in.",
                "success",
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash(
                "That email or student ID is already registered.",
                "danger",
            )

    return render_template("register.html")


# Login page for the selected role.
@app.route("/login", methods=["GET", "POST"])
@app.route("/login/<role>", methods=["GET", "POST"])
def login(role=None):
    selected_role = role or request.args.get("role", "student")

    if selected_role not in ("admin", "teacher", "student"):
        abort(404)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with connect_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if (
            user
            and user["active"]
            and user["role"] == selected_role
            and check_password_hash(
                user["password_hash"],
                password,
            )
        ):
            session.clear()
            session["user_id"] = user["id"]

            flash(
                f"Welcome, {user['name']}!",
                "success",
            )

            destination = (
                request.form.get("next")
                or request.args.get("next")
            )

            return redirect(safe_next(destination))

        flash(
            "Email, password or selected role is incorrect, "
            "or account is disabled.",
            "danger",
        )

    return render_template(
        "login.html",
        selected_role=selected_role,
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")

    return redirect(url_for("index"))


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    if g.user["role"] == "admin":
        return redirect(
            url_for("admin_portal.dashboard")
        )

    if g.user["role"] == "teacher":
        return redirect(
            url_for("teacher.dashboard")
        )

    with connect_db() as db:
        if g.user["role"] == "admin":
            stats = {
                "students": db.execute(
                    """
                    SELECT COUNT(*)
                    FROM users
                    WHERE role = 'student'
                    """
                ).fetchone()[0],

                "tasks": db.execute(
                    "SELECT COUNT(*) FROM tasks"
                ).fetchone()[0],

                "sessions": db.execute(
                    "SELECT COUNT(*) FROM attendance_sessions"
                ).fetchone()[0],

                "attendance": db.execute(
                    "SELECT COUNT(*) FROM attendance"
                ).fetchone()[0],
            }

            task_rows = db.execute(
                """
                SELECT t.*, u.name AS student_name
                FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                ORDER BY
                    CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END,
                    COALESCE(t.due_date, '9999-12-31')
                LIMIT 8
                """
            ).fetchall()

            upcoming = db.execute(
                """
                SELECT *
                FROM tasks
                WHERE due_date IS NOT NULL
                  AND due_date >= ?
                  AND status != 'Completed'
                ORDER BY due_date
                LIMIT 5
                """,
                (today_iso(),),
            ).fetchall()

            return render_template(
                "dashboard.html",
                stats=stats,
                tasks=task_rows,
                upcoming=upcoming,
            )

        task_rows = db.execute(
            """
            SELECT *
            FROM tasks
            WHERE assigned_to = ? OR assigned_to IS NULL
            ORDER BY
                CASE WHEN status = 'Completed' THEN 1 ELSE 0 END,
                COALESCE(due_date, '9999-12-31')
            """,
            (g.user["id"],),
        ).fetchall()

        attendance_total = db.execute(
            """
            SELECT COUNT(*)
            FROM attendance_sessions
            WHERE session_date <= ?
            """,
            (today_iso(),),
        ).fetchone()[0]

        attendance_present = db.execute(
            """
            SELECT COUNT(*)
            FROM attendance a
            JOIN attendance_sessions s ON s.id = a.session_id
            WHERE a.student_id = ?
              AND a.status = 'Present'
              AND s.session_date <= ?
            """,
            (g.user["id"], today_iso()),
        ).fetchone()[0]

        percentage = (
            round(attendance_present * 100 / attendance_total, 1)
            if attendance_total
            else 0
        )

        stats = {
            "tasks": len(task_rows),
            "completed": sum(
                1
                for task in task_rows
                if task["status"] == "Completed"
            ),
            "attendance": percentage,
            "sessions": attendance_total,
        }

        upcoming = db.execute(
            """
            SELECT *
            FROM tasks
            WHERE (assigned_to = ? OR assigned_to IS NULL)
              AND due_date IS NOT NULL
              AND due_date >= ?
              AND status != 'Completed'
            ORDER BY due_date
            LIMIT 5
            """,
            (g.user["id"], today_iso()),
        ).fetchall()

    return render_template(
        "dashboard.html",
        stats=stats,
        tasks=task_rows,
        upcoming=upcoming,
    )


# --------------------------------------------------
# Tasks
# --------------------------------------------------

@app.route("/tasks")
@login_required
def tasks():
    with connect_db() as db:
        if g.user["role"] == "admin":
            rows = db.execute(
                """
                SELECT t.*, u.name AS student_name
                FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                ORDER BY
                    COALESCE(t.due_date, '9999-12-31'),
                    t.id DESC
                """
            ).fetchall()

            student_rows = db.execute(
                """
                SELECT id, name, student_no
                FROM users
                WHERE role = 'student' AND active = 1
                ORDER BY name
                """
            ).fetchall()

        else:
            rows = db.execute(
                """
                SELECT t.*, NULL AS student_name
                FROM tasks t
                WHERE t.assigned_to = ? OR t.assigned_to IS NULL
                ORDER BY
                    COALESCE(t.due_date, '9999-12-31'),
                    t.id DESC
                """,
                (g.user["id"],),
            ).fetchall()

            student_rows = []

    return render_template(
        "tasks.html",
        tasks=rows,
        students=student_rows,
    )


@app.route("/tasks/add", methods=["POST"])
@admin_required
def add_task():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date = request.form.get("due_date") or None
    priority = request.form.get("priority", "Medium")
    assigned_to = request.form.get("assigned_to") or None

    try:
        if due_date:
            due_date = date.fromisoformat(due_date).isoformat()

        if not title or priority not in ("Low", "Medium", "High"):
            raise ValueError()

        with connect_db() as db:
            if assigned_to:
                targets = db.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE id = ?
                      AND role = 'student'
                      AND active = 1
                    """,
                    (assigned_to,),
                ).fetchall()
            else:
                targets = db.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE role = 'student' AND active = 1
                    """
                ).fetchall()

            if not targets:
                flash(
                    "No active students selected. "
                    "Register a student first.",
                    "warning",
                )

                return redirect(url_for("tasks"))

            for target in targets:
                db.execute(
                    """
                    INSERT INTO tasks(
                        title,
                        description,
                        due_date,
                        priority,
                        created_by,
                        assigned_to
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title,
                        description,
                        due_date,
                        priority,
                        g.user["id"],
                        target["id"],
                    ),
                )

        flash(
            f"Task assigned independently to "
            f"{len(targets)} student(s).",
            "success",
        )

    except ValueError:
        flash(
            "Enter a title, valid date and priority.",
            "danger",
        )

    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(task_id):
    with connect_db() as db:
        task = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

        if not task:
            abort(404)

        if (
            g.user["role"] != "admin"
            and task["assigned_to"] != g.user["id"]
        ):
            abort(403)

        new_status = request.form.get("status", "Completed")

        if new_status not in (
            "Pending",
            "In Progress",
            "Completed",
        ):
            abort(400)

        db.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (new_status, task_id),
        )

    flash("Task status updated.", "success")

    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@admin_required
def delete_task(task_id):
    with connect_db() as db:
        db.execute(
            "DELETE FROM tasks WHERE id = ?",
            (task_id,),
        )

    flash("Task deleted.", "info")

    return redirect(url_for("tasks"))


# --------------------------------------------------
# Attendance
# --------------------------------------------------

@app.route("/attendance")
@login_required
def attendance():
    with connect_db() as db:
        if g.user["role"] == "admin":
            rows = db.execute(
                """
                SELECT s.*,
                    (
                        SELECT COUNT(*)
                        FROM attendance a
                        WHERE a.session_id = s.id
                    ) AS marked
                FROM attendance_sessions s
                ORDER BY s.session_date DESC, s.id DESC
                """
            ).fetchall()

        else:
            rows = db.execute(
                """
                SELECT
                    s.*,
                    a.status AS my_status,
                    a.marked_at AS my_marked_at
                FROM attendance_sessions s
                LEFT JOIN attendance a
                    ON a.session_id = s.id
                    AND a.student_id = ?
                ORDER BY s.session_date DESC, s.id DESC
                """,
                (g.user["id"],),
            ).fetchall()

    return render_template(
        "attendance.html",
        sessions=rows,
    )


@app.route("/attendance/create", methods=["POST"])
@admin_required
def create_attendance():
    course = request.form.get("course", "").strip()
    session_date = (
        request.form.get("session_date")
        or today_iso()
    )

    if not course:
        flash("Enter a course or class name.", "danger")
        return redirect(url_for("attendance"))

    if session_date != today_iso():
        flash(
            "Create QR sessions for today only.",
            "danger",
        )

        return redirect(url_for("attendance"))

    token = secrets.token_urlsafe(24)

    # Five minutes from session creation.
    expires_at = int(time.time()) + 300

    with connect_db() as db:
        cursor = db.execute(
            """
            INSERT INTO attendance_sessions(
                course,
                session_date,
                token,
                created_by,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                course,
                session_date,
                token,
                g.user["id"],
                expires_at,
            ),
        )

        session_id = cursor.lastrowid

    flash(
        "Attendance session created. "
        "The QR code is valid for 5 minutes.",
        "success",
    )

    return redirect(
        url_for("attendance_qr", session_id=session_id)
    )


@app.route("/attendance/<int:session_id>/qr")
@admin_required
def attendance_qr(session_id):
    with connect_db() as db:
        row = db.execute(
            """
            SELECT *
            FROM attendance_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    if not row:
        abort(404)

    path = url_for(
        "scan_attendance",
        token=row["token"],
    )

    base_url = os.environ.get(
        "PUBLIC_BASE_URL",
        request.url_root,
    ).rstrip("/")

    scan_url = base_url + path

    qr = qrcode.QRCode(
        box_size=8,
        border=3,
    )

    qr.add_data(scan_url)
    qr.make(fit=True)

    image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    output = io.BytesIO()
    image.save(output, format="PNG")

    qr_data = base64.b64encode(
        output.getvalue()
    ).decode("ascii")

    return render_template(
        "attendance_qr.html",
        session_row=row,
        qr_data=qr_data,
        scan_url=scan_url,
    )


@app.route(
    "/attendance/scan/<token>",
    methods=["GET", "POST"],
)
@login_required
def scan_attendance(token):
    if g.user["role"] != "student":
        flash(
            "QR attendance is for student accounts.",
            "warning",
        )

        return redirect(url_for("attendance"))

    with connect_db() as db:
        if request.method == "POST":
            db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT *
            FROM attendance_sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

        if not row:
            abort(404)

        existing = db.execute(
            """
            SELECT id
            FROM attendance
            WHERE session_id = ? AND student_id = ?
            """,
            (row["id"], g.user["id"]),
        ).fetchone()

        if existing:
            flash(
                "Your attendance is already recorded for this class.",
                "info",
            )

            return redirect(url_for("attendance"))

        if (
            not row["active"]
            or row["expires_at"] <= time.time()
            or row["session_date"] != today_iso()
        ):
            flash(
                "This QR session has expired or been closed.",
                "danger",
            )

            return redirect(url_for("attendance"))

        if request.method == "GET":
            return render_template(
                "attendance_confirm.html",
                session_row=row,
            )

        db.execute(
            """
            INSERT INTO attendance(
                session_id,
                student_id,
                status
            )
            VALUES (?, ?, ?)
            """,
            (
                row["id"],
                g.user["id"],
                "Present",
            ),
        )

        flash(
            f"Attendance marked for {row['course']}.",
            "success",
        )

    return redirect(url_for("attendance"))


@app.route(
    "/attendance/<int:session_id>/close",
    methods=["POST"],
)
@admin_required
def close_attendance(session_id):
    with connect_db() as db:
        db.execute(
            """
            UPDATE attendance_sessions
            SET active = 0
            WHERE id = ?
            """,
            (session_id,),
        )

    flash("Attendance session closed.", "info")

    return redirect(url_for("attendance"))


# --------------------------------------------------
# Reports and exports
# --------------------------------------------------

@app.route("/reports")
@admin_required
def reports():
    with connect_db() as db:
        student_rows = db.execute(
            """
            SELECT
                u.id,
                u.name,
                u.student_no,
                u.email,
                (
                    SELECT COUNT(*)
                    FROM attendance a
                    WHERE a.student_id = u.id
                      AND a.status = 'Present'
                ) AS present_count,
                (
                    SELECT COUNT(*)
                    FROM attendance_sessions s
                    WHERE s.session_date <= ?
                ) AS total_sessions,
                (
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.assigned_to = u.id
                      AND t.status = 'Completed'
                ) AS completed_tasks,
                (
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.assigned_to = u.id
                ) AS assigned_tasks
            FROM users u
            WHERE u.role = 'student'
            ORDER BY u.name
            """,
            (today_iso(),),
        ).fetchall()

        recent = db.execute(
            """
            SELECT
                s.course,
                s.session_date,
                u.name,
                u.student_no,
                a.status,
                a.marked_at
            FROM attendance a
            JOIN users u ON u.id = a.student_id
            JOIN attendance_sessions s ON s.id = a.session_id
            ORDER BY s.session_date DESC, a.marked_at DESC
            LIMIT 30
            """
        ).fetchall()

    return render_template(
        "reports.html",
        students=student_rows,
        recent=recent,
    )


@app.route("/export/<kind>")
@admin_required
def export_data(kind):
    with connect_db() as db:
        if kind == "attendance":
            rows = db.execute(
                """
                SELECT
                    s.course,
                    s.session_date,
                    u.name,
                    u.student_no,
                    u.email,
                    a.status,
                    a.marked_at
                FROM attendance a
                JOIN attendance_sessions s ON s.id = a.session_id
                JOIN users u ON u.id = a.student_id
                ORDER BY s.session_date DESC, u.name
                """
            ).fetchall()

            headers = [
                "Course",
                "Date",
                "Student Name",
                "Student ID",
                "Email",
                "Status",
                "Marked At",
            ]

        elif kind == "tasks":
            rows = db.execute(
                """
                SELECT
                    t.title,
                    t.description,
                    t.due_date,
                    t.priority,
                    t.status,
                    u.name AS assigned_student,
                    t.created_at
                FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                ORDER BY t.id DESC
                """
            ).fetchall()

            headers = [
                "Title",
                "Description",
                "Due Date",
                "Priority",
                "Status",
                "Assigned Student",
                "Created At",
            ]

        else:
            abort(404)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for row in rows:
        values = []

        for key in row.keys():
            value = row[key]

            if (
                value is not None
                and str(value).lstrip().startswith(
                    ("=", "+", "-", "@")
                )
            ):
                value = "'" + str(value)

            values.append(value)

        writer.writerow(values)

    data = io.BytesIO(
        output.getvalue().encode("utf-8-sig")
    )

    filename = (
        f"smart_campus_{kind}_{today_iso()}.csv"
    )

    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


# --------------------------------------------------
# Student management
# --------------------------------------------------

@app.route("/admin/students")
@admin_required
def students():
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT
                u.id,
                u.name,
                u.email,
                u.student_no,
                u.created_at,
                u.active,
                (
                    SELECT COUNT(*)
                    FROM attendance a
                    WHERE a.student_id = u.id
                      AND a.status = 'Present'
                ) AS present_count
            FROM users u
            WHERE u.role = 'student'
            ORDER BY u.name
            """
        ).fetchall()

    return render_template(
        "students.html",
        students=rows,
    )


@app.route(
    "/admin/students/<int:user_id>/toggle",
    methods=["POST"],
)
@admin_required
def toggle_student(user_id):
    with connect_db() as db:
        db.execute(
            """
            UPDATE users
            SET active = 1 - active
            WHERE id = ? AND role = 'student'
            """,
            (user_id,),
        )

    flash("Student access updated.", "success")

    return redirect(url_for("students"))


@app.route(
    "/admin/students/<int:user_id>/delete",
    methods=["POST"],
)
@admin_required
def delete_student(user_id):
    with connect_db() as db:
        db.execute(
            """
            DELETE FROM users
            WHERE id = ? AND role = 'student'
            """,
            (user_id,),
        )

    flash("Student account deleted.", "info")

    return redirect(url_for("students"))


# --------------------------------------------------
# Errors and health
# --------------------------------------------------

@app.route("/health")
def health():
    return {
        "status": "ok",
        "app": "Smart Campus",
    }


@app.errorhandler(400)
def bad_request(error):
    return render_template(
        "error.html",
        code=400,
        message=error.description,
    ), 400


@app.errorhandler(403)
def forbidden(_error):
    return render_template(
        "error.html",
        code=403,
        message="You do not have permission to access this page.",
    ), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template(
        "error.html",
        code=404,
        message="The requested page was not found.",
    ), 404

from portal import init_portals


with app.app_context():
    init_db()
    init_portals(app, connect_db, DATABASE, CAMPUS_TZ)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )