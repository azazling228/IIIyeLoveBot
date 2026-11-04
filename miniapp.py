import hashlib
import hmac
import json
import logging
import os
import random
import re
import secrets
import time
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    add_like,
    add_message,
    add_skip,
    add_view,
    create_match,
    get_incoming_likes,
    get_match,
    get_message,
    get_matches,
    get_messages,
    get_next_profile,
    get_user,
    get_profile_photo_ids,
    get_connection,
    get_quiz_best_result,
    get_quiz_leaderboard,
    get_quiz_rating,
    quiz_account_status,
    start_quiz_session,
    finish_quiz_session,
    delete_quiz_results,
    update_quiz_title_visibility,
    has_like,
    has_viewed,
    is_blocked,
    message_matches_banned_words,
    mark_messages_read,
    delete_match,
    delete_user,
    remove_like,
    reset_views,
    update_profile_active,
    update_profile_preferences,
    update_search_settings,
    update_profile_fields,
    update_message_media_file_id,
)
from quiz_data import QUESTIONS, quiz_title


MINIAPP_DIR = Path(__file__).resolve().parent / "miniapp"
MAX_INIT_DATA_AGE = 60 * 60 * 24
MAX_CHAT_MESSAGE_LENGTH = 3900
MAX_CHAT_MEDIA_SIZE = 20 * 1024 * 1024
MAX_QUIZ_QUESTIONS = len(QUESTIONS)


def _current_quiz_month():
    moscow_time = datetime.now(timezone(timedelta(hours=3)))
    return moscow_time.strftime("%Y-%m")


def validate_init_data(init_data, bot_token, now=None):
    if not init_data or not bot_token:
        raise ValueError("Missing Telegram authentication data")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError("Duplicate Telegram authentication fields")
        received_hash = data.pop("hash")
        auth_date = int(data["auth_date"])
        telegram_user = json.loads(data["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Telegram authentication data") from exc

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise ValueError("Invalid Telegram authentication signature")

    current_time = int(time.time()) if now is None else now
    if auth_date > current_time + 30:
        raise ValueError("Telegram authentication date is in the future")
    if current_time - auth_date > MAX_INIT_DATA_AGE:
        raise ValueError("Telegram authentication data has expired")
    if not isinstance(telegram_user, dict) or type(telegram_user.get("id")) is not int:
        raise ValueError("Invalid Telegram user")

    return telegram_user


def _quiz_title_for_user(user_id, rating, admin_id, show_title=None):
    if show_title is None:
        show_title = rating.get("show_title", True) if rating else True
    if not show_title:
        return None
    if user_id == admin_id:
        return "Лега"
    return quiz_title(rating["percent"])["name"] if rating else None


def _profile_payload(profile, admin_id=None):
    rating = get_quiz_rating(profile["telegram_id"])
    photo_ids = get_profile_photo_ids(profile)
    return {
        "id": profile["telegram_id"],
        "name": profile["name"],
        "age": profile["age"],
        "gender": profile["gender"],
        "city": profile["city"],
        "description": profile["description"] or "",
        "has_photo": bool(photo_ids),
        "photos": [
            f"/api/profiles/{profile['telegram_id']}/photos/{index}"
            for index in range(len(photo_ids))
        ],
        "quiz_percent": rating["percent"] if rating else None,
        "quiz_title": _quiz_title_for_user(
            profile["telegram_id"],
            rating,
            admin_id,
            bool(profile["quiz_show_title"]),
        ),
    }


def _chat_payload(chat, admin_id=None):
    rating = get_quiz_rating(chat["other_user_id"])
    return {
        "id": chat["other_user_id"],
        "name": chat["name"],
        "age": chat["age"],
        "gender": chat["gender"],
        "city": chat["city"],
        "description": chat["description"] or "",
        "has_photo": bool(chat["photo_file_id"]),
        "last_message": chat["last_message"] or "",
        "last_message_at": chat["last_message_at"] or chat["created_at"],
        "unread_count": chat["unread_count"],
        "quiz_percent": rating["percent"] if rating else None,
        "quiz_title": _quiz_title_for_user(
            chat["other_user_id"],
            rating,
            admin_id,
            bool(chat["quiz_show_title"]),
        ),
    }


def _json_error(message, status):
    return web.json_response({"error": message}, status=status)


def create_miniapp_app(bot, bot_token, admin_id=None):
    @web.middleware
    async def telegram_auth_middleware(request, handler):
        if request.path in {
            "/",
            "/app.js",
            "/style.css",
            "/healthz",
            "/legal",
        }:
            return await handler(request)
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("tma "):
            return _json_error("Open this app from Telegram.", 401)
        try:
            telegram_user = validate_init_data(
                authorization[4:],
                bot_token,
            )
        except ValueError:
            logging.warning("Rejected invalid Telegram Mini App initData")
            return _json_error("Telegram authorization expired. Reopen the app.", 401)
        request["telegram_user"] = telegram_user
        request["telegram_id"] = telegram_user["id"]
        return await handler(request)

    app = web.Application(
        middlewares=[telegram_auth_middleware],
        client_max_size=MAX_CHAT_MEDIA_SIZE + 64 * 1024,
    )

    def static_file(path):
        return web.FileResponse(
            MINIAPP_DIR / path,
            headers={"Cache-Control": "no-store"},
        )

    async def index(_request):
        return static_file("index.html")

    async def script(_request):
        return static_file("app.js")

    async def styles(_request):
        return static_file("style.css")

    async def legal(_request):
        return static_file("legal.html")

    async def health(_request):
        return web.json_response({"status": "ok"})

    async def me(request):
        user = get_user(request["telegram_id"])
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        quiz_status = quiz_account_status(
            user["telegram_id"],
            _current_quiz_month(),
            is_admin=user["telegram_id"] == admin_id,
        )
        best_result = get_quiz_best_result(user["telegram_id"])
        rating = get_quiz_rating(user["telegram_id"])
        return web.json_response(
            {
                **_profile_payload(user, admin_id),
                "search_gender": user["search_gender"],
                "search_age_min": user["search_age_min"],
                "search_age_max": user["search_age_max"],
                "match_count": len(get_matches(user["telegram_id"])),
                "like_count": user["total_likes_received"],
                "is_active": bool(user["is_active"]),
                "notify_likes": bool(user["notify_likes"]),
                "notify_matches": bool(user["notify_matches"]),
                "notify_messages": bool(user["notify_messages"]),
                "banned_words": user["banned_words"] or "",
                "quiz_attempts_remaining": quiz_status["attempts_remaining"],
                "quiz_show_title": quiz_status["show_title"],
                "quiz_percent": rating["percent"] if rating else None,
                "quiz_title": _quiz_title_for_user(
                    user["telegram_id"],
                    rating,
                    admin_id,
                    quiz_status["show_title"],
                ),
                "quiz_unlimited_attempts": quiz_status["unlimited_attempts"],
                "quiz_best_score": best_result["score"] if best_result else None,
                "quiz_total_questions": (
                    best_result["total_questions"] if best_result else None
                ),
            }
        )

    async def quiz_status(request):
        user_id = request["telegram_id"]
        user = get_user(user_id)
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        account = quiz_account_status(
            user_id,
            _current_quiz_month(),
            is_admin=user_id == admin_id,
        )
        best = get_quiz_best_result(user_id)
        rating = get_quiz_rating(user_id)
        return web.json_response(
            {
                **account,
                "best_score": best["score"] if best else None,
                "total_questions": best["total_questions"] if best else None,
                "percent": rating["percent"] if rating else None,
                "title": _quiz_title_for_user(
                    user_id,
                    rating,
                    admin_id,
                    account["show_title"],
                ),
                "has_result": best is not None,
                "question_count": MAX_QUIZ_QUESTIONS,
            }
        )

    async def quiz_start(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Create a profile in the bot first.", 404)
        questions = []
        for source in QUESTIONS:
            options = [
                {"id": option_id, "text": text}
                for option_id, text in source["options"]
            ]
            random.shuffle(options)
            questions.append(
                {
                    "id": source["id"],
                    "question": source["question"],
                    "options": options,
                    "correct": source["correct"],
                }
            )
        random.shuffle(questions)
        session_id = secrets.token_urlsafe(24)
        attempts_remaining = start_quiz_session(
            user_id,
            session_id,
            json.dumps(questions, ensure_ascii=False),
            _current_quiz_month(),
            is_admin=user_id == admin_id,
        )
        if attempts_remaining is None:
            return _json_error("Profile not found.", 404)
        if not attempts_remaining["started"]:
            return web.json_response(
                {"error": "Попыток пока нет. Новая попытка появится первого числа месяца."},
                status=409,
            )
        return web.json_response(
            {
                "session_id": session_id,
                "attempts_remaining": attempts_remaining["attempts_remaining"],
                "unlimited_attempts": attempts_remaining["unlimited_attempts"],
                "questions": [
                    {
                        "id": question["id"],
                        "question": question["question"],
                        "options": question["options"],
                    }
                    for question in questions
                ],
            }
        )

    async def quiz_submit(request):
        user_id = request["telegram_id"]
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("Valid quiz answers are required.", 400)
        if not isinstance(payload, dict):
            return _json_error("Valid quiz answers are required.", 400)
        session_id = payload.get("session_id")
        answers = payload.get("answers")
        if (
            not isinstance(session_id, str)
            or not isinstance(answers, dict)
            or len(session_id) > 100
            or any(
                not isinstance(question_id, str)
                or not isinstance(option_id, str)
                for question_id, option_id in answers.items()
            )
        ):
            return _json_error("Valid quiz answers are required.", 400)
        connection = get_connection()
        try:
            row = connection.execute(
                """
                SELECT questions_json
                FROM quiz_sessions
                WHERE session_id = ? AND user_id = ?
                """,
                (session_id, user_id),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return _json_error("Quiz session expired or already submitted.", 404)
        questions = json.loads(row["questions_json"])
        expected_ids = {question["id"] for question in questions}
        if set(answers) != expected_ids:
            return _json_error("Answer every question before submitting.", 400)
        if any(
            answer not in {option["id"] for option in question["options"]}
            for question in questions
            for answer in (answers[question["id"]],)
        ):
            return _json_error("One or more answers are invalid.", 400)
        score = sum(
            answers[question["id"]] == question["correct"]
            for question in questions
        )
        best = finish_quiz_session(
            session_id,
            user_id,
            score,
            len(questions),
        )
        if not best:
            return _json_error("Quiz session expired or already submitted.", 404)
        best_percent = best["percent"]
        return web.json_response(
            {
                "score": score,
                "total_questions": len(questions),
                "percent": round(100 * score / len(questions)),
                "best_score": best["score"],
                "best_percent": best_percent,
                "title": _quiz_title_for_user(
                    user_id,
                    {"percent": round(100 * score / len(questions))},
                    admin_id,
                ),
                "best_title": _quiz_title_for_user(
                    user_id,
                    {"percent": best_percent},
                    admin_id,
                ),
            }
        )

    async def quiz_leaderboard(request):
        gender = request.query.get("gender", "all")
        if gender not in {"all", "male", "female"}:
            return _json_error("Gender must be all, male or female.", 400)
        entries = get_quiz_leaderboard(
            None if gender == "all" else gender,
            excluded_user_id=admin_id,
        )
        return web.json_response(
            {
                "entries": [
                    {
                        "rank": rank,
                        "id": entry["telegram_id"],
                        "name": entry["name"],
                        "gender": entry["gender"],
                        "percent": entry["percent"],
                        "score": entry["score"],
                        "total_questions": entry["total_questions"],
                        "title": (
                            quiz_title(entry["percent"])["name"]
                            if entry["quiz_show_title"]
                            else None
                        ),
                        "title_class": (
                            quiz_title(entry["percent"])["class"]
                            if entry["quiz_show_title"]
                            else None
                        ),
                    }
                    for rank, entry in enumerate(entries, start=1)
                ]
            }
        )

    async def quiz_delete_result(request):
        delete_quiz_results(request["telegram_id"])
        return web.json_response({"deleted": True})

    async def quiz_title_setting(request):
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("A valid title visibility setting is required.", 400)
        if not isinstance(payload, dict) or type(payload.get("visible")) is not bool:
            return _json_error("visible must be true or false.", 400)
        if not update_quiz_title_visibility(
            request["telegram_id"],
            payload["visible"],
        ):
            return _json_error("Profile not found.", 404)
        return web.json_response({"show_title": payload["visible"]})

    async def update_me(request):
        user_id = request["telegram_id"]
        user = get_user(user_id)
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("A valid profile is required.", 400)
        if not isinstance(payload, dict) or set(payload) != {
            "name",
            "city",
            "description",
        }:
            return _json_error(
                "Name, city, and description are required.", 400
            )
        name = payload["name"]
        city = payload["city"]
        description = payload["description"]
        if not isinstance(name, str) or not 2 <= len(name.strip()) <= 100:
            return _json_error("Name must contain 2 to 100 characters.", 400)
        if not isinstance(city, str) or not 2 <= len(city.strip()) <= 100:
            return _json_error("City must contain 2 to 100 characters.", 400)
        if not isinstance(description, str) or len(description.strip()) > 1000:
            return _json_error("Description can contain up to 1000 characters.", 400)
        if not update_profile_fields(
            user_id,
            name.strip(),
            city.strip(),
            description.strip(),
        ):
            return _json_error("Profile not found.", 404)
        return web.json_response(_profile_payload(get_user(user_id), admin_id))

    async def update_search(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Create a profile in the bot first.", 404)
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("Valid search settings are required.", 400)
        if not isinstance(payload, dict) or set(payload) != {
            "search_gender",
            "search_age_min",
            "search_age_max",
        }:
            return _json_error(
                "Gender and minimum and maximum ages are required.", 400
            )
        search_gender = payload["search_gender"]
        age_min = payload["search_age_min"]
        age_max = payload["search_age_max"]
        if not isinstance(search_gender, str) or search_gender not in {
            "male",
            "female",
            "all",
        }:
            return _json_error("Gender must be male, female, or all.", 400)
        if type(age_min) is not int or type(age_max) is not int:
            return _json_error("Ages must be whole numbers.", 400)
        if not 18 <= age_min <= 100 or not 18 <= age_max <= 100:
            return _json_error("Ages must be between 18 and 100.", 400)
        if age_max < age_min:
            return _json_error("Maximum age cannot be less than minimum age.", 400)
        update_search_settings(user_id, search_gender, age_min, age_max)
        return web.json_response(
            {
                "search_gender": search_gender,
                "search_age_min": age_min,
                "search_age_max": age_max,
            }
        )

    async def update_profile_preferences_endpoint(request):
        user_id = request["telegram_id"]
        user = get_user(user_id)
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("Valid profile preferences are required.", 400)
        expected_fields = {
            "notify_likes",
            "notify_matches",
            "notify_messages",
            "banned_words",
        }
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            return _json_error("All notification and ban-word settings are required.", 400)
        if any(type(payload[field]) is not bool for field in (
            "notify_likes",
            "notify_matches",
            "notify_messages",
        )):
            return _json_error("Notification settings must be true or false.", 400)
        banned_words = payload["banned_words"]
        if not isinstance(banned_words, str) or len(banned_words) > 1000:
            return _json_error("Ban-word list must not exceed 1000 characters.", 400)
        words = []
        seen_words = set()
        for line in banned_words.splitlines():
            word = " ".join(line.split())
            if not word:
                continue
            if len(word) > 100:
                return _json_error("Each ban word or phrase must be at most 100 characters.", 400)
            normalized = word.casefold()
            if normalized not in seen_words:
                seen_words.add(normalized)
                words.append(word)
        normalized_words = "\n".join(words)
        if not update_profile_preferences(
            user_id,
            payload["notify_likes"],
            payload["notify_matches"],
            payload["notify_messages"],
            normalized_words,
        ):
            return _json_error("Profile not found.", 404)
        return web.json_response(
            {
                "notify_likes": payload["notify_likes"],
                "notify_matches": payload["notify_matches"],
                "notify_messages": payload["notify_messages"],
                "banned_words": normalized_words,
            }
        )

    async def update_account_status(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Profile not found.", 404)
        try:
            payload = await request.json()
        except (TypeError, json.JSONDecodeError):
            return _json_error("A valid active status is required.", 400)
        if not isinstance(payload, dict) or type(payload.get("is_active")) is not bool:
            return _json_error("is_active must be true or false.", 400)
        if not update_profile_active(user_id, payload["is_active"]):
            return _json_error("Profile not found.", 404)
        return web.json_response({"is_active": payload["is_active"]})

    async def delete_account(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Profile not found.", 404)
        former_matches = get_matches(user_id)
        if not delete_user(user_id):
            return _json_error("Profile could not be deleted.", 500)
        for match in former_matches:
            partner_id = match["other_user_id"]
            try:
                await bot.send_message(
                    partner_id,
                    "Профиль собеседника удалён. Мэтч и переписка в приложении больше недоступны.",
                )
            except TelegramAPIError:
                logging.exception(
                    "Failed to notify user about deleted Mini App profile"
                )
        return web.json_response({"deleted": True})

    async def discover(request):
        user = get_user(request["telegram_id"])
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        profile = get_next_profile(
            telegram_id=user["telegram_id"],
            city=user["city"],
            search_gender=user["search_gender"],
            age_min=user["search_age_min"],
            age_max=user["search_age_max"],
        )
        if not profile:
            return web.json_response({"profile": None})
        add_view(user["telegram_id"], profile["telegram_id"])
        return web.json_response({"profile": _profile_payload(profile, admin_id)})

    async def profile_photo(request):
        try:
            profile_id = int(request.match_info["profile_id"])
            photo_index = int(request.match_info.get("photo_index", 0))
        except ValueError:
            raise web.HTTPNotFound()
        user_id = request["telegram_id"]
        profile = get_user(profile_id)
        photo_ids = get_profile_photo_ids(profile) if profile else []
        if (
            not profile
            or photo_index < 0
            or photo_index >= len(photo_ids)
            or is_blocked(user_id, profile_id)
            or (
                profile_id != user_id
                and not has_viewed(user_id, profile_id)
                and not get_match(user_id, profile_id)
                and not has_like(profile_id, user_id)
                and not has_like(user_id, profile_id)
            )
        ):
            raise web.HTTPNotFound()
        try:
            telegram_file = await bot.get_file(photo_ids[photo_index])
            image = BytesIO()
            await bot.download_file(telegram_file.file_path, destination=image)
        except TelegramAPIError:
            logging.exception("Failed to retrieve Mini App profile photo")
            raise web.HTTPBadGateway(text="Could not load profile photo")
        return web.Response(
            body=image.getvalue(),
            content_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )

    async def public_profile(request):
        user_id = request["telegram_id"]
        try:
            profile_id = int(request.match_info["profile_id"])
        except ValueError:
            return _json_error("Profile not found.", 404)
        profile = get_user(profile_id)
        if (
            not profile
            or profile_id == user_id
            or is_blocked(user_id, profile_id)
        ):
            return _json_error("Profile not found.", 404)
        return web.json_response({"profile": _profile_payload(profile, admin_id)})

    async def discover_decision(request):
        user_id = request["telegram_id"]
        try:
            payload = await request.json()
            profile_id = int(payload["profile_id"])
            action = payload["action"]
            like_message = payload.get("message", "")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return _json_error("A valid profile_id and action are required.", 400)
        if action not in {"like", "skip"}:
            return _json_error("Action must be like or skip.", 400)
        if not isinstance(like_message, str) or len(like_message.strip()) > 500:
            return _json_error("A like message can contain up to 500 characters.", 400)
        like_message = like_message.strip()
        if profile_id == user_id or not has_viewed(user_id, profile_id):
            return _json_error("This profile is not available.", 404)
        profile = get_user(profile_id)
        if not profile or is_blocked(user_id, profile_id):
            return _json_error("This profile is not available.", 404)

        if action == "skip":
            add_skip(user_id, profile_id)
            return web.json_response({"matched": False})

        add_like(user_id, profile_id, like_message)
        matched = False
        if has_like(profile_id, user_id):
            new_match = create_match(user_id, profile_id)
            matched = True
            if new_match and profile["notify_matches"]:
                try:
                    await bot.send_message(
                        profile_id,
                        f"💘 У вас мэтч с {get_user(user_id)['name'][:100]}! "
                        "Вы можете продолжить общение в боте или приложении.",
                    )
                except TelegramAPIError:
                    logging.exception("Failed to notify user about Mini App match")
        else:
            await _notify_like(profile_id, user_id)
        return web.json_response({"matched": matched})

    async def incoming_likes(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Create a profile in the bot first.", 404)
        return web.json_response(
            {
                "profiles": [
                    {
                        **_profile_payload(profile, admin_id),
                        "like_message": profile["like_message"] or "",
                    }
                    for profile in get_incoming_likes(user_id)
                ]
            }
        )

    async def respond_to_like(request):
        user_id = request["telegram_id"]
        try:
            payload = await request.json()
            profile_id = int(payload["profile_id"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return _json_error("A valid profile_id is required.", 400)
        action = payload.get("action", "like")
        profile = get_user(profile_id)
        if (
            profile_id == user_id
            or not profile
            or not has_like(profile_id, user_id)
            or is_blocked(user_id, profile_id)
        ):
            return _json_error("This like is no longer available.", 404)
        if action == "skip":
            remove_like(profile_id, user_id)
            return web.json_response({"matched": False})
        if action != "like":
            return _json_error("Action must be like or skip.", 400)
        add_like(user_id, profile_id)
        new_match = create_match(user_id, profile_id)
        if new_match and profile["notify_matches"]:
            try:
                await bot.send_message(
                    profile_id,
                    f"💘 У вас мэтч с {get_user(user_id)['name'][:100]}! "
                    "Вы можете продолжить общение в боте или приложении.",
                )
            except TelegramAPIError:
                logging.exception("Failed to notify user about Mini App match")
        return web.json_response({"matched": True})

    async def chats(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Create a profile in the bot first.", 404)
        return web.json_response(
            {
                "chats": [
                    _chat_payload(chat, admin_id)
                    for chat in get_matches(user_id, include_last_message=True)
                ]
            }
        )

    async def matches(request):
        user_id = request["telegram_id"]
        if not get_user(user_id):
            return _json_error("Create a profile in the bot first.", 404)
        return web.json_response(
            {
                "matches": [
                    {
                        **_chat_payload(match, admin_id),
                        "matched_at": match["created_at"],
                    }
                    for match in get_matches(
                        user_id,
                        include_last_message=True,
                    )
                ]
            }
        )

    async def delete_match_endpoint(request):
        user_id = request["telegram_id"]
        try:
            partner_id = int(request.match_info["partner_id"])
        except ValueError:
            return _json_error("Invalid match.", 400)
        if partner_id == user_id:
            return _json_error("Invalid match.", 400)
        partner = get_user(partner_id)
        if not partner or not delete_match(user_id, partner_id):
            return _json_error("This match is no longer available.", 404)
        try:
            await bot.send_message(
                partner_id,
                "💔 Ваш мэтч был удалён. История переписки больше недоступна.",
            )
        except TelegramAPIError:
            logging.exception("Failed to notify user about removed Mini App match")
        return web.json_response({"deleted": True})

    async def reset_discovery(request):
        reset_views(request["telegram_id"])
        return await discover(request)

    async def chat_messages(request):
        user_id = request["telegram_id"]
        try:
            partner_id = int(request.match_info["partner_id"])
        except ValueError:
            return _json_error("Invalid chat.", 400)
        match = get_match(user_id, partner_id)
        if not match or is_blocked(user_id, partner_id):
            return _json_error("This chat is not available.", 404)
        history = get_messages(match["id"], limit=100)
        mark_messages_read(match["id"], user_id)
        return web.json_response(
            {
                "partner": _profile_payload(get_user(partner_id), admin_id),
                "messages": [
                    {
                        "id": item["id"],
                        "sender_id": item["sender_id"],
                        "text": item["text"],
                        "media_type": item["media_type"],
                        "media_url": (
                            f"/api/chats/{partner_id}/messages/{item['id']}/media"
                            if item["media_type"] != "text"
                            else None
                        ),
                        "created_at": item["created_at"],
                    }
                    for item in history
                ],
            }
        )

    async def send_chat_message(request):
        user_id = request["telegram_id"]
        try:
            partner_id = int(request.match_info["partner_id"])
            payload = await request.json()
            text = payload["text"].strip()
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, AttributeError):
            return _json_error("A valid chat message is required.", 400)
        if not text or len(text) > MAX_CHAT_MESSAGE_LENGTH:
            return _json_error(
                f"Message must contain 1 to {MAX_CHAT_MESSAGE_LENGTH} characters.",
                400,
            )
        match = get_match(user_id, partner_id)
        partner = get_user(partner_id)
        user = get_user(user_id)
        if not match or not partner or not user or is_blocked(user_id, partner_id):
            return _json_error("This chat is not available.", 404)
        if message_matches_banned_words(text, partner_id):
            return web.json_response({"filtered": True}, status=200)
        message_id = add_message(match["id"], user_id, partner_id, text)
        if partner["notify_messages"]:
            try:
                await bot.send_message(
                    partner_id,
                    f"💬 Сообщение от {user['name'][:100]}:\n\n{text}",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="💬 Ответить",
                                    callback_data=f"chat_{user_id}",
                                )
                            ]
                        ]
                    ),
                )
            except TelegramAPIError:
                logging.exception("Failed to deliver Mini App chat notification")
                return web.json_response(
                    {
                        "message_id": message_id,
                        "notification_warning": (
                            "Message saved, but Telegram could not notify the other person."
                        ),
                    },
                    status=201,
                )
        response = {"message_id": message_id}
        if not partner["notify_messages"]:
            response["notification_disabled"] = True
        return web.json_response(response, status=201)

    async def send_chat_media(request):
        user_id = request["telegram_id"]
        try:
            partner_id = int(request.match_info["partner_id"])
            form = await request.post()
            upload = form.get("file")
            caption = form.get("caption", "").strip()
        except (ValueError, TypeError, AttributeError):
            return _json_error("A valid image or audio file is required.", 400)
        if not upload or not hasattr(upload, "file"):
            return _json_error("Choose an image or audio file to send.", 400)
        if not isinstance(caption, str):
            return _json_error("Message caption must be text.", 400)
        if len(caption) > 900:
            return _json_error("A media caption can contain up to 900 characters.", 400)
        try:
            media_data = upload.file.read(MAX_CHAT_MEDIA_SIZE + 1)
        except OSError:
            logging.exception("Failed to read Mini App chat attachment")
            return _json_error("Could not read the selected file.", 400)
        if not media_data or len(media_data) > MAX_CHAT_MEDIA_SIZE:
            return _json_error("Files must be between 1 byte and 20 MB.", 400)

        media_mime_type = (upload.content_type or "").lower()
        if not re.fullmatch(r"(?:image|audio)/[a-z0-9][a-z0-9.+-]*", media_mime_type):
            return _json_error("The selected file has an invalid media type.", 400)
        if media_mime_type.startswith("image/"):
            media_type = "photo"
        elif media_mime_type.startswith("audio/"):
            media_type = "audio"
        else:
            return _json_error("Only image and audio files can be sent.", 400)

        match = get_match(user_id, partner_id)
        partner = get_user(partner_id)
        user = get_user(user_id)
        if not match or not partner or not user or is_blocked(user_id, partner_id):
            return _json_error("This chat is not available.", 404)
        if message_matches_banned_words(caption, partner_id):
            return web.json_response({"filtered": True}, status=200)

        raw_filename = upload.filename or ("photo" if media_type == "photo" else "audio")
        media_file_name = re.sub(
            r"[\x00-\x1f\x7f]",
            "",
            raw_filename.replace("\\", "/").rsplit("/", 1)[-1],
        )[:128]
        if not media_file_name:
            media_file_name = "photo" if media_type == "photo" else "audio"
        message_id = add_message(
            match["id"],
            user_id,
            partner_id,
            caption,
            media_type=media_type,
            media_data=media_data,
            media_mime_type=media_mime_type,
            media_file_name=media_file_name,
        )
        response = {"message_id": message_id}
        if partner["notify_messages"]:
            notification_caption = (
                f"{'📷 Фото' if media_type == 'photo' else '🎧 Аудио'} "
                f"от {user['name'][:100]}"
            )
            if caption:
                notification_caption += f"\n\n{caption}"
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Ответить",
                            callback_data=f"chat_{user_id}",
                        )
                    ]
                ]
            )
            try:
                input_file = BufferedInputFile(media_data, filename=media_file_name)
                if media_type == "photo" and media_mime_type in {
                    "image/jpeg",
                    "image/png",
                }:
                    sent = await bot.send_photo(
                        partner_id,
                        input_file,
                        caption=notification_caption[:1024],
                        reply_markup=reply_markup,
                    )
                    stored_file_id = sent.photo[-1].file_id
                else:
                    sent = await bot.send_document(
                        partner_id,
                        input_file,
                        caption=notification_caption[:1024],
                        reply_markup=reply_markup,
                    )
                    stored_file_id = sent.document.file_id
                update_message_media_file_id(message_id, stored_file_id)
            except TelegramAPIError:
                logging.exception("Failed to deliver Mini App chat attachment")
                response["notification_warning"] = (
                    "Файл сохранён в чате, но Telegram не смог доставить его собеседнику."
                )
        else:
            response["notification_disabled"] = True
        return web.json_response(response, status=201)

    async def chat_media(request):
        user_id = request["telegram_id"]
        try:
            partner_id = int(request.match_info["partner_id"])
            message_id = int(request.match_info["message_id"])
        except ValueError:
            return _json_error("Invalid chat attachment.", 400)
        match = get_match(user_id, partner_id)
        if not match or is_blocked(user_id, partner_id):
            return _json_error("This chat is not available.", 404)
        message = get_message(match["id"], message_id)
        if not message or message["media_type"] not in {"photo", "audio"}:
            return _json_error("Attachment not found.", 404)

        if message["media_data"] is not None:
            media_data = message["media_data"]
        elif message["media_file_id"]:
            try:
                telegram_file = await bot.get_file(message["media_file_id"])
                image = BytesIO()
                await bot.download_file(telegram_file.file_path, destination=image)
                media_data = image.getvalue()
            except TelegramAPIError:
                logging.exception("Failed to retrieve chat attachment from Telegram")
                return _json_error("Could not load this attachment.", 502)
        else:
            return _json_error("Attachment is unavailable.", 404)

        content_type = message["media_mime_type"] or "application/octet-stream"
        return web.Response(
            body=media_data,
            content_type=content_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def _notify_like(recipient_id, sender_id):
        sender = get_user(sender_id)
        recipient = get_user(recipient_id)
        if not sender or not recipient or not recipient["notify_likes"]:
            return
        text = (
            f"❤️ Тебе поставили лайк!\n\n"
            f"👤 {sender['name'][:100]}, {sender['age']} лет\n"
            f"📍 {sender['city'][:100]}"
        )
        if sender["description"]:
            text += f"\n\n📝 {sender['description']}"
        incoming_like = next(
            (
                profile["like_message"]
                for profile in get_incoming_likes(recipient_id)
                if profile["telegram_id"] == sender_id
            ),
            "",
        )
        if incoming_like:
            text += f"\n\n💌 Сообщение для тебя: {incoming_like}"
        text += "\n\nХочешь поставить лайк в ответ?"
        try:
            await bot.send_message(
                recipient_id,
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="❤️ Лайкнуть в ответ",
                                callback_data=f"like_back_{sender_id}",
                            )
                        ]
                    ]
                ),
            )
        except TelegramAPIError:
            logging.exception("Failed to notify user about Mini App like")

    app.router.add_get("/", index)
    app.router.add_get("/app.js", script)
    app.router.add_get("/style.css", styles)
    app.router.add_get("/legal", legal)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/quiz", quiz_status)
    app.router.add_post("/api/quiz/start", quiz_start)
    app.router.add_post("/api/quiz/submit", quiz_submit)
    app.router.add_get("/api/quiz/leaderboard", quiz_leaderboard)
    app.router.add_delete("/api/quiz/result", quiz_delete_result)
    app.router.add_patch("/api/quiz/title-visibility", quiz_title_setting)
    app.router.add_patch("/api/me", update_me)
    app.router.add_patch("/api/search-settings", update_search)
    app.router.add_patch(
        "/api/profile-preferences",
        update_profile_preferences_endpoint,
    )
    app.router.add_patch("/api/account/status", update_account_status)
    app.router.add_delete("/api/account", delete_account)
    app.router.add_get("/api/discover", discover)
    app.router.add_post("/api/discover/reset", reset_discovery)
    app.router.add_post("/api/discover/decision", discover_decision)
    app.router.add_get("/api/profiles/{profile_id}/photo", profile_photo)
    app.router.add_get("/api/profiles/{profile_id}/photos/{photo_index}", profile_photo)
    app.router.add_get("/api/profiles/{profile_id}", public_profile)
    app.router.add_get("/api/likes", incoming_likes)
    app.router.add_post("/api/likes/respond", respond_to_like)
    app.router.add_get("/api/chats", chats)
    app.router.add_get("/api/matches", matches)
    app.router.add_delete(
        "/api/matches/{partner_id}",
        delete_match_endpoint,
    )
    app.router.add_get("/api/chats/{partner_id}/messages", chat_messages)
    app.router.add_post("/api/chats/{partner_id}/messages", send_chat_message)
    app.router.add_post("/api/chats/{partner_id}/media", send_chat_media)
    app.router.add_get(
        "/api/chats/{partner_id}/messages/{message_id}/media",
        chat_media,
    )
    return app


async def start_miniapp_server(bot, bot_token, admin_id=None):
    app = create_miniapp_app(bot, bot_token, admin_id)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Telegram Mini App web server listening on port %s", port)
    return runner
