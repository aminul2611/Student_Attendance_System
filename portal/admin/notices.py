from contextlib import closing
from datetime import datetime

from flask import (
    abort,
    current_app,
    g,
    jsonify,
    render_template,
    request,
)

from . import bp
from ..common import database, require


@bp.record_once
def setup_notices(state):
    connect = state.app.extensions["portal"]["connect"]

    with closing(connect()) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS admin_notices(
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
                    CHECK(active IN (0,1)),
                created_by INTEGER
                    REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_notice_recipients(
                notice_id INTEGER NOT NULL
                    REFERENCES admin_notices(id)
                    ON DELETE CASCADE,
                user_id INTEGER NOT NULL
                    REFERENCES users(id)
                    ON DELETE CASCADE,
                PRIMARY KEY(notice_id, user_id)
            );

            CREATE INDEX IF NOT EXISTS
                idx_admin_notice_recipient_user
            ON admin_notice_recipients(user_id, notice_id);
            """
        )
        db.commit()

    @state.app.context_processor
    def visible_notices():
        user = getattr(g, "user", None)

        if (
            not user
            or user["role"] not in (
                "admin",
                "teacher",
                "student",
            )
        ):
            return {"campus_notices": []}

        with database() as db:
            rows = db.execute(
                """
                SELECT
                    n.id,
                    n.title,
                    n.body,
                    n.created_at,
                    u.name AS author

                FROM admin_notices n

                JOIN admin_notice_recipients r
                    ON r.notice_id=n.id

                LEFT JOIN users u
                    ON u.id=n.created_by

                WHERE n.active=1
                  AND r.user_id=?

                ORDER BY n.created_at DESC, n.id DESC
                """,
                (user["id"],),
            ).fetchall()

        return {"campus_notices": rows}


def notice_rows():
    with database() as db:
        rows = db.execute(
            """
            SELECT n.*, u.name AS author

            FROM admin_notices n

            LEFT JOIN users u
                ON u.id=n.created_by

            ORDER BY n.updated_at DESC, n.id DESC
            """
        ).fetchall()

        people = db.execute(
            """
            SELECT
                r.notice_id,
                u.name,
                u.role

            FROM admin_notice_recipients r

            JOIN users u
                ON u.id=r.user_id

            ORDER BY u.name
            """
        ).fetchall()

    recipients = {}

    for person in people:
        recipients.setdefault(
            person["notice_id"], []
        ).append(dict(person))

    return [
        dict(
            row,
            recipients=recipients.get(row["id"], []),
        )
        for row in rows
    ]


@bp.get("/notices")
@require("admin")
def notices():
    editing = None
    selected_ids = set()

    with database() as db:
        people = db.execute(
            """
            SELECT
                id,
                name,
                email,
                role,
                student_no,
                active

            FROM users

            WHERE role IN ('teacher', 'student')

            ORDER BY name
            """
        ).fetchall()

        notice_id = request.args.get("edit", "").strip()

        if notice_id:
            try:
                notice_id = int(notice_id)
            except ValueError:
                abort(404)

            editing = db.execute(
                """
                SELECT *
                FROM admin_notices
                WHERE id=?
                """,
                (notice_id,),
            ).fetchone()

            if editing is None:
                abort(404)

            selected_ids = {
                row["user_id"]
                for row in db.execute(
                    """
                    SELECT user_id
                    FROM admin_notice_recipients
                    WHERE notice_id=?
                    """,
                    (notice_id,),
                )
            }

    return render_template(
        "admin/notices.html",
        notices=notice_rows(),
        editing=editing,
        people=people,
        selected_ids=selected_ids,
    )


@bp.post("/notices/save")
@require("admin")
def save_notice():
    notice_id_text = request.form.get(
        "notice_id", ""
    ).strip()

    title = request.form.get(
        "title", ""
    ).strip()

    body = request.form.get(
        "body", ""
    ).strip()

    active = request.form.get("active", "")

    if (
        not 1 <= len(title) <= 140
        or not 1 <= len(body) <= 5000
    ):
        return jsonify(
            ok=False,
            message=(
                "Enter a title (1–140 characters) "
                "and message (1–5000 characters)."
            ),
        ), 400

    if active not in ("0", "1"):
        return jsonify(
            ok=False,
            message="Choose Published or Draft.",
        ), 400

    notice_id = None

    if notice_id_text:
        try:
            notice_id = int(notice_id_text)
        except ValueError:
            return jsonify(
                ok=False,
                message="Invalid notice.",
            ), 400

        if notice_id <= 0:
            return jsonify(
                ok=False,
                message="Invalid notice.",
            ), 400

    try:
        recipient_ids = {
            int(value)
            for value in request.form.getlist(
                "recipients"
            )
        }
    except ValueError:
        return jsonify(
            ok=False,
            message="Select valid recipients.",
        ), 400

    if not recipient_ids:
        return jsonify(
            ok=False,
            message="Select at least one teacher or student.",
        ), 400

    timezone = current_app.extensions[
        "portal"
    ]["timezone"]

    timestamp = datetime.now(
        timezone
    ).isoformat(timespec="seconds")

    with database() as db:
        allowed = {
            row["id"]
            for row in db.execute(
                """
                SELECT id
                FROM users
                WHERE role IN ('teacher', 'student')
                """
            )
        }

        if not recipient_ids.issubset(allowed):
            return jsonify(
                ok=False,
                message="Select valid teachers or students.",
            ), 400

        if notice_id is not None:
            existing = db.execute(
                """
                SELECT id
                FROM admin_notices
                WHERE id=?
                """,
                (notice_id,),
            ).fetchone()

            if existing is None:
                abort(404)

            db.execute(
                """
                UPDATE admin_notices

                SET title=?,
                    body=?,
                    active=?,
                    updated_at=?

                WHERE id=?
                """,
                (
                    title,
                    body,
                    int(active),
                    timestamp,
                    notice_id,
                ),
            )

            db.execute(
                """
                DELETE FROM admin_notice_recipients
                WHERE notice_id=?
                """,
                (notice_id,),
            )

        else:
            notice_id = db.execute(
                """
                INSERT INTO admin_notices(
                    title,
                    body,
                    active,
                    created_by,
                    created_at,
                    updated_at
                )
                VALUES(?,?,?,?,?,?)
                """,
                (
                    title,
                    body,
                    int(active),
                    g.user["id"],
                    timestamp,
                    timestamp,
                ),
            ).lastrowid

        db.executemany(
            """
            INSERT INTO admin_notice_recipients(
                notice_id,
                user_id
            )
            VALUES(?,?)
            """,
            [
                (notice_id, user_id)
                for user_id in recipient_ids
            ],
        )

    return jsonify(
        ok=True,
        message="OK — Notice saved for selected recipients.",
        html=render_template(
            "admin/notice_list.html",
            notices=notice_rows(),
        ),
    )


@bp.post("/notices/<int:notice_id>/delete")
@require("admin")
def delete_notice(notice_id):
    with database() as db:
        existing = db.execute(
            """
            SELECT id
            FROM admin_notices
            WHERE id=?
            """,
            (notice_id,),
        ).fetchone()

        if existing is None:
            abort(404)

        db.execute(
            """
            DELETE FROM admin_notice_recipients
            WHERE notice_id=?
            """,
            (notice_id,),
        )

        db.execute(
            """
            DELETE FROM admin_notices
            WHERE id=?
            """,
            (notice_id,),
        )

    return jsonify(
        ok=True,
        message="OK — Notice deleted.",
        deleted_id=notice_id,
        html=render_template(
            "admin/notice_list.html",
            notices=notice_rows(),
        ),
    )