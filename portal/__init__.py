import math

import click
from flask import g, redirect, request, url_for
from werkzeug.security import generate_password_hash

from .schema import upgrade
from .tables import create_tables


def init_portals(app, connect_db, database, timezone):
    app.extensions["portal"] = {
        "connect": connect_db,
        "timezone": timezone,
    }

    upgrade(connect_db, database)
    create_tables(connect_db)

    from .common import init_view

    init_view(app)

    from .teacher import bp as teacher_bp
    from .admin import bp as admin_bp

    app.register_blueprint(teacher_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def teacher_redirect():
        if (
            g.user
            and g.user["role"] == "teacher"
            and request.method == "GET"
        ):
            destinations = {
                "dashboard": "teacher.dashboard",
                "tasks": "teacher.marks",
                "attendance": "teacher.attendance",
            }

            if request.endpoint in destinations:
                return redirect(
                    url_for(destinations[request.endpoint])
                )

    from .common import database as open_db
    from .common import today

    @app.cli.command("create-teacher")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option(hide_input=False)
    def create_teacher(name, email, password):
        name = name.strip()
        email = email.strip().lower()

        if (
            not name
            or len(name) > 100
            or "@" not in email
            or len(password) < 8
        ):
            raise click.ClickException(
                "Enter a name, email and password "
                "of at least 8 characters."
            )

        with open_db() as db:
            existing = db.execute(
                "SELECT 1 FROM users WHERE email=?",
                (email,),
            ).fetchone()

            if existing:
                raise click.ClickException(
                    "This email already exists; "
                    "no account was changed."
                )

            db.execute(
                """
                INSERT INTO users(
                    name, email, password_hash, role
                )
                VALUES(?,?,?,?)
                """,
                (
                    name,
                    email,
                    generate_password_hash(password),
                    "teacher",
                ),
            )

        click.echo("Teacher account created.")

    @app.cli.command("assign-teacher-class")
    @click.option("--teacher-email", prompt=True)
    @click.option("--code", prompt=True)
    @click.option("--name", prompt="Class name")
    @click.option(
        "--student-nos",
        prompt="Student IDs, separated by commas",
    )
    @click.option(
        "--assessment-max",
        default=20.0,
        type=click.FloatRange(min=0, max=1000),
    )
    @click.option(
        "--mid-max",
        default=30.0,
        type=click.FloatRange(min=0, max=1000),
    )
    @click.option(
        "--final-max",
        default=50.0,
        type=click.FloatRange(min=0, max=1000),
    )
    def assign_teacher_class(
        teacher_email,
        code,
        name,
        student_nos,
        assessment_max,
        mid_max,
        final_max,
    ):
        limits = (
            assessment_max,
            mid_max,
            final_max,
        )

        if (
            not code.strip()
            or not name.strip()
            or not all(math.isfinite(x) for x in limits)
            or sum(limits) <= 0
        ):
            raise click.ClickException(
                "Enter class code/name and positive total marks."
            )

        with open_db() as db:
            teacher = db.execute(
                """
                SELECT id FROM users
                WHERE email=? AND role='teacher' AND active=1
                """,
                (teacher_email.strip().lower(),),
            ).fetchone()

            if not teacher:
                raise click.ClickException(
                    "Active teacher not found."
                )

            students = []

            for value in student_nos.split(","):
                if not value.strip():
                    continue

                student = db.execute(
                    """
                    SELECT id FROM users
                    WHERE student_no=?
                      AND role='student'
                      AND active=1
                    """,
                    (value.strip(),),
                ).fetchone()

                if not student:
                    raise click.ClickException(
                        "An entered Student ID was not found."
                    )

                students.append(student["id"])

            existing = db.execute(
                "SELECT * FROM teacher_classes WHERE code=?",
                (code.strip(),),
            ).fetchone()

            if existing:
                if existing["teacher_id"] != teacher["id"]:
                    raise click.ClickException(
                        "Class belongs to a different teacher."
                    )

                class_id = existing["id"]
            else:
                class_id = db.execute(
                    """
                    INSERT INTO teacher_classes(
                        code, name, teacher_id,
                        assessment_max, mid_max, final_max
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        code.strip(),
                        name.strip(),
                        teacher["id"],
                        assessment_max,
                        mid_max,
                        final_max,
                    ),
                ).lastrowid

            for student_id in students:
                db.execute(
                    """
                    INSERT OR IGNORE INTO teacher_enrolments
                    VALUES(?,?,?)
                    """,
                    (class_id, student_id, today()),
                )

        click.echo("Class assigned and students enrolled.")