from flask import abort, g, render_template, request

from . import bp
from ..common import database, require, roster


@bp.get("/students")
@require("teacher")
def students():
    selected = request.args.get("class_id", "").strip()
    classroom = None
    student_rows = []

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

        if selected:
            try:
                class_id = int(selected)
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

            student_rows = roster(db, classroom)

    return render_template(
        "teacher/students.html",
        classes=classes,
        classroom=classroom,
        students=student_rows,
    )