from contextlib import closing


def create_tables(connect):
    with closing(connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS teacher_profiles(
            user_id INTEGER PRIMARY KEY
                REFERENCES users(id) ON DELETE CASCADE,
            phone TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT '',
            designation TEXT NOT NULL DEFAULT 'Teacher'
        );

        CREATE TABLE IF NOT EXISTS teacher_classes(
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            teacher_id INTEGER NOT NULL REFERENCES users(id),
            assessment_max REAL NOT NULL DEFAULT 20
                CHECK(assessment_max >= 0),
            mid_max REAL NOT NULL DEFAULT 30
                CHECK(mid_max >= 0),
            final_max REAL NOT NULL DEFAULT 50
                CHECK(final_max >= 0)
        );

        CREATE TABLE IF NOT EXISTS teacher_enrolments(
            class_id INTEGER NOT NULL
                REFERENCES teacher_classes(id),
            student_id INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            joined_on TEXT NOT NULL,
            PRIMARY KEY(class_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS teacher_lessons(
            id INTEGER PRIMARY KEY,
            class_id INTEGER NOT NULL
                REFERENCES teacher_classes(id),
            lesson_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            room TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS teacher_marks(
            class_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            assessment REAL,
            mid REAL,
            final REAL,
            PRIMARY KEY(class_id, student_id),
            FOREIGN KEY(class_id, student_id)
                REFERENCES teacher_enrolments(class_id, student_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS teacher_student_attendance(
            lesson_id INTEGER NOT NULL
                REFERENCES teacher_lessons(id),
            student_id INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL
                CHECK(status IN ('Present','Absent','Late','Excused')),
            PRIMARY KEY(lesson_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS teacher_work_attendance(
            teacher_id INTEGER NOT NULL REFERENCES users(id),
            work_date TEXT NOT NULL,
            check_in INTEGER NOT NULL,
            check_out INTEGER,
            PRIMARY KEY(teacher_id, work_date)
        );
        """)