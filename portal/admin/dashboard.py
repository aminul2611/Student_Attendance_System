import csv
import io

from flask import make_response, render_template

from . import bp
from .analytics import dashboard_data

from ..common import database, require


@bp.get("/")
@require("admin")
def dashboard():
    with database() as db:
        data = dashboard_data(db)

    return render_template(
        "admin/dashboard.html",
        **data,
    )


@bp.get("/attendance-summary.csv")
@require("admin")
def attendance_summary():
    with database() as db:
        graph = dashboard_data(db)["graphs"]

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        ["Date"]
        + graph["statuses"]
        + [
            "Teacher check-ins",
            "Teacher check-outs",
        ]
    )

    for day in graph["days"]:
        writer.writerow(
            [day]
            + [
                graph["student"][day][status]
                for status in graph["statuses"]
            ]
            + [
                graph["teacher"][day]["ins"],
                graph["teacher"][day]["outs"],
            ]
        )

    response = make_response(
        "\ufeff" + output.getvalue()
    )

    response.headers["Content-Type"] = (
        "text/csv; charset=utf-8"
    )

    response.headers["Content-Disposition"] = (
        "attachment; filename=attendance-summary.csv"
    )

    return response