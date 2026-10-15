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
from ..common import database, require, class_context


@bp.route("/classes", methods=["GET", "POST"])
@require("teacher")
def classes():
    with database() as db:
        class_rows, classroom = class_context(db)

        if request.method == "POST":
            if not classroom:
                abort(404)

            try:
                day = date.fromisoformat(
                    request.form.get("lesson_date", "")
                ).isoformat()

                start = datetime.strptime(
                    request.form.get("start_time", ""),
                    "%H:%M",
                ).strftime("%H:%M")

                end = datetime.strptime(
                    request.form.get("end_time", ""),
                    "%H:%M",
                ).strftime("%H:%M")

                if end <= start:
                    raise ValueError(
                        "End time must be after start time."
                    )

                overlap = db.execute(
                    """
                    SELECT 1
                    FROM teacher_lessons l
                    JOIN teacher_classes c ON c.id=l.class_id
                    WHERE c.teacher_id=?
                      AND l.lesson_date=?
                      AND l.start_time<?
                      AND l.end_time>?
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
                        class_id, lesson_date,
                        start_time, end_time, room, topic
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        classroom["id"],
                        day,
                        start,
                        end,
                        request.form.get("room", "").strip(),
                        request.form.get("topic", "").strip(),
                    ),
                )

                flash("Class scheduled.", "success")

            return redirect(
                url_for(
                    "teacher.classes",
                    class_id=classroom["id"],
                )
            )

        lessons = []

        if classroom:
            lessons = db.execute(
                """
                SELECT * FROM teacher_lessons
                WHERE class_id=?
                ORDER BY lesson_date DESC, start_time
                """,
                (classroom["id"],),
            ).fetchall()

        return render_template(
            "teacher/classes.html",
            classes=class_rows,
            classroom=classroom,
            lessons=lessons,
        )