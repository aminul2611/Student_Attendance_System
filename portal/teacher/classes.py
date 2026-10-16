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


@bp.route("/classes", methods=["GET", "POST"])
@require("teacher")
def classes():
    source = (
        request.form
        if request.method == "POST"
        else request.args
    )

    selected = source.get("class_id", "").strip()
    classroom = None
    lessons = []

    form_values = {
        "lesson_date": today(),
        "start_time": "",
        "end_time": "",
        "room": "",
        "topic": "",
    }

    with database() as db:
        class_rows = db.execute(
            """
            SELECT *
            FROM teacher_classes
            WHERE teacher_id = ?
              AND teacher_removed = 0
            ORDER BY code
            """,
            (g.user["id"],),
        ).fetchall()

        if selected:
            try:
                class_id = int(selected)
            except ValueError:
                abort(404)

            classroom = next(
                (
                    row for row in class_rows
                    if row["id"] == class_id
                ),
                None,
            )

            if classroom is None:
                abort(404)

        if request.method == "POST":
            if classroom is None:
                abort(400, description="Select a class first.")

            form_values = {
                key: request.form.get(key, "").strip()
                for key in form_values
            }

            try:
                try:
                    day = date.fromisoformat(
                        form_values["lesson_date"]
                    ).isoformat()

                    start = datetime.strptime(
                        form_values["start_time"], "%H:%M"
                    ).strftime("%H:%M")

                    end = datetime.strptime(
                        form_values["end_time"], "%H:%M"
                    ).strftime("%H:%M")

                except ValueError:
                    raise ValueError(
                        "Enter a valid date, start time and end time."
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

                # Acquire the SQLite write lock before checking
                # and inserting, to prevent overlapping requests.
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
                    JOIN teacher_classes c ON c.id = l.class_id
                    WHERE c.teacher_id = ?
                      AND l.lesson_date = ?
                      AND l.start_time < ?
                      AND l.end_time > ?
                    """,
                    (g.user["id"], day, end, start),
                ).fetchone()

                if overlap:
                    raise ValueError(
                        "This time overlaps another class "
                        "in your schedule."
                    )

            except ValueError as error:
                flash(str(error), "danger")

            else:
                db.execute(
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
                        day,
                        start,
                        end,
                        form_values["room"],
                        form_values["topic"],
                    ),
                )

                flash("Class session scheduled.", "success")

                return redirect(
                    url_for(
                        "teacher.classes",
                        class_id=classroom["id"],
                        _anchor="tc-session-workspace",
                    ),
                    code=303,
                )

        if classroom is not None:
            lessons = db.execute(
                """
                SELECT *
                FROM teacher_lessons
                WHERE class_id = ?
                ORDER BY lesson_date DESC, start_time
                """,
                (classroom["id"],),
            ).fetchall()

    return render_template(
        "teacher/classes.html",
        classes=class_rows,
        classroom=classroom,
        lessons=lessons,
        form_values=form_values,
    )