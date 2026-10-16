from datetime import datetime

from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from . import bp
from ..common import database, require


@bp.route("/notices", methods=["GET", "POST"])
@require("teacher")
def notices():
    teacher_id = g.user["id"]

    with database() as db:
        classes = db.execute(
            """
            SELECT id, code, name
            FROM teacher_classes
            WHERE teacher_id=?
              AND teacher_removed=0
            ORDER BY code
            """,
            (teacher_id,),
        ).fetchall()

        students = db.execute(
            """
            SELECT DISTINCT
                u.id,
                u.name,
                u.student_no

            FROM users u

            JOIN teacher_enrolments e
                ON e.student_id=u.id

            JOIN teacher_classes c
                ON c.id=e.class_id

            WHERE c.teacher_id=?
              AND c.teacher_removed=0
              AND u.role='student'
              AND u.active=1

            ORDER BY u.name
            """,
            (teacher_id,),
        ).fetchall()

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            audience = request.form.get("audience", "").strip()

            recipients = set()

            try:
                if not 1 <= len(title) <= 140:
                    raise ValueError(
                        "Enter a title using 1–140 characters."
                    )

                if not 1 <= len(body) <= 5000:
                    raise ValueError(
                        "Enter a message using 1–5000 characters."
                    )

                if audience == "admin":
                    recipients = {
                        row["id"]
                        for row in db.execute(
                            """
                            SELECT id
                            FROM users
                            WHERE role='admin'
                              AND active=1
                            """
                        )
                    }

                elif audience == "class":
                    try:
                        class_id = int(
                            request.form.get("class_id", "")
                        )
                    except (TypeError, ValueError):
                        raise ValueError(
                            "Select a valid class."
                        )

                    allowed_classes = {
                        classroom["id"]
                        for classroom in classes
                    }

                    if class_id not in allowed_classes:
                        raise ValueError(
                            "Select one of your assigned classes."
                        )

                    recipients = {
                        row["id"]
                        for row in db.execute(
                            """
                            SELECT u.id

                            FROM teacher_enrolments e

                            JOIN users u
                                ON u.id=e.student_id

                            WHERE e.class_id=?
                              AND u.role='student'
                              AND u.active=1
                            """,
                            (class_id,),
                        )
                    }

                elif audience == "students":
                    try:
                        recipients = {
                            int(value)
                            for value in request.form.getlist(
                                "student_ids"
                            )
                        }
                    except (TypeError, ValueError):
                        raise ValueError(
                            "Select valid students."
                        )

                    allowed_students = {
                        student["id"]
                        for student in students
                    }

                    if not recipients.issubset(allowed_students):
                        raise ValueError(
                            "Select students from your own classes."
                        )

                else:
                    raise ValueError(
                        "Choose who should receive this notice."
                    )
                if request.form.get("also_admin") == "1":
                    admin_ids = {
                        row["id"]
                        for row in db.execute(
                            """
                            SELECT id
                            FROM users
                            WHERE role='admin'
                              AND active=1
                            """
                        )
                    }

                    if not admin_ids:
                        raise ValueError(
                            "No active Admin account found."
                        )

                    recipients.update(admin_ids)

                if not recipients:
                    raise ValueError(
                        "No eligible recipients selected."
                    )

            except ValueError as error:
                flash(str(error), "danger")

            else:
                timezone = current_app.extensions[
                    "portal"
                ]["timezone"]

                timestamp = datetime.now(
                    timezone
                ).isoformat(timespec="seconds")

                notice_id = db.execute(
                    """
                    INSERT INTO admin_notices(
                        title,
                        body,
                        active,
                        created_by,
                        created_at,
                        updated_at
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        title,
                        body,
                        1,
                        teacher_id,
                        timestamp,
                        timestamp,
                    ),
                ).lastrowid

                db.executemany(
                    """
                    INSERT INTO admin_notice_recipients(
                        notice_id,
                        user_id
                    )
                    VALUES(?,?)
                    """,
                    [
                        (notice_id, user_id)
                        for user_id in recipients
                    ],
                )

                flash(
                    "Notice sent to selected recipients.",
                    "success",
                )

                return redirect(
                    url_for("teacher.notices"),
                    code=303,
                )

        received = db.execute(
            """
            SELECT
                n.id,
                n.title,
                n.body,
                n.created_at,
                u.name AS author

            FROM admin_notices n

            JOIN admin_notice_recipients r
                ON r.notice_id=n.id

            LEFT JOIN users u
                ON u.id=n.created_by

            WHERE r.user_id=?
              AND n.active=1

            ORDER BY n.created_at DESC, n.id DESC
            """,
            (teacher_id,),
        ).fetchall()

        sent = db.execute(
            """
            SELECT
                n.*,
                (
                    SELECT COUNT(*)
                    FROM admin_notice_recipients r
                    WHERE r.notice_id=n.id
                ) AS recipient_count

            FROM admin_notices n

            WHERE n.created_by=?

            ORDER BY n.created_at DESC, n.id DESC
            """,
            (teacher_id,),
        ).fetchall()

    return render_template(
        "teacher/notices.html",
        classes=classes,
        students=students,
        received=received,
        sent=sent,
    )