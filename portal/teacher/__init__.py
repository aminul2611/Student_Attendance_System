from flask import Blueprint


bp = Blueprint(
    "teacher",
    __name__,
    url_prefix="/teacher",
)

from . import (
    dashboard,
    students,
    marks,
    classes,
    attendance,
    profile,
    calendar_page,
)