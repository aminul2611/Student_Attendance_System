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
from ..class_rules import remove_teacher_assignment


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
            action = request.form.get("action", "")
            class_id = request.form.get("class_id", type=int)

            try:
                if action != "remove_teacher_class":
                    raise ValueError("Invalid action.")

                remove_teacher_assignment(
                    db,
                    class_id,
                    teacher_id,
                )

                flash(
                    "Teacher assignment removed. "
                    "Student assignments and results are preserved.",
                    "success",
                )

            except ValueError as error:
                flash(str(error), "danger")

            return redirect(
                url_for(
                    "admin_portal.teacher_teaching",
                    teacher_id=teacher_id,
                ),
                code=303,
            )

        classes = db.execute(
            """
            SELECT
                id, code, name, semester, class_time
            FROM teacher_classes
            WHERE teacher_id = ?
              AND teacher_removed = 0
            ORDER BY semester, code
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
              AND c.teacher_removed = 0
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