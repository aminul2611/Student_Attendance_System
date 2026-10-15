from flask import (
    g,
    jsonify,
    render_template,
    request,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from . import bp
from ..common import database, require


@bp.route("/profile", methods=["GET", "POST"])
@require("admin")
def profile():
    if request.method == "GET":
        return render_template("admin/profile.html")

    action = request.form.get("action")

    if action == "name":
        name = request.form.get("name", "").strip()

        if not name or len(name) > 100:
            return jsonify(
                ok=False,
                message="Enter a name using 1–100 characters.",
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

        return jsonify(
            ok=True,
            message="OK — Profile updated successfully.",
            name=name,
        )

    if action == "password":
        current = request.form.get(
            "current_password", ""
        )

        new = request.form.get(
            "new_password", ""
        )

        confirmation = request.form.get(
            "confirm_password", ""
        )

        if not check_password_hash(
            g.user["password_hash"],
            current,
        ):
            return jsonify(
                ok=False,
                message="Current password is incorrect.",
            ), 400

        if not 8 <= len(new) <= 128:
            return jsonify(
                ok=False,
                message="Use a new password of 8–128 characters.",
            ), 400

        if new != confirmation:
            return jsonify(
                ok=False,
                message="New passwords do not match.",
            ), 400

        with database() as db:
            db.execute(
                """
                UPDATE users
                SET password_hash=?
                WHERE id=?
                """,
                (
                    generate_password_hash(new),
                    g.user["id"],
                ),
            )

        return jsonify(
            ok=True,
            message="OK — Password changed successfully.",
        )

    return jsonify(
        ok=False,
        message="Invalid profile action.",
    ), 400