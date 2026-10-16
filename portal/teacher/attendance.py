import time
from datetime import date, datetime

from flask import (
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from . import bp
from ..common import database, require, today


@bp.route("/attendance", methods=["GET", "POST"])
@require("teacher")
def attendance():
    current_day = today()

    source = (
        request.form
        if request.method == "POST"
        else request.args
    )

    selected_class = source.get("class_id", "").strip()
    selected_lesson = source.get("lesson_id", "").strip()

    try:
        attendance_date = date.fromisoformat(
            source.get("attendance_date") or current_day
        ).isoformat()
    except ValueError:
        abort(
            400,
            description="Enter a valid attendance date.",
        )

    classroom = None
    lesson = None
    lessons = []
    students = []

    form_values = {
        "start_time": "",
        "end_time": "",
        "room": "",
        "topic": "",
    }

    with database() as db:
        classes = db.execute(
            """
            SELECT *
            FROM teacher_classes
            WHERE teacher_id = ?
              AND teacher_removed = 0
            ORDER BY code
            """,
            (g.user["id"],),
        ).fetchall()

        if selected_class:
            try:
                class_id = int(selected_class)
            except ValueError:
                abort(404)

            classroom = next(
                (
                    row
                    for row in classes
                    if row["id"] == class_id
                ),
                None,
            )

            if classroom is None:
                abort(404)

        if classroom is not None:
            # Support attendance links from Daily Classes
            # and the Dashboard.
            if selected_lesson:
                try:
                    lesson_id = int(selected_lesson)
                except ValueError:
                    abort(404)

                lesson = db.execute(
                    """
                    SELECT *
                    FROM teacher_lessons
                    WHERE id = ?
                      AND class_id = ?
                    """,
                    (lesson_id, classroom["id"]),
                ).fetchone()

                if lesson is None:
                    abort(404)

                attendance_date = lesson["lesson_date"]

            lessons = db.execute(
                """
                SELECT *
                FROM teacher_lessons
                WHERE class_id = ?
                  AND lesson_date = ?
                ORDER BY start_time, id
                """,
                (classroom["id"], attendance_date),
            ).fetchall()

            # Automatically select the only available session.
            if lesson is None and len(lessons) == 1:
                lesson = lessons[0]

        elif selected_lesson:
            abort(404)

        if request.method == "POST":
            if classroom is None:
                abort(
                    400,
                    description="Select a class first.",
                )

            action = request.form.get("action", "")

            if action == "create_session":
                form_values = {
                    key: request.form.get(key, "").strip()
                    for key in form_values
                }

                try:
                    if attendance_date > current_day:
                        raise ValueError(
                            "Attendance sessions must be "
                            "today or earlier."
                        )

                    try:
                        start = datetime.strptime(
                            form_values["start_time"],
                            "%H:%M",
                        ).strftime("%H:%M")

                        end = datetime.strptime(
                            form_values["end_time"],
                            "%H:%M",
                        ).strftime("%H:%M")

                    except ValueError:
                        raise ValueError(
                            "Enter a valid start time "
                            "and end time."
                        )

                    if end <= start:
                        raise ValueError(
                            "End time must be after start time."
                        )

                    if len(form_values["room"]) > 100:
                        raise ValueError(
                            "Room must be within 100 characters."
                        )

                    if len(form_values["topic"]) > 200:
                        raise ValueError(
                            "Topic must be within 200 characters."
                        )

                    # Lock before checking and inserting
                    # to prevent concurrent overlapping sessions.
                    db.execute(
                        """
                        UPDATE teacher_classes
                        SET name = name
                        WHERE id = ?
                        """,
                        (classroom["id"],),
                    )

                    overlap = db.execute(
                        """
                        SELECT 1
                        FROM teacher_lessons l
                        JOIN teacher_classes c
                            ON c.id = l.class_id
                        WHERE c.teacher_id = ?
                          AND l.lesson_date = ?
                          AND l.start_time < ?
                          AND l.end_time > ?
                        """,
                        (
                            g.user["id"],
                            attendance_date,
                            end,
                            start,
                        ),
                    ).fetchone()

                    if overlap:
                        raise ValueError(
                            "This time overlaps another "
                            "class in your schedule."
                        )

                except ValueError as error:
                    flash(str(error), "danger")

                else:
                    new_lesson_id = db.execute(
                        """
                        INSERT INTO teacher_lessons(
                            class_id,
                            lesson_date,
                            start_time,
                            end_time,
                            room,
                            topic
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            classroom["id"],
                            attendance_date,
                            start,
                            end,
                            form_values["room"],
                            form_values["topic"],
                        ),
                    ).lastrowid

                    flash(
                        "Session created. "
                        "You can now mark attendance.",
                        "success",
                    )

                    return redirect(
                        url_for(
                            "teacher.attendance",
                            class_id=classroom["id"],
                            attendance_date=attendance_date,
                            lesson_id=new_lesson_id,
                        ),
                        code=303,
                    )

            elif action == "save_attendance":
                if lesson is None:
                    abort(
                        400,
                        description="Select a session first.",
                    )

                if lesson["lesson_date"] > current_day:
                    abort(
                        400,
                        description=(
                            "Future attendance cannot be recorded."
                        ),
                    )

                try:
                    student_id = int(
                        request.form.get("student_id", "")
                    )
                except (TypeError, ValueError):
                    abort(400)

                status = request.form.get("status", "")

                if status not in (
                    "Present",
                    "Absent",
                    "Late",
                    "Excused",
                ):
                    abort(
                        400,
                        description="Select a valid status.",
                    )

                enrolled = db.execute(
                    """
                    SELECT 1
                    FROM teacher_enrolments e
                    JOIN users u ON u.id = e.student_id
                    WHERE e.class_id = ?
                      AND e.student_id = ?
                      AND e.joined_on <= ?
                      AND u.role = 'student'
                      AND u.active = 1
                    """,
                    (
                        classroom["id"],
                        student_id,
                        lesson["lesson_date"],
                    ),
                ).fetchone()

                if enrolled is None:
                    abort(403)

                db.execute(
                    """
                    INSERT INTO teacher_student_attendance(
                        lesson_id,
                        student_id,
                        status
                    )
                    VALUES (?, ?, ?)

                    ON CONFLICT(lesson_id, student_id)
                    DO UPDATE SET
                        status = excluded.status
                    """,
                    (
                        lesson["id"],
                        student_id,
                        status,
                    ),
                )

                flash(
                    "Student attendance saved.",
                    "success",
                )

                return redirect(
                    url_for(
                        "teacher.attendance",
                        class_id=classroom["id"],
                        attendance_date=attendance_date,
                        lesson_id=lesson["id"],
                    ),
                    code=303,
                )

            else:
                abort(
                    400,
                    description="Invalid action.",
                )

        # Show eligible students after choosing a class,
        # even if a session has not yet been created.
        if classroom is not None:
            students = db.execute(
                """
                SELECT
                    u.id,
                    u.name,
                    u.student_no,
                    a.status
                FROM teacher_enrolments e
                JOIN users u ON u.id = e.student_id

                LEFT JOIN teacher_student_attendance a
                    ON a.student_id = u.id
                   AND a.lesson_id = ?

                WHERE e.class_id = ?
                  AND e.joined_on <= ?
                  AND u.role = 'student'
                  AND u.active = 1

                ORDER BY u.name
                """,
                (
                    lesson["id"] if lesson is not None else None,
                    classroom["id"],
                    attendance_date,
                ),
            ).fetchall()

    return render_template(
        "teacher/attendance.html",
        classes=classes,
        classroom=classroom,
        lessons=lessons,
        lesson=lesson,
        students=students,
        attendance_date=attendance_date,
        attendance_today=current_day,
        form_values=form_values,
    )


@bp.route("/my-attendance", methods=["GET", "POST"])
@require("teacher")
def my_attendance():
    current_day = today()

    with database() as db:
        row = db.execute(
            """
            SELECT *
            FROM teacher_work_attendance
            WHERE teacher_id = ?
              AND work_date = ?
            """,
            (g.user["id"], current_day),
        ).fetchone()

        if request.method == "POST":
            action = request.form.get("action", "")

            if action not in ("in", "out"):
                abort(400)

            if action == "in":
                db.execute(
                    """
                    INSERT OR IGNORE INTO teacher_work_attendance(
                        teacher_id,
                        work_date,
                        check_in
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        g.user["id"],
                        current_day,
                        int(time.time()),
                    ),
                )

            elif row is not None and row["check_out"] is None:
                db.execute(
                    """
                    UPDATE teacher_work_attendance
                    SET check_out = ?
                    WHERE teacher_id = ?
                      AND work_date = ?
                      AND check_out IS NULL
                    """,
                    (
                        int(time.time()),
                        g.user["id"],
                        current_day,
                    ),
                )

            else:
                flash(
                    "Check in first. A completed check-out "
                    "cannot be repeated.",
                    "warning",
                )

            return redirect(
                url_for("teacher.my_attendance"),
                code=303,
            )

        history = db.execute(
            """
            SELECT *
            FROM teacher_work_attendance
            WHERE teacher_id = ?
            ORDER BY work_date DESC
            LIMIT 60
            """,
            (g.user["id"],),
        ).fetchall()

    return render_template(
        "teacher/my_attendance.html",
        record=row,
        history=history,
    )