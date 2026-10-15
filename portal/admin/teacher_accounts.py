import re
import sqlite3
from datetime import date

from flask import abort, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from . import bp
from ..common import database, require


def teacher_rows():
    with database() as db:
        return db.execute("""
            SELECT
                u.id,
                u.name,
                u.email,
                u.active,
                COALESCE(p.department, '') AS department
            FROM users u
            LEFT JOIN teacher_profiles p
                ON p.user_id = u.id
            WHERE u.role = 'teacher'
            ORDER BY u.name COLLATE NOCASE, u.id
        """).fetchall()


def identity():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()

    if not 1 <= len(name) <= 100:
        raise ValueError(
            "Enter a name using 1-100 characters."
        )

    if (
        len(email) > 254
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    ):
        raise ValueError("Enter a valid email address.")

    return name, email


def password_error():
    password = request.form.get("new_password", "")
    confirmation = request.form.get("confirm_password", "")

    if not 8 <= len(password) <= 128:
        return "Password must contain 8-128 characters."

    if password != confirmation:
        return "Passwords do not match."

    return None

@bp.get("/teacher-details")
@require("admin")
def teacher_details():
    month = request.args.get("month", "").strip()

    try:
        start = date.fromisoformat(month + "-01")
    except ValueError:
        start = date.today().replace(day=1)

    selected_month = start.strftime("%Y-%m")

    if start.month == 12:
        end_text = f"{start.year + 1:04d}-01-01"
    else:
        end_text = (
            f"{start.year:04d}-{start.month + 1:02d}-01"
        )

    with database() as db:
        attendance_chart = db.execute(
            """
            SELECT
                u.id,
                u.name,
                COUNT(DISTINCT a.work_date) AS checkin_days
            FROM users u
            LEFT JOIN teacher_work_attendance a
                ON a.teacher_id = u.id
                AND a.work_date >= ?
                AND a.work_date < ?
                AND a.check_in IS NOT NULL
            WHERE u.role = 'teacher'
            GROUP BY u.id, u.name
            ORDER BY checkin_days DESC,
                     u.name COLLATE NOCASE,
                     u.id
            """,
            (start.isoformat(), end_text),
        ).fetchall()

    chart_max = max(
        (row["checkin_days"] for row in attendance_chart),
        default=0,
    )

    return render_template(
        "admin/teacher_details.html",
        teachers=teacher_rows(),
        attendance_chart=attendance_chart,
        chart_max=max(chart_max, 1),
        selected_month=selected_month,
        month_label=start.strftime("%B %Y"),
    )


@bp.post("/teacher-details/create")
@require("admin")
def create_teacher_account():
    try:
        name, email = identity()
    except ValueError as error:
        return jsonify(
            ok=False,
            message=str(error),
        ), 400

    department = request.form.get("department", "").strip()

    if len(department) > 150:
        return jsonify(
            ok=False,
            message="Department must be within 150 characters.",
        ), 400

    error = password_error()

    if error:
        return jsonify(ok=False, message=error), 400

    hashed = generate_password_hash(
        request.form["new_password"]
    )

    try:
        with database() as db:
            existing = db.execute(
                "SELECT 1 FROM users WHERE lower(email) = ?",
                (email,),
            ).fetchone()

            if existing:
                return jsonify(
                    ok=False,
                    message="This email is already in use.",
                ), 409

            teacher_id = db.execute("""
                INSERT INTO users(
                    name,
                    email,
                    password_hash,
                    role,
                    active
                )
                VALUES (?, ?, ?, 'teacher', 1)
            """, (name, email, hashed)).lastrowid

            db.execute("""
                INSERT INTO teacher_profiles(
                    user_id,
                    department
                )
                VALUES (?, ?)
            """, (teacher_id, department))

    except sqlite3.IntegrityError:
        return jsonify(
            ok=False,
            message=(
                "Could not create account. "
                "Check the email and try again."
            ),
        ), 409

    return jsonify(
        ok=True,
        message="Teacher account created successfully.",
        html=render_template(
            "admin/teacher_rows.html",
            teachers=teacher_rows(),
        ),
    )


@bp.route(
    "/teacher-details/<int:teacher_id>/account",
    methods=["GET", "POST"],
)
@require("admin")
def teacher_account(teacher_id):
    with database() as db:
        teacher = db.execute("""
            SELECT
                u.id,
                u.name,
                u.email,
                u.active,
                COALESCE(p.phone, '') AS phone,
                COALESCE(p.department, '') AS department,
                COALESCE(p.designation, 'Teacher') AS designation
            FROM users u
            LEFT JOIN teacher_profiles p
                ON p.user_id = u.id
            WHERE u.id = ?
              AND u.role = 'teacher'
        """, (teacher_id,)).fetchone()

    if teacher is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "admin/teacher_account.html",
            teacher=teacher,
        )

    try:
        name, email = identity()
    except ValueError as error:
        return jsonify(
            ok=False,
            message=str(error),
        ), 400

    fields = [
        request.form.get(key, "").strip()
        for key in (
            "phone",
            "department",
            "designation",
        )
    ]

    if any(len(value) > 150 for value in fields):
        return jsonify(
            ok=False,
            message=(
                "Phone, department and designation "
                "must be within 150 characters."
            ),
        ), 400

    active = request.form.get("active", "")

    if active not in ("0", "1"):
        return jsonify(
            ok=False,
            message="Choose a valid account status.",
        ), 400

    try:
        with database() as db:
            existing = db.execute("""
                SELECT 1
                FROM users
                WHERE lower(email) = ?
                  AND id <> ?
            """, (email, teacher_id)).fetchone()

            if existing:
                return jsonify(
                    ok=False,
                    message="This email is already in use.",
                ), 409

            db.execute("""
                UPDATE users
                SET name = ?,
                    email = ?,
                    active = ?
                WHERE id = ?
                  AND role = 'teacher'
            """, (
                name,
                email,
                int(active),
                teacher_id,
            ))

            db.execute("""
                INSERT INTO teacher_profiles(
                    user_id,
                    phone,
                    department,
                    designation
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    phone = excluded.phone,
                    department = excluded.department,
                    designation = excluded.designation
            """, (teacher_id, *fields))

    except sqlite3.IntegrityError:
        return jsonify(
            ok=False,
            message=(
                "Could not update account. "
                "Check the email and try again."
            ),
        ), 409

    return jsonify(
        ok=True,
        message="Teacher account updated successfully.",
        name=name,
        email=email,
    )


@bp.post(
    "/teacher-details/<int:teacher_id>/reset-password"
)
@require("admin")
def reset_teacher_password(teacher_id):
    error = password_error()

    if error:
        return jsonify(ok=False, message=error), 400

    hashed = generate_password_hash(
        request.form["new_password"]
    )

    with database() as db:
        result = db.execute("""
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
              AND role = 'teacher'
        """, (hashed, teacher_id))

        if result.rowcount == 0:
            abort(404)

    return jsonify(
        ok=True,
        message="Teacher password reset successfully.",
    )