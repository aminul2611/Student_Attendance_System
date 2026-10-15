from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from . import bp
from ..common import (
    database,
    require,
    class_context,
    roster,
    score,
)


@bp.route("/marks", methods=["GET", "POST"])
@require("teacher")
def marks():
    with database() as db:
        classes, classroom = class_context(db)

        if request.method == "POST":
            if not classroom:
                abort(404)

            student_id = request.form.get("student_id")

            enrolled = db.execute(
                """
                SELECT 1
                FROM teacher_enrolments e
                JOIN users u ON u.id=e.student_id
                WHERE e.class_id=?
                  AND e.student_id=?
                  AND u.active=1
                """,
                (classroom["id"], student_id),
            ).fetchone()

            if not enrolled:
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
                    INSERT INTO teacher_marks
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(class_id,student_id)
                    DO UPDATE SET
                        assessment=excluded.assessment,
                        mid=excluded.mid,
                        final=excluded.final
                    """,
                    (
                        classroom["id"],
                        student_id,
                        *values,
                    ),
                )

                flash("Marks saved.", "success")

            return redirect(
                url_for(
                    "teacher.marks",
                    class_id=classroom["id"],
                )
            )

        return render_template(
            "teacher/marks.html",
            classes=classes,
            classroom=classroom,
            students=roster(db, classroom),
        )