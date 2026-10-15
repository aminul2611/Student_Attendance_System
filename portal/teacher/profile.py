from flask import (
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from . import bp
from ..common import database, require


@bp.route("/profile", methods=["GET", "POST"])
@require("teacher")
def profile():

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        phone = request.form.get("phone", "").strip()
        department = request.form.get(
            "department", ""
        ).strip()
        designation = request.form.get(
            "designation", ""
        ).strip()

        values = [phone, department, designation]

        if not name or len(name) > 100:
            return jsonify(
                ok=False,
                message="Enter your name using 1–100 characters.",
            ), 400

        if any(len(value) > 150 for value in values):
            return jsonify(
                ok=False,
                message="Other fields must be within 150 characters.",
            ), 400

        with database() as db:
            db.execute(
                """
                UPDATE users
                SET name=?
                WHERE id=?
                """,
                (name, g.user["id"]),
            )

            db.execute(
                """
                INSERT INTO teacher_profiles(
                    user_id,
                    phone,
                    department,
                    designation
                )
                VALUES(?,?,?,?)

                ON CONFLICT(user_id)
                DO UPDATE SET
                    phone=excluded.phone,
                    department=excluded.department,
                    designation=excluded.designation
                """,
                (
                    g.user["id"],
                    phone,
                    department,
                    designation,
                ),
            )

        return jsonify(
            ok=True,
            message="OK — Profile updated successfully.",
            name=name,
        )

    with database() as db:
        details = db.execute(
            """
            SELECT *
            FROM teacher_profiles
            WHERE user_id=?
            """,
            (g.user["id"],),
        ).fetchone()

    return render_template(
        "teacher/profile.html",
        details=details,
    )


@bp.route("/password", methods=["GET", "POST"])
@require("teacher")
def password():

    if request.method == "POST":
        current_password = request.form.get(
            "current_password", ""
        )
        new_password = request.form.get(
            "new_password", ""
        )
        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not check_password_hash(
            g.user["password_hash"],
            current_password,
        ):
            flash(
                "Current password is incorrect.",
                "danger",
            )

        elif len(new_password) < 8:
            flash(
                "New password must contain at least 8 characters.",
                "danger",
            )

        elif new_password != confirm_password:
            flash(
                "New passwords do not match.",
                "danger",
            )

        else:
            with database() as db:
                db.execute(
                    """
                    UPDATE users
                    SET password_hash=?
                    WHERE id=?
                    """,
                    (
                        generate_password_hash(new_password),
                        g.user["id"],
                    ),
                )

            session.clear()

            flash(
                "Password changed successfully. "
                "Please log in with your new password.",
                "success",
            )

            return redirect(
                url_for("login", role="teacher")
            )

    return render_template("teacher/password.html")