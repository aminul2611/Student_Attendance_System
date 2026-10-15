from flask import Blueprint


bp = Blueprint(
    "admin_portal",
    __name__,
    url_prefix="/admin",
)

from . import (
    teacher_attendance,
    dashboard,
    notices,
    profile,
)