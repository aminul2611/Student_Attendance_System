from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from .common import database, require, today


bp = Blueprint(
    "student_portal",
    __name__,
    url_prefix="/student",
)

SECTIONS = {
    "dashboard": "Dashboard",
    "classes": "My Classes",
    "tasks": "Tasks",
    "attendance": "My Attendance",
    "results": "My Results",
    "notices": "My Notices",
    "profile": "My Profile",
}

MENU = (
    ("dashboard", "Dashboard", "▦"),
    ("classes", "My Classes", "▤"),
    ("tasks", "Tasks", "✓"),
    ("attendance", "My Attendance", "◷"),
    ("results", "My Results", "↗"),
    ("notices", "My Notices", "▧"),
    ("profile", "My Profile", "◎"),
)


def get_classes(db, student_id):
    rows = db.execute(
        """
        SELECT
            c.id,
            c.code,
            c.name,
            c.class_time,
            c.teacher_removed,
            c.setup_removed,
            c.assessment_max,
            c.mid_max,
            c.final_max,
            e.joined_on,
            u.name AS teacher_name,
            m.assessment,
            m.mid,
            m.final,
            COALESCE(
                NULLIF(TRIM(t.semester), ''),
                NULLIF(TRIM(c.semester), ''),
                'Semester not assigned'
            ) AS semester

        FROM teacher_enrolments e

        JOIN teacher_classes c
            ON c.id=e.class_id

        LEFT JOIN users u
            ON u.id=c.teacher_id

        LEFT JOIN teacher_marks m
            ON m.class_id=e.class_id
            AND m.student_id=e.student_id

        LEFT JOIN student_enrolment_terms t
            ON t.class_id=e.class_id
            AND t.student_id=e.student_id

        WHERE e.student_id=?

        ORDER BY semester, c.code, c.id
        """,
        (student_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def get_attendance(db, student_id):
    return db.execute(
        """
        SELECT
            l.id,
            l.lesson_date,
            l.start_time,
            l.end_time,
            l.room,
            l.topic,
            c.id AS class_id,
            c.code,
            c.name,
            a.status

        FROM teacher_enrolments e

        JOIN teacher_classes c
            ON c.id=e.class_id

        JOIN teacher_lessons l
            ON l.class_id=e.class_id

        LEFT JOIN teacher_student_attendance a
            ON a.lesson_id=l.id
            AND a.student_id=e.student_id

        WHERE e.student_id=?
          AND l.lesson_date>=e.joined_on
          AND l.lesson_date<=?

        ORDER BY
            l.lesson_date DESC,
            l.start_time DESC,
            l.id DESC
        """,
        (student_id, today()),
    ).fetchall()


def get_notices(db, student_id):
    return db.execute(
        """
        SELECT
            n.id,
            n.title,
            n.body,
            n.created_at,
            COALESCE(u.name, 'Campus') AS author,
            COALESCE(u.role, '') AS author_role

        FROM admin_notices n

        JOIN admin_notice_recipients r
            ON r.notice_id=n.id

        LEFT JOIN users u
            ON u.id=n.created_by

        WHERE r.user_id=?
          AND n.active=1

        ORDER BY n.created_at DESC, n.id DESC
        """,
        (student_id,),
    ).fetchall()


def handle_post(db, section, student_id):
    action = request.form.get("action", "")

    if section == "tasks" and action == "task_status":
        task_id = request.form.get("task_id", type=int)
        status = request.form.get("status", "")

        if status not in (
            "Pending",
            "In Progress",
            "Completed",
        ):
            abort(400)

        changed = db.execute(
            """
            UPDATE tasks
            SET status=?
            WHERE id=?
              AND assigned_to=?
            """,
            (status, task_id, student_id),
        ).rowcount

        if not changed:
            abort(404)

        flash("Task status updated successfully.", "success")
        return None

    if section != "profile":
        abort(400)

    if action == "profile":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not 1 <= len(name) <= 100:
            flash(
                "Name must contain 1–100 characters.",
                "danger",
            )
            return None

        if len(phone) > 150:
            flash(
                "Phone must be within 150 characters.",
                "danger",
            )
            return None

        db.execute(
            """
            UPDATE users
            SET name=?
            WHERE id=? AND role='student'
            """,
            (name, student_id),
        )

        db.execute(
            """
            INSERT INTO student_profiles(user_id, phone)
            VALUES(?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET phone=excluded.phone
            """,
            (student_id, phone),
        )

        flash("Profile updated successfully.", "success")
        return None

    if action == "password":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")

        user = db.execute(
            """
            SELECT password_hash
            FROM users
            WHERE id=? AND role='student'
            """,
            (student_id,),
        ).fetchone()

        if not user:
            abort(404)

        if not check_password_hash(
            user["password_hash"], current
        ):
            flash("Current password is incorrect.", "danger")
            return None

        if not 8 <= len(new) <= 128:
            flash(
                "New password must contain 8–128 characters.",
                "danger",
            )
            return None

        if new != confirmation:
            flash("New passwords do not match.", "danger")
            return None

        db.execute(
            """
            UPDATE users
            SET password_hash=?
            WHERE id=? AND role='student'
            """,
            (generate_password_hash(new), student_id),
        )

        session.clear()

        flash(
            "Password changed successfully. "
            "Please log in with your new password.",
            "success",
        )

        return redirect(
            url_for("login", role="student"),
            code=303,
        )

    abort(400)


@bp.route("/<section>", methods=["GET", "POST"])
@require("student")
def page(section):
    if section not in SECTIONS:
        abort(404)

    student_id = g.user["id"]

    with database() as db:
        if request.method == "POST":
            response = handle_post(
                db, section, student_id
            )

            if response is not None:
                return response

            return redirect(
                url_for(
                    "student_portal.page",
                    section=section,
                ),
                code=303,
            )

        classes = get_classes(db, student_id)
        attendance = get_attendance(db, student_id)
        notices = get_notices(db, student_id)

        tasks = db.execute(
            """
            SELECT *
            FROM tasks
            WHERE assigned_to=?
            ORDER BY
                CASE WHEN status='Completed'
                    THEN 1 ELSE 0 END,
                COALESCE(due_date, '9999-12-31'),
                id DESC
            """,
            (student_id,),
        ).fetchall()

        details = db.execute(
            """
            SELECT phone, department
            FROM student_profiles
            WHERE user_id=?
            """,
            (student_id,),
        ).fetchone()

        daily = db.execute(
            """
            SELECT
                c.code,
                c.name,
                l.start_time,
                l.end_time,
                l.room,
                l.topic

            FROM teacher_enrolments e

            JOIN teacher_classes c
                ON c.id=e.class_id

            JOIN teacher_lessons l
                ON l.class_id=e.class_id

            WHERE e.student_id=?
              AND l.lesson_date=?
              AND e.joined_on<=l.lesson_date

            ORDER BY l.start_time, c.code
            """,
            (student_id, today()),
        ).fetchall()

    attendance_counts = {
        status: sum(
            row["status"] == status
            for row in attendance
        )
        for status in (
            "Present",
            "Absent",
            "Late",
            "Excused",
        )
    }

    attendance_counts["Not marked"] = sum(
        row["status"] is None
        for row in attendance
    )

    total_sessions = len(attendance)

    # Present and Late count as attended.
    attended = (
        attendance_counts["Present"]
        + attendance_counts["Late"]
    )

    percentage = (
        round(attended * 100 / total_sessions, 1)
        if total_sessions
        else 0
    )

    completed = sum(
        task["status"] == "Completed"
        for task in tasks
    )

    semesters = sorted({
        classroom["semester"]
        for classroom in classes
    })

    selected_semester = request.args.get(
        "semester", ""
    ).strip()

    visible_classes = [
        classroom
        for classroom in classes
        if not selected_semester
        or classroom["semester"] == selected_semester
    ]

    return render_template(
        "student/portal.html",
        section=section,
        section_title=SECTIONS[section],
        student_menu=MENU,
        classes=classes,
        visible_classes=visible_classes,
        semesters=semesters,
        selected_semester=selected_semester,
        attendance=attendance,
        attendance_counts=attendance_counts,
        attendance_percentage=percentage,
        tasks=tasks,
        completed=completed,
        notices=notices,
        details=details,
        daily=daily,
    )


def init_student_portal(app):
    app.register_blueprint(bp)

    @app.before_request
    def open_student_workspace():
        if (
            request.method == "GET"
            and getattr(g, "user", None)
            and g.user["role"] == "student"
        ):
            destinations = {
                "dashboard": "dashboard",
                "tasks": "tasks",
            }

            section = destinations.get(request.endpoint)

            if section:
                return redirect(
                    url_for(
                        "student_portal.page",
                        section=section,
                    )
                )