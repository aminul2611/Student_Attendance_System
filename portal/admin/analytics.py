import calendar

from datetime import date, timedelta
from flask import abort, request

from ..common import today


STATUSES = [
    "Present",
    "Absent",
    "Late",
    "Excused",
    "Not marked",
]


def dashboard_data(db):
    current = date.fromisoformat(today())
    mode = request.args.get("mode", "daily")

    if mode not in ("daily", "monthly"):
        abort(
            400,
            description="Choose Daily or Monthly.",
        )

    try:
        if mode == "daily":
            start = date.fromisoformat(
                request.args.get("date", today())
            )
            end = start

        else:
            month = request.args.get(
                "month", today()[:7]
            )

            start = date.fromisoformat(
                month + "-01"
            )

            last_day = calendar.monthrange(
                start.year,
                start.month,
            )[1]

            end = date(
                start.year,
                start.month,
                last_day,
            )

        if start > current:
            raise ValueError()

        end = min(end, current)

    except ValueError:
        abort(
            400,
            description="Choose a valid date/month up to today.",
        )

    teachers = db.execute(
        """
        SELECT id, name
        FROM users
        WHERE role='teacher'
        ORDER BY name
        """
    ).fetchall()

    all_classes = db.execute(
        """
        SELECT id, code, name, teacher_id
        FROM teacher_classes
        ORDER BY code
        """
    ).fetchall()

    teacher_id = request.args.get("teacher_id", "")
    class_id = request.args.get("class_id", "")

    valid_teachers = {
        str(teacher["id"])
        for teacher in teachers
    }

    if teacher_id and teacher_id not in valid_teachers:
        abort(
            400,
            description="Teacher not found.",
        )

    classes = [
        classroom
        for classroom in all_classes
        if (
            not teacher_id
            or str(classroom["teacher_id"]) == teacher_id
        )
    ]

    selected_class = next(
        (
            classroom
            for classroom in classes
            if str(classroom["id"]) == class_id
        ),
        None,
    )

    if class_id and not selected_class:
        abort(
            400,
            description=(
                "Class does not match the selected teacher."
            ),
        )

    effective_teacher = (
        str(selected_class["teacher_id"])
        if selected_class
        else teacher_id
    )

    where = "l.lesson_date BETWEEN ? AND ?"

    params = [
        start.isoformat(),
        end.isoformat(),
    ]

    if effective_teacher:
        where += " AND c.teacher_id=?"
        params.append(effective_teacher)

    if class_id:
        where += " AND c.id=?"
        params.append(class_id)

    rows = db.execute(
        """
        SELECT
            l.lesson_date,
            COALESCE(a.status, 'Not marked') AS status,
            COUNT(e.student_id) AS amount

        FROM teacher_lessons l

        JOIN teacher_classes c
            ON c.id=l.class_id

        LEFT JOIN teacher_enrolments e
            ON e.class_id=l.class_id
            AND e.joined_on<=l.lesson_date

        LEFT JOIN teacher_student_attendance a
            ON a.lesson_id=l.id
            AND a.student_id=e.student_id

        WHERE """ + where + """

        GROUP BY
            l.lesson_date,
            COALESCE(a.status, 'Not marked')
        """,
        params,
    ).fetchall()

    days = [
        (start + timedelta(days=index)).isoformat()
        for index in range((end - start).days + 1)
    ]

    student = {
        day: {
            status: 0
            for status in STATUSES
        }
        for day in days
    }

    for row in rows:
        student[row["lesson_date"]][row["status"]] += (
            row["amount"]
        )

    teacher_where = "work_date BETWEEN ? AND ?"

    teacher_params = [
        start.isoformat(),
        end.isoformat(),
    ]

    if effective_teacher:
        teacher_where += " AND teacher_id=?"
        teacher_params.append(effective_teacher)

    work = db.execute(
        """
        SELECT
            work_date,
            COUNT(*) AS ins,
            COUNT(check_out) AS outs

        FROM teacher_work_attendance

        WHERE """ + teacher_where + """

        GROUP BY work_date
        """,
        teacher_params,
    ).fetchall()

    teacher = {
        day: {
            "ins": 0,
            "outs": 0,
        }
        for day in days
    }

    for row in work:
        teacher[row["work_date"]] = {
            "ins": row["ins"],
            "outs": row["outs"],
        }

    sessions = db.execute(
        """
        SELECT
            l.*,
            c.code,
            c.name,
            u.name AS teacher_name

        FROM teacher_lessons l

        JOIN teacher_classes c
            ON c.id=l.class_id

        JOIN users u
            ON u.id=c.teacher_id

        WHERE """ + where + """

        ORDER BY
            l.lesson_date DESC,
            l.start_time

        LIMIT 10
        """,
        params,
    ).fetchall()

    session_count = db.execute(
        """
        SELECT COUNT(*)
        FROM teacher_lessons l

        JOIN teacher_classes c
            ON c.id=l.class_id

        WHERE """ + where,
        params,
    ).fetchone()[0]

    totals = {
        status: sum(
            student[day][status]
            for day in days
        )
        for status in STATUSES
    }

    active_students = db.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE role='student' AND active=1
        """
    ).fetchone()[0]

    active_teachers = db.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE role='teacher' AND active=1
        """
    ).fetchone()[0]

    class_count = len([
        classroom
        for classroom in classes
        if (
            not class_id
            or str(classroom["id"]) == class_id
        )
    ])

    check_ins = sum(
        teacher[day]["ins"]
        for day in days
    )

    cards = [
        (
            "Active Students",
            active_students,
            "Current accounts · all students",
        ),
        (
            "Active Teachers",
            active_teachers,
            "Current accounts · all teachers",
        ),
        (
            "Assigned Classes",
            class_count,
            "Selected teacher / class",
        ),
        (
            "Scheduled Sessions",
            session_count,
            "Selected period through today",
        ),
        (
            "Teacher Check-ins",
            check_ins,
            "Teacher-days in selected period",
        ),
        (
            "Present Records",
            totals["Present"],
            "Student attendance per session",
        ),
    ]

    return {
        "mode": mode,
        "selected_date": start.isoformat(),
        "selected_month": start.strftime("%Y-%m"),
        "max_date": today(),
        "max_month": today()[:7],
        "period": (
            f"{start.isoformat()} → {end.isoformat()}"
        ),
        "teachers": teachers,
        "classes": classes,
        "teacher_id": teacher_id,
        "class_id": class_id,
        "cards": cards,
        "sessions": sessions,
        "totals": totals,
        "graphs": {
            "mode": mode,
            "days": days,
            "statuses": STATUSES,
            "student": student,
            "teacher": teacher,
        },
    }