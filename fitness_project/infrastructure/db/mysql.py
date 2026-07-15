"""MySQL persistence for users and normalized training sessions."""
import json
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import pymysql

from fitness_project.config.settings import settings


class MySQLClient:
    def _connect(self):
        return pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASS,
            database=settings.DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_tables(self) -> None:
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    apple_sub VARCHAR(128) NOT NULL,
                    email VARCHAR(254) NULL,
                    name VARCHAR(100) NULL,
                    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                        ON UPDATE CURRENT_TIMESTAMP(3),
                    UNIQUE KEY uk_users_apple_sub (apple_sub)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS training_sessions (
                    id CHAR(36) NOT NULL PRIMARY KEY,
                    user_id INT NOT NULL,
                    started_at DATETIME(3) NOT NULL,
                    local_date DATE NOT NULL,
                    focus_area VARCHAR(200) NULL,
                    duration_seconds INT UNSIGNED NOT NULL DEFAULT 0,
                    is_completed TINYINT(1) NOT NULL DEFAULT 0,
                    version INT UNSIGNED NOT NULL DEFAULT 1,
                    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                        ON UPDATE CURRENT_TIMESTAMP(3),
                    KEY idx_sessions_user_date (user_id, local_date, started_at),
                    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id)
                        REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS training_session_exercises (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    session_id CHAR(36) NOT NULL,
                    external_id CHAR(36) NOT NULL,
                    backend_id VARCHAR(255) NULL,
                    exercise_order SMALLINT UNSIGNED NOT NULL,
                    exercise_name VARCHAR(200) NOT NULL,
                    target_sets SMALLINT UNSIGNED NOT NULL,
                    target_reps VARCHAR(32) NOT NULL,
                    equipment VARCHAR(100) NULL,
                    difficulty VARCHAR(32) NULL,
                    images JSON NULL,
                    instructions TEXT NULL,
                    focus_area VARCHAR(100) NULL,
                    primary_muscles JSON NULL,
                    rest_seconds SMALLINT UNSIGNED NOT NULL DEFAULT 90,
                    UNIQUE KEY uk_session_exercise_id (session_id, external_id),
                    UNIQUE KEY uk_session_exercise_order (session_id, exercise_order),
                    CONSTRAINT fk_session_exercises_session FOREIGN KEY (session_id)
                        REFERENCES training_sessions(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS training_session_sets (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    session_exercise_id BIGINT UNSIGNED NOT NULL,
                    external_id CHAR(36) NOT NULL,
                    set_order SMALLINT UNSIGNED NOT NULL,
                    weight_kg DECIMAL(8,2) NOT NULL DEFAULT 0,
                    reps SMALLINT UNSIGNED NOT NULL DEFAULT 0,
                    is_completed TINYINT(1) NOT NULL DEFAULT 0,
                    UNIQUE KEY uk_exercise_set_id (session_exercise_id, external_id),
                    UNIQUE KEY uk_exercise_set_order (session_exercise_id, set_order),
                    CONSTRAINT fk_sets_session_exercise FOREIGN KEY (session_exercise_id)
                        REFERENCES training_session_exercises(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

    def get_user_by_apple_sub(self, apple_sub: str) -> Optional[Dict[str, Any]]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, apple_sub, email, name FROM users WHERE apple_sub = %s",
                    (apple_sub,),
                )
                return cursor.fetchone()
        finally:
            connection.close()

    def upsert_user(
        self,
        apple_sub: str,
        email: Optional[str],
        name: Optional[str],
    ) -> Dict[str, Any]:
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (apple_sub, email, name)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    email = COALESCE(VALUES(email), email),
                    name = COALESCE(VALUES(name), name),
                    id = LAST_INSERT_ID(id)
                """,
                (apple_sub, email, name),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "SELECT id, apple_sub, email, name FROM users WHERE id = %s",
                (user_id,),
            )
            return cursor.fetchone()

    def save_training_session(self, user_id: int, session: Dict[str, Any]) -> int:
        """Atomically replace a client-owned session and all nested snapshots."""
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO training_sessions
                    (id, user_id, started_at, local_date, focus_area,
                     duration_seconds, is_completed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    started_at = VALUES(started_at),
                    local_date = VALUES(local_date),
                    focus_area = VALUES(focus_area),
                    duration_seconds = VALUES(duration_seconds),
                    is_completed = VALUES(is_completed),
                    version = version + 1
                """,
                (
                    session["id"],
                    user_id,
                    session["started_at"],
                    session["local_date"],
                    session.get("focus_area"),
                    session["duration"],
                    session["is_completed"],
                ),
            )
            cursor.execute(
                "DELETE FROM training_session_exercises WHERE session_id = %s",
                (session["id"],),
            )

            for exercise in session["exercises"]:
                cursor.execute(
                    """
                    INSERT INTO training_session_exercises
                        (session_id, external_id, backend_id, exercise_order,
                         exercise_name, target_sets, target_reps, equipment,
                         difficulty, images, instructions, focus_area,
                         primary_muscles, rest_seconds)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session["id"],
                        exercise["id"],
                        exercise.get("backend_id"),
                        exercise["order"],
                        exercise["exercise_name"],
                        exercise["sets"],
                        exercise["reps"],
                        exercise.get("equipment"),
                        exercise.get("difficulty"),
                        json.dumps(exercise.get("images", []), ensure_ascii=False),
                        exercise.get("instructions"),
                        exercise.get("focus_area"),
                        json.dumps(exercise.get("primary_muscles", []), ensure_ascii=False),
                        exercise.get("rest_time", 90),
                    ),
                )
                exercise_row_id = cursor.lastrowid
                for index, exercise_set in enumerate(exercise["exercise_sets"], start=1):
                    cursor.execute(
                        """
                        INSERT INTO training_session_sets
                            (session_exercise_id, external_id, set_order,
                             weight_kg, reps, is_completed)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            exercise_row_id,
                            exercise_set["id"],
                            index,
                            exercise_set["weight"],
                            exercise_set["reps"],
                            exercise_set["is_completed"],
                        ),
                    )

            cursor.execute(
                "SELECT version FROM training_sessions WHERE id = %s AND user_id = %s",
                (session["id"], user_id),
            )
            return int(cursor.fetchone()["version"])

    def fetch_training_sessions_by_date(
        self,
        user_id: int,
        local_date: str,
    ) -> List[Dict[str, Any]]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, started_at, local_date, focus_area,
                           duration_seconds, is_completed, version
                    FROM training_sessions
                    WHERE user_id = %s AND local_date = %s
                    ORDER BY started_at, id
                    """,
                    (user_id, local_date),
                )
                sessions = cursor.fetchall()
                for session in sessions:
                    cursor.execute(
                        """
                        SELECT id, external_id, backend_id, exercise_order,
                               exercise_name, target_sets, target_reps, equipment,
                               difficulty, images, instructions, focus_area,
                               primary_muscles, rest_seconds
                        FROM training_session_exercises
                        WHERE session_id = %s
                        ORDER BY exercise_order
                        """,
                        (session["id"],),
                    )
                    exercises = cursor.fetchall()
                    for exercise in exercises:
                        cursor.execute(
                            """
                            SELECT external_id, weight_kg, reps, is_completed
                            FROM training_session_sets
                            WHERE session_exercise_id = %s
                            ORDER BY set_order
                            """,
                            (exercise["id"],),
                        )
                        exercise["exercise_sets"] = cursor.fetchall()
                    session["exercises"] = exercises
                return sessions
        finally:
            connection.close()


mysql_client = MySQLClient()
