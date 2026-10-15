import calendar
from datetime import datetime

from flask import abort, g, render_template, request

from . import bp
from ..common import database, require, today


@bp.get("/calendar")
@require("teacher")
def calendar_page():
    month = request.args.get("month", today()[:7])

    try:
        first = datetime.strptime(
            month, "%Y-%m"
        ).date().replace(day=1)

        if not 1901 <= first.year <= 2099:
            raise ValueError()

    except ValueError:
        abort(
            400,
            description=(
                "Choose a valid month between 1901 and 2099."
            ),
        )

    days = list(
        calendar.Calendar().itermonthdates(
            first.year, first.month
        )
    )

    with database() as db:
        lessons = db.execute(
            """
            SELECT l.*, c.name, c.code
            FROM teacher_lessons l
            JOIN teacher_classes c ON c.id=l.class_id
            WHERE c.teacher_id=?
              AND l.lesson_date BETWEEN ? AND ?
            ORDER BY l.lesson_date, l.start_time
            """,
            (
                g.user["id"],
                days[0].isoformat(),
                days[-1].isoformat(),
            ),
        ).fetchall()

        return render_template(
            "teacher/calendar.html",
            month=month,
            days=days,
            month_number=first.month,
            lessons=lessons,
        )