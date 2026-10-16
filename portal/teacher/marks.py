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
from ..common import database, require, roster, score


@bp.route("/marks", methods=["GET", "POST"])
@require("teacher")
def marks():
    source = (
        request.form
        if request.method == "POST"
        else request.args
    )

    selected = source.get("class_id", "").strip()

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

        if request.method == "POST":
            if classroom is None:
                abort(400)

            try:
                student_id = int(
                    request.form.get("student_id", "")
                )
            except (TypeError, ValueError):
                abort(400)

            enrolled = db.execute(
                """
                SELECT 1
                FROM teacher_enrolments e
                JOIN users u ON u.id = e.student_id
                WHERE e.class_id = ?
                  AND e.student_id = ?
                  AND u.role = 'student'
                  AND u.active = 1
                """,
                (classroom["id"], student_id),
            ).fetchone()

            if enrolled is None:
                abort(403)

            try:
                values = [
                    score(
                        request.form.get(key),
                        classroom[key + "_max"],
                    )
                    for key in ("assessment", "mid", "final")
                ]

            except ValueError as error:
                flash(str(error), "danger")

            else:
                db.execute(
                    """
                    INSERT INTO teacher_marks(
                        class_id,
                        student_id,
                        assessment,
                        mid,
                        final
                    )
                    VALUES (?, ?, ?, ?, ?)

                    ON CONFLICT(class_id, student_id)
                    DO UPDATE SET
                        assessment = excluded.assessment,
                        mid = excluded.mid,
                        final = excluded.final
                    """,
                    (
                        classroom["id"],
                        student_id,
                        *values,
                    ),
                )

                flash("Marks saved successfully.", "success")

            return redirect(
                url_for(
                    "teacher.marks",
                    class_id=classroom["id"],
                ),
                code=303,
            )

        if classroom is not None:
            student_rows = roster(db, classroom)

    return render_template(
        "teacher/marks.html",
        classes=classes,
        classroom=classroom,
        students=student_rows,
    )