import re
import sqlite3

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import generate_password_hash

from . import bp
from ..common import database, require, today
from ..class_rules import (
    init_class_rules,
    read_weekly_slots,
    schedule_text,
    remove_student_enrolment,
)


# DATABASE SETUP

def init_student_tables(connect):
    db = connect()

    try:
        with db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS student_profiles (
                    user_id INTEGER PRIMARY KEY
                        REFERENCES users(id) ON DELETE CASCADE,
                    phone TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS student_enrolment_terms (
                    class_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    semester TEXT NOT NULL,

                    PRIMARY KEY (class_id, student_id),

                    FOREIGN KEY (class_id, student_id)
                        REFERENCES teacher_enrolments(
                            class_id, student_id
                        )
                        ON DELETE CASCADE
                );
            """)

            columns = {
                row[1]
                for row in db.execute(
                    "PRAGMA table_info(teacher_classes)"
                ).fetchall()
            }

            if not columns:
                raise RuntimeError(
                    "Create teacher_classes before "
                    "calling init_student_tables()."
                )

            if "semester" not in columns:
                db.execute("""
                    ALTER TABLE teacher_classes
                    ADD COLUMN semester TEXT NOT NULL DEFAULT ''
                """)

            if "class_time" not in columns:
                db.execute("""
                    ALTER TABLE teacher_classes
                    ADD COLUMN class_time TEXT NOT NULL DEFAULT ''
                """)

            if "setup_removed" not in columns:
                db.execute("""
                    ALTER TABLE teacher_classes
                    ADD COLUMN setup_removed INTEGER NOT NULL DEFAULT 0
                """)

            init_class_rules(db)

    finally:
        db.close()


# VALIDATION HELPERS

def find_student(db, student_id):
    student = db.execute(
        """
        SELECT
            u.*,
            COALESCE(p.phone, '') AS phone,
            COALESCE(p.department, '') AS department
        FROM users u
        LEFT JOIN student_profiles p
            ON p.user_id=u.id
        WHERE u.id=?
          AND u.role='student'
        """,
        (student_id,),
    ).fetchone()

    if student is None:
        abort(404)

    return student


def student_fields():
    fields = {
        key: request.form.get(key, "").strip()
        for key in (
            "name",
            "email",
            "student_no",
            "phone",
            "department",
        )
    }

    fields["email"] = fields["email"].lower()

    if not 1 <= len(fields["name"]) <= 100:
        raise ValueError(
            "Name must contain 1-100 characters."
        )

    if (
        len(fields["email"]) > 254
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            fields["email"],
        )
    ):
        raise ValueError("Enter a valid email address.")

    if not 1 <= len(fields["student_no"]) <= 100:
        raise ValueError(
            "Student ID must contain 1-100 characters."
        )

    if any(
        len(fields[key]) > 150
        for key in ("phone", "department")
    ):
        raise ValueError(
            "Phone and department must be within 150 characters."
        )

    return fields


def new_password():
    password = request.form.get("new_password", "")
    confirmation = request.form.get("confirm_password", "")

    if not 8 <= len(password) <= 128:
        raise ValueError(
            "Password must contain 8-128 characters."
        )

    if password != confirmation:
        raise ValueError("Passwords do not match.")

    return generate_password_hash(password)


# STUDENT LIST WITH CLASS / SEMESTER FILTERS

@bp.get("/student-details")
@require("admin")
def student_details():
    selected_semester = request.args.get(
        "semester", ""
    ).strip()

    class_text = request.args.get(
        "class_id", ""
    ).strip()

    selected_class_id = None

    if class_text:
        try:
            selected_class_id = int(class_text)
        except ValueError:
            abort(400)

        if selected_class_id <= 0:
            abort(400)

    # Prefer the semester saved with the student's assignment.
    semester_sql = """
        COALESCE(
            NULLIF(TRIM(t.semester), ''),
            NULLIF(TRIM(c.semester), ''),
            'Semester not assigned'
        )
    """

    with database() as db:
        # Historical classes remain available for reviewing assignments.
        classes = db.execute(
            """
            SELECT id, code, name, semester
            FROM teacher_classes
            ORDER BY semester, code, id
            """
        ).fetchall()

        selected_class = None

        if selected_class_id is not None:
            selected_class = next(
                (
                    row for row in classes
                    if row["id"] == selected_class_id
                ),
                None,
            )

            if selected_class is None:
                abort(404)

        semesters = [
            row["semester"]
            for row in db.execute(
                f"""
                SELECT DISTINCT
                    {semester_sql} AS semester
                FROM teacher_enrolments e
                JOIN teacher_classes c
                    ON c.id=e.class_id
                LEFT JOIN student_enrolment_terms t
                    ON t.class_id=e.class_id
                    AND t.student_id=e.student_id
                ORDER BY semester
                """
            ).fetchall()
        ]

        conditions = ["e.student_id=u.id"]
        parameters = []

        if selected_class_id is not None:
            conditions.append("e.class_id=?")
            parameters.append(selected_class_id)

        if selected_semester:
            conditions.append(f"{semester_sql}=?")
            parameters.append(selected_semester)

        assignment_filter = ""

        if selected_class_id is not None or selected_semester:
            assignment_filter = f"""
                AND EXISTS (
                    SELECT 1
                    FROM teacher_enrolments e
                    JOIN teacher_classes c
                        ON c.id=e.class_id
                    LEFT JOIN student_enrolment_terms t
                        ON t.class_id=e.class_id
                        AND t.student_id=e.student_id
                    WHERE {" AND ".join(conditions)}
                )
            """

        students = db.execute(
            f"""
            SELECT
                u.id,
                u.name,
                u.email,
                u.student_no,
                u.active,
                COALESCE(p.department, '') AS department,

                EXISTS (
                    SELECT 1
                    FROM teacher_marks m
                    WHERE m.student_id=u.id
                      AND m.class_id=?
                      AND (
                          m.assessment IS NOT NULL
                          OR m.mid IS NOT NULL
                          OR m.final IS NOT NULL
                      )
                ) AS has_marks

            FROM users u

            LEFT JOIN student_profiles p
                ON p.user_id=u.id

            WHERE u.role='student'
            {assignment_filter}

            ORDER BY u.name COLLATE NOCASE, u.id
            """,
            [selected_class_id, *parameters],
        ).fetchall()

    return render_template(
        "admin/student_details.html",
        students=students,
        classes=classes,
        semesters=semesters,
        selected_class=selected_class,
        selected_class_id=selected_class_id,
        selected_semester=selected_semester,
    )


# CREATE STUDENT

@bp.post("/student-details/create")
@require("admin")
def create_student_account():
    try:
        fields = student_fields()
        hashed = new_password()

        with database() as db:
            student_id = db.execute(
                """
                INSERT INTO users(
                    name,
                    email,
                    student_no,
                    password_hash,
                    role,
                    active
                )
                VALUES(?, ?, ?, ?, 'student', 1)
                """,
                (
                    fields["name"],
                    fields["email"],
                    fields["student_no"],
                    hashed,
                ),
            ).lastrowid

            db.execute(
                """
                INSERT INTO student_profiles(
                    user_id,
                    phone,
                    department
                )
                VALUES(?, ?, ?)
                """,
                (
                    student_id,
                    fields["phone"],
                    fields["department"],
                ),
            )

        flash(
            "Student account created successfully.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    except sqlite3.IntegrityError:
        flash(
            "Could not save. Email or Student ID "
            "may already be in use.",
            "danger",
        )

    return redirect(
        url_for("admin_portal.student_details"),
        code=303,
    )


# STUDENT STATUS

@bp.post("/student-details/<int:student_id>/status")
@require("admin")
def set_student_status(student_id):
    active = request.form.get("active", "")

    if active not in ("0", "1"):
        abort(400)

    with database() as db:
        find_student(db, student_id)

        db.execute(
            """
            UPDATE users
            SET active=?
            WHERE id=?
              AND role='student'
            """,
            (int(active), student_id),
        )

    flash("Student status updated.", "success")

    return redirect(
        url_for("admin_portal.student_details"),
        code=303,
    )


# STUDENT ACCOUNT SETTINGS

@bp.route(
    "/student-details/<int:student_id>/account",
    methods=["GET", "POST"],
)
@require("admin")
def student_account(student_id):
    with database() as db:
        student = find_student(db, student_id)

    if request.method == "GET":
        return render_template(
            "admin/student_account.html",
            student=student,
        )

    try:
        fields = student_fields()
        active = request.form.get("active", "")

        if active not in ("0", "1"):
            raise ValueError(
                "Choose a valid account status."
            )

        with database() as db:
            find_student(db, student_id)

            db.execute(
                """
                UPDATE users
                SET name=?,
                    email=?,
                    student_no=?,
                    active=?
                WHERE id=?
                  AND role='student'
                """,
                (
                    fields["name"],
                    fields["email"],
                    fields["student_no"],
                    int(active),
                    student_id,
                ),
            )

            db.execute(
                """
                INSERT INTO student_profiles(
                    user_id,
                    phone,
                    department
                )
                VALUES(?, ?, ?)

                ON CONFLICT(user_id) DO UPDATE SET
                    phone=excluded.phone,
                    department=excluded.department
                """,
                (
                    student_id,
                    fields["phone"],
                    fields["department"],
                ),
            )

        flash(
            "Student account updated successfully.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    except sqlite3.IntegrityError:
        flash(
            "Could not save. Email or Student ID "
            "may already be in use.",
            "danger",
        )

    return redirect(
        url_for(
            "admin_portal.student_account",
            student_id=student_id,
        ),
        code=303,
    )


# RESET STUDENT PASSWORD

@bp.post(
    "/student-details/<int:student_id>/reset-password"
)
@require("admin")
def reset_student_password(student_id):
    with database() as db:
        find_student(db, student_id)

    try:
        hashed = new_password()

        with database() as db:
            db.execute(
                """
                UPDATE users
                SET password_hash=?
                WHERE id=?
                  AND role='student'
                """,
                (hashed, student_id),
            )

        flash(
            "Student password reset successfully.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    return redirect(
        url_for(
            "admin_portal.student_account",
            student_id=student_id,
        ),
        code=303,
    )


# TASK PAGE: CLASS SETUP

@bp.get("/class-tasks")
@require("admin")
def class_tasks():
    with database() as db:
        teachers = db.execute(
            """
            SELECT id, name
            FROM users
            WHERE role='teacher'
              AND active=1
            ORDER BY name COLLATE NOCASE, id
            """
        ).fetchall()

        class_setups = db.execute(
            """
            SELECT
                c.id,
                c.code,
                c.name,
                c.semester,
                c.class_time,
                c.teacher_removed,
                u.name AS teacher_name,
                (
                    SELECT COUNT(*)
                    FROM teacher_enrolments e
                    WHERE e.class_id=c.id
                ) AS student_count

            FROM teacher_classes c

            JOIN users u ON u.id=c.teacher_id

            WHERE c.setup_removed=0

            ORDER BY c.semester, c.code, c.id
            """
        ).fetchall()

    return render_template(
        "admin/class_tasks.html",
        teachers=teachers,
        class_setups=class_setups,
    )


# CREATE CLASS WITH WEEKLY TIMES

@bp.post("/student-details/class-setup")
@require("admin")
def create_student_class_setup():
    class_name = request.form.get(
        "class_name", ""
    ).strip()

    semester = request.form.get(
        "semester", ""
    ).strip()

    subject_name = request.form.get(
        "subject_name", ""
    ).strip()

    teacher_id = request.form.get(
        "teacher_id", type=int
    )

    try:
        for label, value, limit in (
            ("Class", class_name, 80),
            ("Semester", semester, 80),
            ("Subject name", subject_name, 150),
        ):
            if not 1 <= len(value) <= limit:
                raise ValueError(
                    f"{label} must contain 1-{limit} characters."
                )

        slots = read_weekly_slots(request.form)
        class_time = schedule_text(slots)

        with database() as db:
            teacher = db.execute(
                """
                SELECT id
                FROM users
                WHERE id=?
                  AND role='teacher'
                  AND active=1
                """,
                (teacher_id,),
            ).fetchone()

            if teacher is None:
                raise ValueError(
                    "Select an active teacher."
                )

            class_id = db.execute(
                """
                INSERT INTO teacher_classes(
                    teacher_id,
                    code,
                    name,
                    semester,
                    class_time,
                    assessment_max,
                    mid_max,
                    final_max,
                    setup_removed,
                    teacher_removed
                )
                VALUES(?, ?, ?, ?, ?, 20, 30, 50, 0, 0)
                """,
                (
                    teacher_id,
                    class_name,
                    subject_name,
                    semester,
                    class_time,
                ),
            ).lastrowid

            db.executemany(
                """
                INSERT INTO class_weekly_slots(
                    class_id,
                    weekday,
                    start_time,
                    end_time
                )
                VALUES(?, ?, ?, ?)
                """,
                [
                    (class_id, day, start, end)
                    for day, start, end in slots
                ],
            )

        flash(
            "Class and weekly schedule saved successfully.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    except sqlite3.IntegrityError:
        flash(
            "Could not save. Use a unique class code. "
            "Previously removed class codes remain reserved.",
            "danger",
        )

    return redirect(
        url_for("admin_portal.class_tasks"),
        code=303,
    )


# REMOVE COURSE FROM NEW ASSIGNMENTS

@bp.post("/class-tasks/<int:class_id>/remove")
@require("admin")
def remove_class_setup(class_id):
    with database() as db:
        classroom = db.execute(
            """
            SELECT id
            FROM teacher_classes
            WHERE id=?
            """,
            (class_id,),
        ).fetchone()

        if classroom is None:
            abort(404)

        db.execute(
            """
            UPDATE teacher_classes
            SET setup_removed=1
            WHERE id=?
            """,
            (class_id,),
        )

    flash(
        "Course removed from new assignments. "
        "Existing assignments and results are preserved.",
        "success",
    )

    return redirect(
        url_for("admin_portal.class_tasks"),
        code=303,
    )


# STUDENT CLASS ASSIGNMENTS AND RESULTS

@bp.get(
    "/student-details/<int:student_id>/classes"
)
@require("admin")
def student_classes(student_id):
    with database() as db:
        student = find_student(db, student_id)

        classes = db.execute(
            """
            SELECT
                c.id,
                c.code,
                c.name,
                c.semester,
                c.class_time,
                u.name AS teacher_name

            FROM teacher_classes c

            JOIN users u ON u.id=c.teacher_id

            WHERE TRIM(COALESCE(c.semester, '')) <> ''
              AND c.setup_removed=0
              AND c.teacher_removed=0

            ORDER BY c.semester, c.code, c.id
            """
        ).fetchall()

        results = db.execute(
            """
            SELECT
                c.id,
                c.code,
                c.name,
                c.class_time,
                c.teacher_removed,
                u.name AS teacher_name,
                c.assessment_max,
                c.mid_max,
                c.final_max,
                m.assessment,
                m.mid,
                m.final,

                (
                    m.assessment IS NOT NULL
                    OR m.mid IS NOT NULL
                    OR m.final IS NOT NULL
                ) AS has_marks,

                COALESCE(
                    NULLIF(TRIM(t.semester), ''),
                    NULLIF(TRIM(c.semester), ''),
                    'Semester not assigned'
                ) AS semester

            FROM teacher_enrolments e

            JOIN teacher_classes c
                ON c.id=e.class_id

            JOIN users u
                ON u.id=c.teacher_id

            LEFT JOIN teacher_marks m
                ON m.class_id=e.class_id
                AND m.student_id=e.student_id

            LEFT JOIN student_enrolment_terms t
                ON t.class_id=e.class_id
                AND t.student_id=e.student_id

            WHERE e.student_id=?

            ORDER BY semester, c.code, c.id
            """,
            (student_id,),
        ).fetchall()

    return render_template(
        "admin/student_classes.html",
        student=student,
        classes=classes,
        results=results,
    )


# ASSIGN CLASS TO STUDENT

@bp.post(
    "/student-details/<int:student_id>/assign-class"
)
@require("admin")
def assign_student_class(student_id):
    class_id = request.form.get("class_id", type=int)

    with database() as db:
        # Acquire a write lock before checking availability.
        db.execute(
            """
            UPDATE teacher_classes
            SET setup_removed=setup_removed
            WHERE id=?
            """,
            (class_id,),
        )

        find_student(db, student_id)

        classroom = db.execute(
            """
            SELECT id, semester
            FROM teacher_classes
            WHERE id=?
              AND setup_removed=0
              AND teacher_removed=0
            """,
            (class_id,),
        ).fetchone()

        if classroom is None:
            flash(
                "Select an available class "
                "with an assigned teacher.",
                "danger",
            )

        elif not (classroom["semester"] or "").strip():
            flash(
                "This class has no semester. "
                "Add a class from Task → Class Setup.",
                "danger",
            )

        else:
            db.execute(
                """
                INSERT OR IGNORE INTO teacher_enrolments(
                    class_id,
                    student_id,
                    joined_on
                )
                VALUES(?, ?, ?)
                """,
                (
                    class_id,
                    student_id,
                    today(),
                ),
            )

            db.execute(
                """
                INSERT INTO student_enrolment_terms(
                    class_id,
                    student_id,
                    semester
                )
                VALUES(?, ?, ?)

                ON CONFLICT(class_id, student_id)
                DO UPDATE SET
                    semester=excluded.semester
                """,
                (
                    class_id,
                    student_id,
                    classroom["semester"],
                ),
            )

            flash(
                "Class assigned successfully.",
                "success",
            )

    return redirect(
        url_for(
            "admin_portal.student_classes",
            student_id=student_id,
        ),
        code=303,
    )


# REMOVE ASSIGNMENT FROM STUDENT'S DETAILS PAGE

@bp.post(
    "/student-details/<int:student_id>"
    "/classes/<int:class_id>/remove"
)
@require("admin")
def remove_student_class(student_id, class_id):
    try:
        with database() as db:
            find_student(db, student_id)

            remove_student_enrolment(
                db,
                class_id,
                student_id,
            )

        flash(
            "Student class assignment removed.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    return redirect(
        url_for(
            "admin_portal.student_classes",
            student_id=student_id,
        ),
        code=303,
    )


# REMOVE ASSIGNMENT FROM FILTERED STUDENT LIST

@bp.post(
    "/student-details/<int:student_id>"
    "/classes/<int:class_id>/remove-from-list"
)
@require("admin")
def remove_student_class_from_list(student_id, class_id):
    semester = request.form.get(
        "semester", ""
    ).strip()

    try:
        with database() as db:
            find_student(db, student_id)

            remove_student_enrolment(
                db,
                class_id,
                student_id,
            )

        flash(
            "Student removed from the selected class. "
            "The student account is unchanged.",
            "success",
        )

    except ValueError as error:
        flash(str(error), "danger")

    return redirect(
        url_for(
            "admin_portal.student_details",
            class_id=class_id,
            semester=semester,
        ),
        code=303,
    )