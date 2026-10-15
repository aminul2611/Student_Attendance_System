import time

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
from ..common import (
    database,
    require,
    class_context,
    today,
)


@bp.route("/attendance", methods=["GET", "POST"])
@require("teacher")
def attendance():
    with database() as db:
        classes, classroom = class_context(db)

        lessons = []

        if classroom:
            lessons = db.execute(
                """
                SELECT * FROM teacher_lessons
                WHERE class_id=?
                ORDER BY lesson_date DESC, start_time DESC
                """,
                (classroom["id"],),
            ).fetchall()

        selected = request.values.get("lesson_id") or (
            lessons[0]["id"] if lessons else None
        )

        lesson = next(
            (
                row for row in lessons
                if str(row["id"]) == str(selected)
            ),
            None,
        )

        if selected and not lesson:
            abort(404)

        if request.method == "POST":
            if not lesson or lesson["lesson_date"] > today():
                abort(
                    400,
                    description=(
                        "Select a class held today or earlier."
                    ),
                )

            student_id = request.form.get("student_id")
            status = request.form.get("status")

            if status not in (
                "Present", "Absent", "Late", "Excused"
            ):
                abort(400)

            enrolled = db.execute(
                """
                SELECT 1
                FROM teacher_enrolments e
                JOIN users u ON u.id=e.student_id
                WHERE e.class_id=?
                  AND e.student_id=?
                  AND e.joined_on<=?
                  AND u.active=1
                """,
                (
                    classroom["id"],
                    student_id,
                    lesson["lesson_date"],
                ),
            ).fetchone()

            if not enrolled:
                abort(403)

            db.execute(
                """
                INSERT INTO teacher_student_attendance
                VALUES(?,?,?)
                ON CONFLICT(lesson_id,student_id)
                DO UPDATE SET status=excluded.status
                """,
                (lesson["id"], student_id, status),
            )

            flash("Student attendance saved.", "success")

            return redirect(
                url_for(
                    "teacher.attendance",
                    class_id=classroom["id"],
                    lesson_id=lesson["id"],
                )
            )

        students = []

        if lesson:
            students = db.execute(
                """
                SELECT u.id, u.name, u.student_no, a.status
                FROM teacher_enrolments e
                JOIN users u ON u.id=e.student_id
                LEFT JOIN teacher_student_attendance a
                    ON a.student_id=u.id AND a.lesson_id=?
                WHERE e.class_id=?
                  AND e.joined_on<=?
                  AND u.active=1
                ORDER BY u.name
                """,
                (
                    lesson["id"],
                    classroom["id"],
                    lesson["lesson_date"],
                ),
            ).fetchall()

        return render_template(
            "teacher/attendance.html",
            classes=classes,
            classroom=classroom,
            lessons=lessons,
            lesson=lesson,
            students=students,
        )


@bp.route("/my-attendance", methods=["GET", "POST"])
@require("teacher")
def my_attendance():
    with database() as db:
        row = db.execute(
            """
            SELECT * FROM teacher_work_attendance
            WHERE teacher_id=? AND work_date=?
            """,
            (g.user["id"], today()),
        ).fetchone()

        if request.method == "POST":
            action = request.form.get("action")

            if action not in ("in", "out"):
                abort(400)

            if action == "in":
                db.execute(
                    """
                    INSERT OR IGNORE INTO teacher_work_attendance(
                        teacher_id, work_date, check_in
                    )
                    VALUES(?,?,?)
                    """,
                    (
                        g.user["id"],
                        today(),
                        int(time.time()),
                    ),
                )

            elif row and row["check_out"] is None:
                db.execute(
                    """
                    UPDATE teacher_work_attendance
                    SET check_out=?
                    WHERE teacher_id=?
                      AND work_date=?
                      AND check_out IS NULL
                    """,
                    (
                        int(time.time()),
                        g.user["id"],
                        today(),
                    ),
                )

            else:
                flash(
                    "Check in first. A completed check-out "
                    "cannot be repeated.",
                    "warning",
                )

            return redirect(
                url_for("teacher.my_attendance")
            )

        history = db.execute(
            """
            SELECT * FROM teacher_work_attendance
            WHERE teacher_id=?
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