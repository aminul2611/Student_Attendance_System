from flask import render_template

from . import bp
from ..common import (
    database,
    require,
    class_context,
    roster,
)


@bp.get("/students")
@require("teacher")
def students():
    with database() as db:
        classes, classroom = class_context(db)

        return render_template(
            "teacher/students.html",
            classes=classes,
            classroom=classroom,
            students=roster(db, classroom),
        )