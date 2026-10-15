import re
import sqlite3

from contextlib import closing
from datetime import datetime


def upgrade(connect, database):
    with closing(connect()) as db:
        sql = db.execute(
            "SELECT sql FROM sqlite_master WHERE name='users'"
        ).fetchone()[0]

        if "'teacher'" in sql:
            return

        backup = (
            database
            + ".before_teacher_"
            + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            + ".bak"
        )

        with sqlite3.connect(backup) as destination:
            db.backup(destination)

        db.execute("PRAGMA foreign_keys=OFF")

        try:
            db.execute("BEGIN IMMEDIATE")

            sql = db.execute(
                "SELECT sql FROM sqlite_master WHERE name='users'"
            ).fetchone()[0]

            if "'teacher'" not in sql:
                sql, count = re.subn(
                    r"CHECK\s*\(\s*role\s+IN\s*\(\s*'admin'"
                    r"\s*,\s*'student'\s*\)\s*\)",
                    "CHECK(role IN ('admin','student','teacher'))",
                    sql,
                    flags=re.I,
                )

                if count != 1:
                    raise RuntimeError(
                        "Database structure differs. "
                        "Migration stopped. Backup was saved."
                    )

                sql = re.sub(
                    r'CREATE\s+TABLE\s+["`\[]?users["`\]]?',
                    "CREATE TABLE users_new",
                    sql,
                    count=1,
                    flags=re.I,
                )

                columns = ",".join(
                    '"' + row[1] + '"'
                    for row in db.execute(
                        "PRAGMA table_info(users)"
                    )
                )

                objects = db.execute(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE tbl_name='users'
                      AND type IN ('index','trigger')
                      AND sql IS NOT NULL
                    """
                ).fetchall()

                sequence = db.execute(
                    """
                    SELECT seq
                    FROM sqlite_sequence
                    WHERE name='users'
                    """
                ).fetchone()

                db.execute(sql)

                db.execute(
                    f"INSERT INTO users_new({columns}) "
                    f"SELECT {columns} FROM users"
                )

                db.execute("DROP TABLE users")

                db.execute(
                    "ALTER TABLE users_new RENAME TO users"
                )

                if sequence:
                    db.execute(
                        """
                        UPDATE sqlite_sequence
                        SET seq=MAX(seq,?)
                        WHERE name='users'
                        """,
                        (sequence[0],),
                    )

                for item in objects:
                    db.execute(item[0])

                if db.execute(
                    "PRAGMA foreign_key_check"
                ).fetchone():
                    raise RuntimeError(
                        "Database relationship check failed."
                    )

            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.execute("PRAGMA foreign_keys=ON")