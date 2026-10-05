import sqlite3


DATABASE_NAME = "dating.db"


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
                photo_file_id TEXT
            )
        """)

        # --------------------------------------
        # МИГРАЦИЯ СТАРОЙ БАЗЫ
        # --------------------------------------

        columns = connection.execute(
            "PRAGMA table_info(users)"
        ).fetchall()

        column_names = {
            column["name"]
            for column in columns
        }

        if "photo_file_id" not in column_names:
            connection.execute("""
                ALTER TABLE users
                ADD COLUMN photo_file_id TEXT
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
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
    photo_file_id
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
                photo_file_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    city,
                )
            ).fetchall()

        return users

    finally:
        connection.close()


# ==========================================
# ПОЛУЧИТЬ СЛЕДУЮЩУЮ АНКЕТУ
# ==========================================

def get_next_profile(
    telegram_id,
    city,
    search_gender,
    age_min,
    age_max
):
    connection = get_connection()

    try:
        if search_gender == "all":
            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND age BETWEEN ? AND ?

                  AND telegram_id NOT IN (
                      SELECT viewed_id
                      FROM views
                      WHERE viewer_id = ?
                  )

                ORDER BY
                    CASE
                        WHEN city = ? THEN 0
                        ELSE 1
                    END,
                    RANDOM()

                LIMIT 1
                """,
                (
                    telegram_id,
                    age_min,
                    age_max,
                    telegram_id,
                    city,
                )
            ).fetchone()

        else:
            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id != ?
                  AND gender = ?
                  AND age BETWEEN ? AND ?

                  AND telegram_id NOT IN (
                      SELECT viewed_id
                      FROM views
                      WHERE viewer_id = ?
                  )

                ORDER BY
                    CASE
                        WHEN city = ? THEN 0
                        ELSE 1
                    END,
                    RANDOM()

                LIMIT 1
                """,
                (
                    telegram_id,
                    search_gender,
                    age_min,
                    age_max,
                    telegram_id,
                    city,
                )
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
        connection.execute(
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

                CASE
                    WHEN matches.user_one = ?
                    THEN matches.user_two
                    ELSE matches.user_one
                END AS other_user_id,

                users.name,
                users.age,
                users.gender,
                users.city,
                users.photo_file_id

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
            FROM messages
            WHERE match_id = ?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (
                match_id,
                limit,
            )
        ).fetchall()

        return messages

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