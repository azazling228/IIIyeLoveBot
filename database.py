import os
import sqlite3

os.makedirs("/app/data", exist_ok=True)
DATABASE_NAME = "/app/data/dating.db"

# ==========================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ
# ==========================================

def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection

# ==========================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ
# ==========================================

def init_database():
    connection = get_connection()
    try:
        # ======================================
        # ПОЛЬЗОВАТЕЛИ
        # ======================================
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                city TEXT NOT NULL,
                search_gender TEXT NOT NULL,
                search_age_min INTEGER NOT NULL,
                search_age_max INTEGER NOT NULL,
                photo_file_id TEXT,
                description TEXT
            )
        """)

        # --------------------------------------
        # МИГРАЦИЯ СТАРОЙ БАЗЫ
        # --------------------------------------
        columns = connection.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
        column_names = {column["name"] for column in columns}
        if "photo_file_id" not in column_names:
            connection.execute("""
                ALTER TABLE users
                ADD COLUMN photo_file_id TEXT
            """)
        if "description" not in column_names:
            connection.execute("""
                ALTER TABLE users
                ADD COLUMN description TEXT
            """)

        # ======================================
        # ПРОСМОТРЫ
        # ======================================
        connection.execute("""
            CREATE TABLE IF NOT EXISTS views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewer_id INTEGER NOT NULL,
                viewed_id INTEGER NOT NULL,
                UNIQUE(viewer_id, viewed_id)
            )
        """)

        # ======================================
        # ЛАЙКИ
        # ======================================
        connection.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user INTEGER NOT NULL,
                to_user INTEGER NOT NULL,
                UNIQUE(from_user, to_user)
            )
        """)

        # ======================================
        # МЭТЧИ
        # ======================================
        connection.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_one INTEGER NOT NULL,
                user_two INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_one, user_two)
            )
        """)

        # ======================================
        # СООБЩЕНИЯ
        # ======================================
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP
            )
        """)

        message_columns = connection.execute(
            "PRAGMA table_info(messages)"
        ).fetchall()
        if "read_at" not in {column["name"] for column in message_columns}:
            connection.execute("""
                ALTER TABLE messages
                ADD COLUMN read_at TIMESTAMP
            """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS skips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                viewer_id INTEGER NOT NULL,
                skipped_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                blocker_id INTEGER NOT NULL,
                blocked_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (blocker_id, blocked_id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER NOT NULL,
                reported_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notified INTEGER NOT NULL DEFAULT 0,
                UNIQUE(reporter_id, reported_id)
            )
        """)
        report_columns = connection.execute(
            "PRAGMA table_info(reports)"
        ).fetchall()
        if "notified" not in {column["name"] for column in report_columns}:
            connection.execute("""
                ALTER TABLE reports
                ADD COLUMN notified INTEGER NOT NULL DEFAULT 0
            """)

        # ======================================
        # ИНДЕКСЫ
        # ======================================
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram_id
            ON users(telegram_id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_search
            ON users(city, gender, age)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_views_viewer
            ON views(viewer_id, viewed_id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_likes_from
            ON likes(from_user, to_user)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_likes_to
            ON likes(to_user, from_user)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_matches_user_one
            ON matches(user_one)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_matches_user_two
            ON matches(user_two)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_match
            ON messages(match_id, created_at)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_receiver
            ON messages(receiver_id, created_at)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_unread
            ON messages(receiver_id, read_at, match_id)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_skips_viewer
            ON skips(viewer_id, id)
        """)

        connection.commit()
    finally:
        connection.close()

# ==========================================
# ПОЛУЧИТЬ ПОЛЬЗОВАТЕЛЯ
# ==========================================

def get_user(telegram_id):
    connection = get_connection()
    try:
        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        ).fetchone()
        return user
    finally:
        connection.close()

# ==========================================
# СОЗДАТЬ ПОЛЬЗОВАТЕЛЯ
# ==========================================

def create_user(
    telegram_id,
    name,
    age,
    gender,
    city,
    search_gender,
    search_age_min,
    search_age_max,
    photo_file_id,
    description=""
):
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO users (
                telegram_id,
                name,
                age,
                gender,
                city,
                search_gender,
                search_age_min,
                search_age_max,
                photo_file_id,
                description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                name,
                age,
                gender,
                city,
                search_gender,
                search_age_min,
                search_age_max,
                photo_file_id,
                description,
            )
        )
        connection.commit()
    finally:
        connection.close()

# ==========================================
# ОБНОВИТЬ НАСТРОЙКИ ПОИСКА
# ==========================================

def update_search_settings(
    telegram_id,
    search_gender,
    search_age_min,
    search_age_max
):
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE users
            SET
                search_gender = ?,
                search_age_min = ?,
                search_age_max = ?
            WHERE telegram_id = ?
            """,
            (
                search_gender,
                search_age_min,
                search_age_max,
                telegram_id,
            )
        )
        connection.commit()
    finally:
        connection.close()

def update_profile_city(telegram_id, city):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET city = ? WHERE telegram_id = ?",
            (city, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()

def update_profile_photo(telegram_id, photo_file_id):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET photo_file_id = ? WHERE telegram_id = ?",
            (photo_file_id, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()

# ==========================================
# ПОИСК АНКЕТ
# ==========================================

def find_profiles(
    telegram_id,
    city,
    search_gender,
    age_min,
    age_max
):
    connection = get_connection()
    try:
        if search_gender == "all":
            users = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND age BETWEEN ? AND ?
                  AND NOT EXISTS (
                      SELECT 1 FROM blocks
                      WHERE (blocker_id = ? AND blocked_id = users.telegram_id)
                         OR (blocker_id = users.telegram_id AND blocked_id = ?)
                  )
                ORDER BY
                    CASE
                        WHEN city = ? THEN 0
                        ELSE 1
                    END,
                    RANDOM()
                """,
                (
                    telegram_id,
                    age_min,
                    age_max,
                    telegram_id,
                    telegram_id,
                    city,
                )
            ).fetchall()
        else:
            users = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND gender = ?
                  AND age BETWEEN ? AND ?
                  AND NOT EXISTS (
                      SELECT 1 FROM blocks
                      WHERE (blocker_id = ? AND blocked_id = users.telegram_id)
                         OR (blocker_id = users.telegram_id AND blocked_id = ?)
                  )
                ORDER BY
                    CASE
                        WHEN city = ? THEN 0
                        ELSE 1
                    END,
                    RANDOM()
                """,
                (
                    telegram_id,
                    search_gender,
                    age_min,
                    age_max,
                    telegram_id,
                    telegram_id,
                    city,
                )
            ).fetchall()
        return users
    finally:
        connection.close()

# ==========================================
# ПОЛУЧИТЬ СЛЕДУЮЩУЮ АНКЕТУ
# ==========================================

def get_next_profile(telegram_id, city, search_gender, age_min, age_max):
    connection = get_connection()
    try:
        if search_gender == "all":
            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND age BETWEEN ? AND ?
                  AND NOT EXISTS (
                      SELECT 1 FROM blocks
                      WHERE (blocker_id = ? AND blocked_id = users.telegram_id)
                         OR (blocker_id = users.telegram_id AND blocked_id = ?)
                  )
                  AND telegram_id NOT IN (
                      SELECT viewed_id
                      FROM views
                      WHERE viewer_id = ?
                  )
                ORDER BY
                    CASE WHEN city = ? THEN 0 ELSE 1 END,
                    RANDOM()
                LIMIT 1
                """,
                (
                    telegram_id,
                    age_min,
                    age_max,
                    telegram_id,
                    telegram_id,
                    telegram_id,
                    city,
                ),
            ).fetchone()
        else:
            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND gender = ?
                  AND age BETWEEN ? AND ?
                  AND NOT EXISTS (
                      SELECT 1 FROM blocks
                      WHERE (blocker_id = ? AND blocked_id = users.telegram_id)
                         OR (blocker_id = users.telegram_id AND blocked_id = ?)
                  )
                  AND telegram_id NOT IN (
                      SELECT viewed_id
                      FROM views
                      WHERE viewer_id = ?
                  )
                ORDER BY
                    CASE WHEN city = ? THEN 0 ELSE 1 END,
                    RANDOM()
                LIMIT 1
                """,
                (
                    telegram_id,
                    search_gender,
                    age_min,
                    age_max,
                    telegram_id,
                    telegram_id,
                    telegram_id,
                    city,
                ),
            ).fetchone()

        return user

    finally:
        connection.close()

# ==========================================
# ДОБАВИТЬ ПРОСМОТР
# ==========================================

def add_view(
    viewer_id,
    viewed_id
):
    if viewer_id == viewed_id:
        return
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO views (
                viewer_id,
                viewed_id
            )
            VALUES (?, ?)
            """,
            (
                viewer_id,
                viewed_id,
            )
        )
        connection.commit()
    finally:
        connection.close()

def add_skip(viewer_id, skipped_id):
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM skips WHERE viewer_id = ? AND skipped_id = ?",
            (viewer_id, skipped_id),
        )
        connection.execute(
            "INSERT INTO skips (viewer_id, skipped_id) VALUES (?, ?)",
            (viewer_id, skipped_id),
        )
        connection.commit()
    finally:
        connection.close()

def undo_last_skip(viewer_id):
    connection = get_connection()
    try:
        skip = connection.execute(
            """
            SELECT id, skipped_id
            FROM skips
            WHERE viewer_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (viewer_id,),
        ).fetchone()
        if not skip:
            return None
        connection.execute("DELETE FROM skips WHERE id = ?", (skip["id"],))
        connection.commit()
        return skip["skipped_id"]
    finally:
        connection.close()

def reset_views(viewer_id):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "DELETE FROM views WHERE viewer_id = ?",
            (viewer_id,),
        )
        connection.execute(
            "DELETE FROM skips WHERE viewer_id = ?",
            (viewer_id,),
        )
        connection.commit()
        return cursor.rowcount
    finally:
        connection.close()

# ==========================================
# ДОБАВИТЬ ЛАЙК
# ==========================================

def add_like(
    from_user,
    to_user
):
    if from_user == to_user:
        return
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO likes (
                from_user,
                to_user
            )
            VALUES (?, ?)
            """,
            (
                from_user,
                to_user,
            )
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()

def remove_like(from_user, to_user):
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM likes WHERE from_user = ? AND to_user = ?",
            (from_user, to_user),
        )
        connection.commit()
    finally:
        connection.close()

def get_incoming_likes(telegram_id):
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT users.*
            FROM likes
            JOIN users ON users.telegram_id = likes.from_user
            WHERE likes.to_user = ?
              AND NOT EXISTS (
                  SELECT 1 FROM likes AS reciprocal
                  WHERE reciprocal.from_user = ? AND reciprocal.to_user = likes.from_user
              )
            ORDER BY likes.rowid DESC
            """,
            (telegram_id, telegram_id),
        ).fetchall()
    finally:
        connection.close()

# ==========================================
# ПРОВЕРИТЬ ЛАЙК
# ==========================================

def has_like(
    from_user,
    to_user
):
    connection = get_connection()
    try:
        like = connection.execute(
            """
            SELECT 1
            FROM likes
            WHERE from_user = ?
              AND to_user = ?
            LIMIT 1
            """,
            (
                from_user,
                to_user,
            )
        ).fetchone()
        return like is not None
    finally:
        connection.close()

# ==========================================
# ПРОВЕРИТЬ ВЗАИМНЫЙ ЛАЙК
# ==========================================

def is_mutual_like(
    user_id,
    other_user_id
):
    return (
        has_like(user_id, other_user_id)
        and has_like(other_user_id, user_id)
    )

# ==========================================
# СОЗДАТЬ МЭТЧ
# ==========================================

def create_match(
    user_one,
    user_two
):
    if user_one == user_two:
        return False
    if user_one > user_two:
        user_one, user_two = user_two, user_one
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO matches (
                user_one,
                user_two
            )
            VALUES (?, ?)
            """,
            (
                user_one,
                user_two,
            )
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()

# ==========================================
# ПОЛУЧИТЬ ВСЕ МЭТЧИ ПОЛЬЗОВАТЕЛЯ
# ==========================================

def get_matches(
    telegram_id
):
    connection = get_connection()
    try:
        matches = connection.execute(
            """
            SELECT
                matches.id AS match_id,
                matches.created_at,
                (
                    SELECT COUNT(*)
                    FROM messages
                    WHERE messages.match_id = matches.id
                      AND messages.receiver_id = ?
                      AND messages.read_at IS NULL
                ) AS unread_count,
                CASE
                    WHEN matches.user_one = ?
                    THEN matches.user_two
                    ELSE matches.user_one
                END AS other_user_id,
                users.name,
                users.age,
                users.gender,
                users.city,
                users.photo_file_id,
                users.description
            FROM matches
            JOIN users
                ON users.telegram_id =
                    CASE
                        WHEN matches.user_one = ?
                        THEN matches.user_two
                        ELSE matches.user_one
                    END
            WHERE matches.user_one = ?
               OR matches.user_two = ?
            ORDER BY matches.created_at DESC
            """,
            (
                telegram_id,
                telegram_id,
                telegram_id,
                telegram_id,
                telegram_id,
            )
        ).fetchall()
        return matches
    finally:
        connection.close()

# ==========================================
# ПОЛУЧИТЬ ОДИН МЭТЧ
# ==========================================

def get_match(
    user_one,
    user_two
):
    if user_one > user_two:
        user_one, user_two = user_two, user_one
    connection = get_connection()
    try:
        match = connection.execute(
            """
            SELECT *
            FROM matches
            WHERE user_one = ?
              AND user_two = ?
            """,
            (
                user_one,
                user_two,
            )
        ).fetchone()
        return match
    finally:
        connection.close()

# ==========================================
# ДОБАВИТЬ СООБЩЕНИЕ
# ==========================================

def add_message(
    match_id,
    sender_id,
    receiver_id,
    text
):
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO messages (
                match_id,
                sender_id,
                receiver_id,
                text
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                match_id,
                sender_id,
                receiver_id,
                text,
            )
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()

# ==========================================
# ПОЛУЧИТЬ ИСТОРИЮ ЧАТА
# ==========================================

def get_messages(
    match_id,
    limit=50
):
    connection = get_connection()
    try:
        messages = connection.execute(
            """
            SELECT *
            FROM (
                SELECT *
                FROM messages
                WHERE match_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (
                match_id,
                limit,
            )
        ).fetchall()
        return messages
    finally:
        connection.close()

def mark_messages_read(match_id, receiver_id):
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE messages
            SET read_at = CURRENT_TIMESTAMP
            WHERE match_id = ? AND receiver_id = ? AND read_at IS NULL
            """,
            (match_id, receiver_id),
        )
        connection.commit()
    finally:
        connection.close()

def add_block(blocker_id, blocked_id):
    if blocker_id == blocked_id:
        return
    connection = get_connection()
    try:
        connection.execute(
            "INSERT OR IGNORE INTO blocks (blocker_id, blocked_id) VALUES (?, ?)",
            (blocker_id, blocked_id),
        )
        connection.execute(
            """
            DELETE FROM likes
            WHERE (from_user = ? AND to_user = ?)
               OR (from_user = ? AND to_user = ?)
            """,
            (blocker_id, blocked_id, blocked_id, blocker_id),
        )
        connection.execute(
            """
            DELETE FROM views
            WHERE (viewer_id = ? AND viewed_id = ?)
               OR (viewer_id = ? AND viewed_id = ?)
            """,
            (blocker_id, blocked_id, blocked_id, blocker_id),
        )
        connection.execute(
            """
            DELETE FROM skips
            WHERE (viewer_id = ? AND skipped_id = ?)
               OR (viewer_id = ? AND skipped_id = ?)
            """,
            (blocker_id, blocked_id, blocked_id, blocker_id),
        )
        match_ids = connection.execute(
            """
            SELECT id FROM matches
            WHERE (user_one = ? AND user_two = ?)
               OR (user_one = ? AND user_two = ?)
            """,
            (blocker_id, blocked_id, blocked_id, blocker_id),
        ).fetchall()
        for match in match_ids:
            connection.execute(
                "DELETE FROM messages WHERE match_id = ?",
                (match["id"],),
            )
        connection.execute(
            """
            DELETE FROM matches
            WHERE (user_one = ? AND user_two = ?)
               OR (user_one = ? AND user_two = ?)
            """,
            (blocker_id, blocked_id, blocked_id, blocker_id),
        )
        connection.commit()
    finally:
        connection.close()

def is_blocked(user_one, user_two):
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT 1 FROM blocks
            WHERE (blocker_id = ? AND blocked_id = ?)
               OR (blocker_id = ? AND blocked_id = ?)
            LIMIT 1
            """,
            (user_one, user_two, user_two, user_one),
        ).fetchone() is not None
    finally:
        connection.close()

def add_report(reporter_id, reported_id):
    if reporter_id == reported_id:
        return False
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO reports (reporter_id, reported_id)
            VALUES (?, ?)
            """,
            (reporter_id, reported_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()

def is_report_notified(reporter_id, reported_id):
    connection = get_connection()
    try:
        report = connection.execute(
            """
            SELECT notified FROM reports
            WHERE reporter_id = ? AND reported_id = ?
            """,
            (reporter_id, reported_id),
        ).fetchone()
        return bool(report and report["notified"])
    finally:
        connection.close()

def mark_report_notified(reporter_id, reported_id):
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE reports
            SET notified = 1
            WHERE reporter_id = ? AND reported_id = ?
            """,
            (reporter_id, reported_id),
        )
        connection.commit()
    finally:
        connection.close()

# ==========================================
# УДАЛИТЬ МЭТЧ
# ==========================================

def delete_match(
    user_one,
    user_two
):
    if user_one > user_two:
        user_one, user_two = user_two, user_one
    connection = get_connection()
    try:
        match = connection.execute(
            """
            SELECT id
            FROM matches
            WHERE user_one = ?
              AND user_two = ?
            """,
            (
                user_one,
                user_two,
            )
        ).fetchone()
        if match:
            connection.execute(
                """
                DELETE FROM messages
                WHERE match_id = ?
                """,
                (
                    match["id"],
                )
            )
            connection.execute(
                """
                DELETE FROM matches
                WHERE id = ?
                """,
                (
                    match["id"],
                )
            )
            connection.execute(
                """
                DELETE FROM likes
                WHERE (from_user = ? AND to_user = ?)
                   OR (from_user = ? AND to_user = ?)
                """,
                (user_one, user_two, user_two, user_one),
            )
        connection.commit()
    finally:
        connection.close()

# ==========================================
# УДАЛИТЬ ПОЛЬЗОВАТЕЛЯ
# ==========================================

def delete_user(
    telegram_id
):
    connection = get_connection()
    try:
        # --------------------------------------
        # УДАЛЯЕМ СООБЩЕНИЯ
        # --------------------------------------
        connection.execute(
            """
            DELETE FROM messages
            WHERE sender_id = ?
               OR receiver_id = ?
            """,
            (
                telegram_id,
                telegram_id,
            )
        )

        # --------------------------------------
        # УДАЛЯЕМ ЛАЙКИ
        # --------------------------------------
        connection.execute(
            """
            DELETE FROM likes
            WHERE from_user = ?
               OR to_user = ?
            """,
            (
                telegram_id,
                telegram_id,
            )
        )

        # --------------------------------------
        # УДАЛЯЕМ ПРОСМОТРЫ
        # --------------------------------------
        connection.execute(
            """
            DELETE FROM views
            WHERE viewer_id = ?
               OR viewed_id = ?
            """,
            (
                telegram_id,
                telegram_id,
            )
        )

        connection.execute(
            """
            DELETE FROM skips
            WHERE viewer_id = ? OR skipped_id = ?
            """,
            (telegram_id, telegram_id),
        )
        connection.execute(
            """
            DELETE FROM blocks
            WHERE blocker_id = ? OR blocked_id = ?
            """,
            (telegram_id, telegram_id),
        )
        connection.execute(
            """
            DELETE FROM reports
            WHERE reporter_id = ? OR reported_id = ?
            """,
            (telegram_id, telegram_id),
        )

        # --------------------------------------
        # НАХОДИМ МЭТЧИ
        # --------------------------------------
        match_ids = connection.execute(
            """
            SELECT id
            FROM matches
            WHERE user_one = ?
               OR user_two = ?
            """,
            (
                telegram_id,
                telegram_id,
            )
        ).fetchall()

        # --------------------------------------
        # УДАЛЯЕМ СООБЩЕНИЯ МЭТЧЕЙ
        # --------------------------------------
        for match in match_ids:
            connection.execute(
                """
                DELETE FROM messages
                WHERE match_id = ?
                """,
                (
                    match["id"],
                )
            )

        # --------------------------------------
        # УДАЛЯЕМ МЭТЧИ
        # --------------------------------------
        connection.execute(
            """
            DELETE FROM matches
            WHERE user_one = ?
               OR user_two = ?
            """,
            (
                telegram_id,
                telegram_id,
            )
        )

        # --------------------------------------
        # УДАЛЯЕМ ПОЛЬЗОВАТЕЛЯ
        # --------------------------------------
        connection.execute(
            """
            DELETE FROM users
            WHERE telegram_id = ?
            """,
            (
                telegram_id,
            )
        )

        connection.commit()
    finally:
        connection.close()