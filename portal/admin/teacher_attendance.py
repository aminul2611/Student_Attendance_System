from datetime import date

from flask import abort, render_template, request

from . import bp
from ..common import database, require, today


@bp.get("/teacher-attendance")
@require("admin")
def teacher_attendance():
    selected = request.args.get("date", today())

    try:
        selected = date.fromisoformat(
            selected
        ).isoformat()
    except ValueError:
        abort(400, description="Choose a valid date.")

    with database() as db:
        rows = db.execute(
            """
            SELECT
                u.name,
                u.email,
                a.check_in,
                a.check_out
            FROM users u
            LEFT JOIN teacher_work_attendance a
                ON a.teacher_id=u.id
                AND a.work_date=?
            WHERE u.role='teacher'
            ORDER BY u.name
            """,
            (selected,),
        ).fetchall()

    return render_template(
        "admin/teacher_attendance.html",
        rows=rows,
        selected=selected,
    )