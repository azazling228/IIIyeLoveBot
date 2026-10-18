import hashlib
import hmac
import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import (
    add_like,
    add_message,
    add_skip,
    add_view,
    create_match,
    get_incoming_likes,
    get_match,
    get_matches,
    get_messages,
    get_next_profile,
    get_user,
    has_like,
    has_viewed,
    is_blocked,
    mark_messages_read,
    remove_like,
    reset_views,
    update_profile_fields,
)


MINIAPP_DIR = Path(__file__).resolve().parent / "miniapp"
MAX_INIT_DATA_AGE = 60 * 60 * 24
MAX_CHAT_MESSAGE_LENGTH = 3900


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


def _profile_payload(profile):
    return {
        "id": profile["telegram_id"],
        "name": profile["name"],
        "age": profile["age"],
        "gender": profile["gender"],
        "city": profile["city"],
        "description": profile["description"] or "",
        "has_photo": bool(profile["photo_file_id"]),
    }


def _chat_payload(chat):
    return {
        "id": chat["other_user_id"],
        "name": chat["name"],
        "age": chat["age"],
        "city": chat["city"],
        "description": chat["description"] or "",
        "has_photo": bool(chat["photo_file_id"]),
        "last_message": chat["last_message"] or "",
        "last_message_at": chat["last_message_at"] or chat["created_at"],
        "unread_count": chat["unread_count"],
    }


def _json_error(message, status):
    return web.json_response({"error": message}, status=status)


def create_miniapp_app(bot, bot_token):
    @web.middleware
    async def telegram_auth_middleware(request, handler):
        if request.path in {"/", "/app.js", "/style.css", "/healthz"}:
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

    app = web.Application(middlewares=[telegram_auth_middleware])

    async def index(_request):
        return web.FileResponse(MINIAPP_DIR / "index.html")

    async def script(_request):
        return web.FileResponse(MINIAPP_DIR / "app.js")

    async def styles(_request):
        return web.FileResponse(MINIAPP_DIR / "style.css")

    async def health(_request):
        return web.json_response({"status": "ok"})

    async def me(request):
        user = get_user(request["telegram_id"])
        if not user:
            return _json_error("Create a profile in the bot first.", 404)
        return web.json_response(_profile_payload(user))

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
        return web.json_response(_profile_payload(get_user(user_id)))

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
        return web.json_response({"profile": _profile_payload(profile)})

    async def profile_photo(request):
        try:
            profile_id = int(request.match_info["profile_id"])
        except ValueError:
            raise web.HTTPNotFound()
        user_id = request["telegram_id"]
        profile = get_user(profile_id)
        if (
            not profile
            or not profile["photo_file_id"]
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
            telegram_file = await bot.get_file(profile["photo_file_id"])
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

    async def discover_decision(request):
        user_id = request["telegram_id"]
        try:
            payload = await request.json()
            profile_id = int(payload["profile_id"])
            action = payload["action"]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return _json_error("A valid profile_id and action are required.", 400)
        if action not in {"like", "skip"}:
            return _json_error("Action must be like or skip.", 400)
        if profile_id == user_id or not has_viewed(user_id, profile_id):
            return _json_error("This profile is not available.", 404)
        profile = get_user(profile_id)
        if not profile or is_blocked(user_id, profile_id):
            return _json_error("This profile is not available.", 404)

        if action == "skip":
            add_skip(user_id, profile_id)
            return web.json_response({"matched": False})

        add_like(user_id, profile_id)
        matched = False
        if has_like(profile_id, user_id):
            create_match(user_id, profile_id)
            matched = True
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
            {"profiles": [_profile_payload(profile) for profile in get_incoming_likes(user_id)]}
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
        create_match(user_id, profile_id)
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
                    _chat_payload(chat)
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
                        **_chat_payload(match),
                        "matched_at": match["created_at"],
                    }
                    for match in get_matches(
                        user_id,
                        include_last_message=True,
                    )
                ]
            }
        )

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
                "partner": _profile_payload(get_user(partner_id)),
                "messages": [
                    {
                        "id": item["id"],
                        "sender_id": item["sender_id"],
                        "text": item["text"],
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
        message_id = add_message(match["id"], user_id, partner_id, text)
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
            logging.exception("Failed to deliver Mini App chat message")
            return web.json_response(
                {
                    "message_id": message_id,
                    "notification_warning": (
                        "Message saved, but Telegram could not notify the other person."
                    ),
                },
                status=201,
            )
        return web.json_response({"message_id": message_id}, status=201)

    async def _notify_like(recipient_id, sender_id):
        sender = get_user(sender_id)
        if not sender:
            return
        text = (
            f"❤️ Тебе поставили лайк!\n\n"
            f"👤 {sender['name'][:100]}, {sender['age']} лет\n"
            f"📍 {sender['city'][:100]}"
        )
        if sender["description"]:
            text += f"\n\n📝 {sender['description']}"
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
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/me", me)
    app.router.add_patch("/api/me", update_me)
    app.router.add_get("/api/discover", discover)
    app.router.add_post("/api/discover/reset", reset_discovery)
    app.router.add_post("/api/discover/decision", discover_decision)
    app.router.add_get("/api/profiles/{profile_id}/photo", profile_photo)
    app.router.add_get("/api/likes", incoming_likes)
    app.router.add_post("/api/likes/respond", respond_to_like)
    app.router.add_get("/api/chats", chats)
    app.router.add_get("/api/matches", matches)
    app.router.add_get("/api/chats/{partner_id}/messages", chat_messages)
    app.router.add_post("/api/chats/{partner_id}/messages", send_chat_message)
    return app


async def start_miniapp_server(bot, bot_token):
    app = create_miniapp_app(bot, bot_token)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Telegram Mini App web server listening on port %s", port)
    return runner
