import sqlite3
from datetime import date, datetime

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from . import bp
from ..common import database, require


@bp.route(
    "/teacher-details/<int:teacher_id>/teaching",
    methods=["GET", "POST"],
)
@require("admin")
def teacher_teaching(teacher_id):
    with database() as db:
        teacher = db.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE id = ? AND role = 'teacher'
            """,
            (teacher_id,),
        ).fetchone()

        if teacher is None:
            abort(404)

        if request.method == "POST":
            try:
                action = request.form.get("action", "")

                if action == "assign_class":
                    code = request.form.get("code", "").strip()
                    name = request.form.get("name", "").strip()

                    if not code or not name:
                        raise ValueError(
                            "Class code and class name are required."
                        )

                    if len(code) > 80 or len(name) > 150:
                        raise ValueError(
                            "Class code: maximum 80 characters. "
                            "Class name: maximum 150 characters."
                        )

                    db.execute(
                        """
                        INSERT INTO teacher_classes(
                            code, name, teacher_id
                        )
                        VALUES (?, ?, ?)
                        """,
                        (code, name, teacher_id),
                    )

                    flash("Class assigned successfully.", "success")

                elif action == "schedule":
                    try:
                        class_id = int(
                            request.form.get("class_id", "")
                        )
                    except (TypeError, ValueError):
                        raise ValueError("Choose a valid class.")

                    classroom = db.execute(
                        """
                        SELECT id
                        FROM teacher_classes
                        WHERE id = ? AND teacher_id = ?
                        """,
                        (class_id, teacher_id),
                    ).fetchone()

                    if classroom is None:
                        raise ValueError(
                            "Choose a class assigned to this teacher."
                        )

                    try:
                        lesson_date = date.fromisoformat(
                            request.form.get("lesson_date", "")
                        ).isoformat()

                        start_time = datetime.strptime(
                            request.form.get("start_time", ""),
                            "%H:%M",
                        ).strftime("%H:%M")

                        end_time = datetime.strptime(
                            request.form.get("end_time", ""),
                            "%H:%M",
                        ).strftime("%H:%M")

                    except ValueError:
                        raise ValueError(
                            "Enter a valid date, start time and end time."
                        )

                    if end_time <= start_time:
                        raise ValueError(
                            "End time must be after start time."
                        )

                    room = request.form.get("room", "").strip()
                    topic = request.form.get("topic", "").strip()

                    if len(room) > 100 or len(topic) > 300:
                        raise ValueError(
                            "Room: maximum 100 characters. "
                            "Topic: maximum 300 characters."
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
                            teacher_id,
                            lesson_date,
                            end_time,
                            start_time,
                        ),
                    ).fetchone()

                    if overlap:
                        raise ValueError(
                            "This teacher already has a class "
                            "during this time."
                        )

                    if room:
                        room_busy = db.execute(
                            """
                            SELECT 1
                            FROM teacher_lessons
                            WHERE lesson_date = ?
                              AND lower(trim(room)) = lower(?)
                              AND start_time < ?
                              AND end_time > ?
                            """,
                            (
                                lesson_date,
                                room,
                                end_time,
                                start_time,
                            ),
                        ).fetchone()

                        if room_busy:
                            raise ValueError(
                                "This room is already booked "
                                "during this time."
                            )

                    db.execute(
                        """
                        INSERT INTO teacher_lessons(
                            class_id, lesson_date,
                            start_time, end_time, room, topic
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            class_id,
                            lesson_date,
                            start_time,
                            end_time,
                            room,
                            topic,
                        ),
                    )

                    flash("Class scheduled successfully.", "success")

                else:
                    raise ValueError("Invalid action.")

            except ValueError as error:
                flash(str(error), "danger")

            except sqlite3.IntegrityError:
                flash(
                    "Could not save. Class codes must be unique.",
                    "danger",
                )

            return redirect(
                url_for(
                    "admin_portal.teacher_teaching",
                    teacher_id=teacher_id,
                )
            )

        classes = db.execute(
            """
            SELECT id, code, name
            FROM teacher_classes
            WHERE teacher_id = ?
            ORDER BY name, code
            """,
            (teacher_id,),
        ).fetchall()

        lessons = db.execute(
            """
            SELECT
                l.lesson_date,
                l.start_time,
                l.end_time,
                l.room,
                l.topic,
                c.code,
                c.name
            FROM teacher_lessons l
            JOIN teacher_classes c ON c.id = l.class_id
            WHERE c.teacher_id = ?
            ORDER BY l.lesson_date DESC, l.start_time
            """,
            (teacher_id,),
        ).fetchall()

        return render_template(
            "admin/teacher_teaching.html",
            teacher=teacher,
            classes=classes,
            lessons=lessons,
        )