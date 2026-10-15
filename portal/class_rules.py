from datetime import datetime


DAYS = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


def init_class_rules(db):
    columns = {
        row[1]
        for row in db.execute(
            "PRAGMA table_info(teacher_classes)"
        ).fetchall()
    }

    if "teacher_removed" not in columns:
        db.execute("""
            ALTER TABLE teacher_classes
            ADD COLUMN teacher_removed INTEGER NOT NULL DEFAULT 0
        """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS class_weekly_slots (
            id INTEGER PRIMARY KEY,

            class_id INTEGER NOT NULL
                REFERENCES teacher_classes(id)
                ON DELETE CASCADE,

            weekday INTEGER NOT NULL
                CHECK(weekday BETWEEN 0 AND 6),

            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,

            CHECK(start_time < end_time),

            UNIQUE(
                class_id,
                weekday,
                start_time,
                end_time
            )
        )
    """)


def read_weekly_slots(form):
    days = form.getlist("weekday")
    starts = form.getlist("start_time")
    ends = form.getlist("end_time")

    if not (
        1 <= len(days) <= 21
        and len(days) == len(starts) == len(ends)
    ):
        raise ValueError(
            "Add 1-21 complete weekly time slots."
        )

    slots = []

    for day, start, end in zip(days, starts, ends):
        try:
            if day not in tuple(str(i) for i in range(7)):
                raise ValueError()

            weekday = int(day)

            start = datetime.strptime(
                start, "%H:%M"
            ).strftime("%H:%M")

            end = datetime.strptime(
                end, "%H:%M"
            ).strftime("%H:%M")

        except (ValueError, TypeError):
            raise ValueError(
                "Select a day and valid start/end times."
            )

        if end <= start:
            raise ValueError(
                "End time must be after start time."
            )

        if any(
            d == weekday and a < end and b > start
            for d, a, b in slots
        ):
            raise ValueError(
                "Time slots for this class overlap."
            )

        slots.append((weekday, start, end))

    return sorted(slots)


def schedule_text(slots):
    def clock(value):
        return datetime.strptime(
            value, "%H:%M"
        ).strftime("%I:%M %p")

    return " | ".join(
        f"{DAYS[day]} {clock(start)}–{clock(end)}"
        for day, start, end in slots
    )


def remove_student_enrolment(db, class_id, student_id):
    # Acquire a write lock before checking marks.
    db.execute(
        """
        UPDATE teacher_classes
        SET setup_removed = setup_removed
        WHERE id = ?
        """,
        (class_id,),
    )

    enrolled = db.execute(
        """
        SELECT 1
        FROM teacher_enrolments
        WHERE class_id = ? AND student_id = ?
        """,
        (class_id, student_id),
    ).fetchone()

    if not enrolled:
        raise ValueError(
            "This class is not assigned to this student."
        )

    marked = db.execute(
        """
        SELECT 1
        FROM teacher_marks
        WHERE class_id = ?
          AND student_id = ?
          AND (
              assessment IS NOT NULL
              OR mid IS NOT NULL
              OR final IS NOT NULL
          )
        """,
        (class_id, student_id),
    ).fetchone()

    if marked:
        raise ValueError(
            "Cannot remove: marks have already been entered."
        )

    # Only empty marks rows can reach this point.
    db.execute(
        """
        DELETE FROM teacher_marks
        WHERE class_id = ? AND student_id = ?
        """,
        (class_id, student_id),
    )

    db.execute(
        """
        DELETE FROM student_enrolment_terms
        WHERE class_id = ? AND student_id = ?
        """,
        (class_id, student_id),
    )

    db.execute(
        """
        DELETE FROM teacher_enrolments
        WHERE class_id = ? AND student_id = ?
        """,
        (class_id, student_id),
    )


def remove_teacher_assignment(db, class_id, teacher_id):
    changed = db.execute(
        """
        UPDATE teacher_classes
        SET teacher_removed = 1
        WHERE id = ? AND teacher_id = ?
        """,
        (class_id, teacher_id),
    ).rowcount

    if not changed:
        raise ValueError(
            "Class not found for this teacher."
        )