from flask import g, render_template

from . import bp
from ..common import database, require, today


@bp.get("/")
@require("teacher")
def dashboard():
    with database() as db:
        classes = db.execute(
            """
            SELECT * FROM teacher_classes
            WHERE teacher_id=?
            ORDER BY code
            """,
            (g.user["id"],),
        ).fetchall()

        daily = db.execute(
            """
            SELECT l.*, c.name, c.code
            FROM teacher_lessons l
            JOIN teacher_classes c ON c.id=l.class_id
            WHERE c.teacher_id=? AND l.lesson_date=?
            ORDER BY l.start_time
            """,
            (g.user["id"], today()),
        ).fetchall()

        return render_template(
            "teacher/dashboard.html",
            classes=classes,
            daily=daily,
        )