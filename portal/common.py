import math
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import (
    abort,
    current_app,
    g,
    redirect,
    request,
    url_for,
)


@contextmanager
def database():
    db = current_app.extensions["portal"]["connect"]()

    try:
        with db:
            yield db
    finally:
        db.close()


def today():
    timezone = current_app.extensions["portal"]["timezone"]

    return datetime.now(
        timezone
    ).date().isoformat()


def require(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(
                    url_for(
                        "login",
                        role=role,
                        next=request.full_path,
                    )
                )

            if g.user["role"] != role:
                abort(403)

            return view(*args, **kwargs)

        return wrapped

    return decorator


def class_context(db):
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

    selected = request.values.get("class_id") or (
        classes[0]["id"] if classes else None
    )

    classroom = None

    if selected:
        classroom = db.execute(
            """
            SELECT *
            FROM teacher_classes
            WHERE id = ?
              AND teacher_id = ?
              AND teacher_removed = 0
            """,
            (
                selected,
                g.user["id"],
            ),
        ).fetchone()

        if classroom is None:
            abort(404)

    return classes, classroom


def roster(db, classroom):
    if not classroom:
        return []

    return db.execute(
        """
        SELECT
            u.id,
            u.name,
            u.email,
            u.student_no,
            u.created_at,
            u.active,
            m.assessment,
            m.mid,
            m.final
        FROM teacher_enrolments e
        JOIN users u
            ON u.id = e.student_id
        LEFT JOIN teacher_marks m
            ON m.class_id = e.class_id
            AND m.student_id = e.student_id
        WHERE e.class_id = ?
        ORDER BY u.name
        """,
        (classroom["id"],),
    ).fetchall()


def score(text, maximum):
    if text is None or not text.strip():
        return None

    try:
        value = float(text)

    except (TypeError, ValueError):
        raise ValueError(
            "Enter a valid numeric mark."
        )

    if (
        not math.isfinite(value)
        or not 0 <= value <= maximum
    ):
        raise ValueError(
            f"Mark must be between 0 and {maximum:g}."
        )

    return value


def init_view(app):
    @app.context_processor
    def shared_context():
        timezone = app.extensions["portal"]["timezone"]

        return {
            "campus_timezone": timezone.key,
        }

    @app.template_filter("campus_time")
    def campus_time(value):
        if value is None:
            return "—"

        timezone = app.extensions["portal"]["timezone"]

        return datetime.fromtimestamp(
            value,
            timezone,
        ).strftime("%I:%M:%S %p")