import asyncio
import logging
import os
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramAPIError
from database import (
    init_database,
    get_user,
    create_user,
    get_next_profile,
    add_view,
    add_like,
    has_like,
    is_mutual_like,
    create_match,
    get_matches,
    get_match,
    add_message,
    delete_user,
    get_connection,
    update_search_settings,
    add_skip,
    undo_last_skip,
    reset_views,
    get_incoming_likes,
    remove_like,
    add_block,
    is_blocked,
    add_report,
    mark_messages_read,
    get_messages,
    delete_match,
    update_profile_city,
    update_profile_photo,
    is_report_notified,
    mark_report_notified,
)

# ==========================================
# НАСТРОЙКИ
# ==========================================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "Не найден BOT_TOKEN в файле .env"
    )
BOT_ADMIN_ID = os.getenv("BOT_ADMIN_ID")
try:
    BOT_ADMIN_ID = int(BOT_ADMIN_ID) if BOT_ADMIN_ID else None
except ValueError:
    raise ValueError("BOT_ADMIN_ID должен быть числом в файле .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def limit_caption(text, max_length=1024):
    return text[:max_length]

# ==========================================
# СОСТОЯНИЯ
# ==========================================

class Registration(StatesGroup):
    captcha = State()
    name = State()
    age = State()
    gender = State()
    city = State()
    search_gender = State()
    search_age_min = State()
    search_age_max = State()
    description = State()
    photo = State()
    edit_name = State()
    edit_description = State()
    edit_photo = State()
    edit_city = State()
    # Настройки поиска
    settings_gender = State()
    settings_age_min = State()
    settings_age_max = State()

class ChatState(StatesGroup):
    chatting = State()

# ==========================================
# КЛАВИАТУРЫ
# ==========================================

gender_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="👨 Парень"),
            KeyboardButton(text="👩 Девушка"),
        ]
    ],
    resize_keyboard=True,
)

search_gender_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="👨 Парни"),
            KeyboardButton(text="👩 Девушки"),
        ],
        [
            KeyboardButton(text="❤️ Все"),
        ],
    ],
    resize_keyboard=True,
)

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="💘 Знакомства"),
            KeyboardButton(text="💞 Мои мэтчи"),
        ],
        [
            KeyboardButton(text="❤️ Кто меня лайкнул"),
            KeyboardButton(text="↩️ Вернуть анкету"),
        ],
        [
            KeyboardButton(text="🔄 Показать анкеты заново"),
        ],
        [
            KeyboardButton(text="👤 Моя анкета"),
        ],
        [
            KeyboardButton(text="⚙️ Настройки поиска"),
        ],
    ],
    resize_keyboard=True,
)

chat_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="↩️ Выйти из чата"),
        ]
    ],
    resize_keyboard=True,
)

# ==========================================
# КАПЧА
# ==========================================

CAPTCHA_SYMBOLS = [
    "🍎",
    "🍋",
    "🍉",
    "🍓",
    "🍒",
    "🍌",
    "🍇",
    "🥝",
]

def create_captcha():
    target = random.choice(CAPTCHA_SYMBOLS)
    options = random.sample(CAPTCHA_SYMBOLS, 4)
    if target not in options:
        options[random.randrange(4)] = target
    random.shuffle(options)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=options[0]),
                KeyboardButton(text=options[1]),
            ],
            [
                KeyboardButton(text=options[2]),
                KeyboardButton(text=options[3]),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    return target, keyboard

# ==========================================
# INLINE-КЛАВИАТУРЫ
# ==========================================

def create_profile_keyboard(profile_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Нравится",
                    callback_data=f"like_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Пропустить",
                    callback_data=f"skip_{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"block_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=f"report_{profile_id}",
                ),
            ],
        ]
    )

def create_like_back_keyboard(profile_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Лайкнуть в ответ",
                    callback_data=f"like_back_{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Пропустить",
                    callback_data=f"skip_like_{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"block_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=f"report_{profile_id}",
                ),
            ],
        ]
    )

def create_my_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Имя",
                    callback_data="profile_edit_name",
                ),
                InlineKeyboardButton(
                    text="📝 Описание",
                    callback_data="profile_edit_description",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📸 Фото",
                    callback_data="profile_edit_photo",
                ),
                InlineKeyboardButton(
                    text="📍 Город",
                    callback_data="profile_edit_city",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить анкету",
                    callback_data="delete_profile",
                )
            ],
        ]
    )

def create_delete_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Да, удалить",
                    callback_data="delete_profile_yes",
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data="delete_profile_no",
                ),
            ]
        ]
    )

def create_match_action_keyboard(profile_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Написать",
                    callback_data=f"chat_{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💞 Мои мэтчи",
                    callback_data="my_matches",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💔 Удалить мэтч",
                    callback_data=f"unmatch_{profile_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data=f"block_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=f"report_{profile_id}",
                ),
            ],
        ]
    )

def create_unmatch_confirm_keyboard(profile_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💔 Да, удалить мэтч",
                    callback_data=f"confirm_unmatch_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=f"cancel_unmatch_{profile_id}",
                ),
            ]
        ]
    )

def create_block_confirm_keyboard(profile_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Да, заблокировать",
                    callback_data=f"confirm_block_{profile_id}",
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=f"cancel_block_{profile_id}",
                ),
            ]
        ]
    )

# ==========================================
# /START
# ==========================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
):
    user = get_user(message.from_user.id)
    await state.clear()
    if user:
        await message.answer(
            f"С возвращением, {user['name']}! ❤️\n\n"
            "Твоя анкета уже существует.",
            reply_markup=main_keyboard,
        )
        return
    target, keyboard = create_captcha()
    await state.set_state(Registration.captcha)
    await state.update_data(captcha_target=target)
    await message.answer(
        "Привет! 👋\n\n"
        "Добро пожаловать в наш бот знакомств ❤️\n\n"
        "Перед созданием анкеты нужно пройти "
        "небольшую проверку.\n\n"
        f"🤖 Нажми кнопку с символом {target}",
        reply_markup=keyboard,
    )

# ==========================================
# КАПЧА
# ==========================================

@dp.message(Registration.captcha)
async def captcha_handler(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()
    target = data.get("captcha_target")
    if not target:
        target, keyboard = create_captcha()
        await state.update_data(captcha_target=target)
        await message.answer(
            "🤖 Давай попробуем ещё раз.\n\n"
            f"Нажми кнопку с символом {target}",
            reply_markup=keyboard,
        )
        return
    if message.text != target:
        target, keyboard = create_captcha()
        await state.update_data(captcha_target=target)
        await message.answer(
            "❌ Неверно.\n\n"
            "Пройди проверку ещё раз.\n\n"
            f"Нажми кнопку с символом {target}",
            reply_markup=keyboard,
        )
        return
    await state.update_data(captcha_passed=True)
    await state.set_state(Registration.name)
    await message.answer(
        "✅ Проверка пройдена!\n\n"
        "Теперь создадим твою анкету ❤️\n\n"
        "Как тебя зовут?",
        reply_markup=ReplyKeyboardRemove(),
    )

# ==========================================
# РЕГИСТРАЦИЯ — ИМЯ
# ==========================================

@dp.message(Registration.name)
async def registration_name(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer("Напиши своё имя текстом.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "Имя слишком короткое.\n"
            "Напиши ещё раз."
        )
        return
    await state.update_data(name=name)
    await state.set_state(Registration.age)
    await message.answer(
        "Сколько тебе лет?\n\n"
        "Напиши число от 18 до 100."
    )

# ==========================================
# РЕГИСТРАЦИЯ — ВОЗРАСТ
# ==========================================

@dp.message(Registration.age)
async def registration_age(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 24"
        )
        return
    try:
        age = int(message.text)
    except ValueError:
        await message.answer(
            "Нужно написать число.\n"
            "Например: 24"
        )
        return
    if age < 18 or age > 100:
        await message.answer("Возраст должен быть от 18 до 100 лет.")
        return
    await state.update_data(age=age)
    await state.set_state(Registration.gender)
    await message.answer(
        "Укажи свой пол:",
        reply_markup=gender_keyboard,
    )

# ==========================================
# РЕГИСТРАЦИЯ — ПОЛ
# ==========================================

@dp.message(Registration.gender)
async def registration_gender(
    message: Message,
    state: FSMContext,
):
    if message.text not in ["👨 Парень", "👩 Девушка"]:
        await message.answer(
            "Выбери вариант кнопкой ниже.",
            reply_markup=gender_keyboard,
        )
        return
    if message.text == "👨 Парень":
        gender = "male"
    else:
        gender = "female"
    await state.update_data(gender=gender)
    await state.set_state(Registration.city)
    await message.answer(
        "В каком городе ты живёшь?\n\n"
        "Напиши название города."
    )

# ==========================================
# РЕГИСТРАЦИЯ — ГОРОД
# ==========================================

@dp.message(Registration.city)
async def registration_city(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer("Напиши название города.")
        return
    city = message.text.strip()
    if len(city) < 2:
        await message.answer(
            "Название города слишком короткое.\n"
            "Напиши ещё раз."
        )
        return
    await state.update_data(city=city)
    await state.set_state(Registration.search_gender)
    await message.answer(
        "Кого ты хочешь найти? ❤️",
        reply_markup=search_gender_keyboard,
    )

# ==========================================
# РЕГИСТРАЦИЯ — КОГО ИЩЕМ
# ==========================================

@dp.message(Registration.search_gender)
async def registration_search_gender(
    message: Message,
    state: FSMContext,
):
    options = {
        "👨 Парни": "male",
        "👩 Девушки": "female",
        "❤️ Все": "all",
    }
    if message.text not in options:
        await message.answer(
            "Выбери вариант кнопкой.",
            reply_markup=search_gender_keyboard,
        )
        return
    search_gender = options[message.text]
    await state.update_data(search_gender=search_gender)
    await state.set_state(Registration.search_age_min)
    await message.answer(
        "От какого возраста искать?\n\n"
        "Например: 18"
    )

# ==========================================
# РЕГИСТРАЦИЯ — МИНИМАЛЬНЫЙ ВОЗРАСТ
# ==========================================

@dp.message(Registration.search_age_min)
async def registration_search_age_min(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 18"
        )
        return
    try:
        age_min = int(message.text)
    except ValueError:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 18"
        )
        return
    if age_min < 18 or age_min > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    await state.update_data(search_age_min=age_min)
    await state.set_state(Registration.search_age_max)
    await message.answer(
        "До какого возраста искать?\n\n"
        "Например: 30"
    )

# ==========================================
# РЕГИСТРАЦИЯ — МАКСИМАЛЬНЫЙ ВОЗРАСТ
# ==========================================

@dp.message(Registration.search_age_max)
async def registration_search_age_max(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 30"
        )
        return
    try:
        age_max = int(message.text)
    except ValueError:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 30"
        )
        return
    data = await state.get_data()
    if age_max < 18 or age_max > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    age_min = data.get("search_age_min")
    if not isinstance(age_min, int):
        await state.clear()
        await message.answer(
            "Потерялись данные регистрации.\n\n"
            "Напиши /start, чтобы начать создание анкеты заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    if age_max < age_min:
        await message.answer(
            "Максимальный возраст не может быть "
            "меньше минимального."
        )
        return
    await state.update_data(search_age_max=age_max)
    await state.set_state(Registration.description)
    await message.answer(
        "📝 Расскажи немного о себе.\n\n"
        "Напиши несколько слов о себе, своих интересах или том, "
        "кого хочешь встретить.\n\n"
        "Можно написать «Пропустить», если не хочешь заполнять описание."
    )

# ==========================================
# РЕГИСТРАЦИЯ — ОПИСАНИЕ
# ==========================================

@dp.message(Registration.description)
async def registration_description(
    message: Message,
    state: FSMContext,
):
    description = (message.text or "").strip()
    if description.lower() == "пропустить":
        description = ""
    elif len(description) > 1000:
        await message.answer("Описание слишком длинное. Максимум — 1000 символов.")
        return
    await state.update_data(description=description)
    await state.set_state(Registration.photo)
    await message.answer(
        "📸 Теперь отправь свою фотографию.\n\n"
        "Лучше отправить обычную фотографию через Telegram, а не файл."
    )

# ==========================================
# РЕГИСТРАЦИЯ — ФОТО
# ==========================================

@dp.message(Registration.photo)
async def registration_photo(
    message: Message,
    state: FSMContext,
):
    if not message.photo:
        await message.answer(
            "📸 Я не вижу фотографию.\n\n"
            "Отправь именно фотографию через Telegram."
        )
        return
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    required_fields = (
        "name",
        "age",
        "gender",
        "city",
        "search_gender",
        "search_age_min",
        "search_age_max",
        "description",
    )
    if any(field not in data for field in required_fields):
        await state.clear()
        await message.answer(
            "Потерялись данные регистрации, поэтому анкету не удалось сохранить.\n\n"
            "Напиши /start, чтобы начать создание анкеты заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await state.update_data(photo_file_id=photo_file_id)
    create_user(
        telegram_id=message.from_user.id,
        name=data["name"],
        age=data["age"],
        gender=data["gender"],
        city=data["city"],
        search_gender=data["search_gender"],
        search_age_min=data["search_age_min"],
        search_age_max=data["search_age_max"],
        photo_file_id=photo_file_id,
        description=data["description"],
    )
    await state.clear()
    await message.answer(
        "🎉 Анкета создана!\n\n"
        f"👤 {data['name']}\n"
        f"🎂 {data['age']} лет\n"
        f"📍 {data['city']}\n\n"
        "Теперь можно начинать знакомиться ❤️",
        reply_markup=main_keyboard,
    )

# ==========================================
# ЗНАКОМСТВА
# ==========================================

@dp.message(
    lambda message: message.text == "💘 Знакомства"
)
async def start_dating(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "Сначала нужно создать анкету.\n\n"
            "Напиши /start"
        )
        return
    await show_next_profile(message, user)

async def show_next_profile(message: Message, user):
    profile = get_next_profile(
        telegram_id=user["telegram_id"],
        city=user["city"],
        search_gender=user["search_gender"],
        age_min=user["search_age_min"],
        age_max=user["search_age_max"],
    )
    if not profile:
        await message.answer(
            "😔 Подходящих анкет больше нет.\n\n"
            "Попробуй изменить настройки поиска."
        )
        return
    add_view(
        viewer_id=user["telegram_id"],
        viewed_id=profile["telegram_id"],
    )
    await send_profile_card(message, profile)

async def send_profile_card(message: Message, profile):
    caption = (
        "💘 Новая анкета!\n\n"
        f"👤 {profile['name']}\n"
        f"🎂 {profile['age']} лет\n"
        f"📍 {profile['city']}"
    )

    if profile["description"]:
        caption += f"\n\n📝 {profile['description']}"
    keyboard = create_profile_keyboard(profile["telegram_id"])
    if profile["photo_file_id"]:
        await message.answer_photo(
            photo=profile["photo_file_id"],
            caption=limit_caption(caption),
            reply_markup=keyboard,
        )
    else:
        await message.answer(caption, reply_markup=keyboard)

# ==========================================
# ВХОДЯЩИЕ ЛАЙКИ И ВОЗВРАТ АНКЕТЫ
# ==========================================

async def show_next_incoming_like(message: Message, user_id):
    incoming_likes = get_incoming_likes(user_id)
    if not incoming_likes:
        await message.answer(
            "❤️ Новых лайков пока нет.\n\n"
            "Когда кто-нибудь тебя лайкнет, анкета появится здесь.",
            reply_markup=main_keyboard,
        )
        return
    profile = incoming_likes[0]
    caption = (
        "❤️ Тебе поставили лайк!\n\n"
        f"👤 {profile['name']}\n"
        f"🎂 {profile['age']} лет\n"
        f"📍 {profile['city']}"
    )
    if profile["description"]:
        caption += f"\n\n📝 {profile['description']}"
    keyboard = create_like_back_keyboard(profile["telegram_id"])
    if profile["photo_file_id"]:
        await message.answer_photo(
            photo=profile["photo_file_id"],
            caption=limit_caption(caption),
            reply_markup=keyboard,
        )
    else:
        await message.answer(caption, reply_markup=keyboard)

@dp.message(lambda message: message.text == "❤️ Кто меня лайкнул")
async def incoming_likes(message: Message):
    if not get_user(message.from_user.id):
        await message.answer("Сначала создай анкету через /start.")
        return
    await show_next_incoming_like(message, message.from_user.id)

@dp.message(lambda message: message.text == "↩️ Вернуть анкету")
async def undo_skip(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала создай анкету через /start.")
        return
    profile_id = undo_last_skip(message.from_user.id)
    if not profile_id:
        await message.answer("Пока нечего возвращать — ты ещё не пропускал анкеты.")
        return
    profile = get_user(profile_id)
    if not profile or is_blocked(message.from_user.id, profile_id):
        await message.answer(
            "Эту анкету уже нельзя показать. Продолжай знакомиться!",
            reply_markup=main_keyboard,
        )
        return
    await send_profile_card(message, profile)

@dp.message(lambda message: message.text == "🔄 Показать анкеты заново")
async def reset_profile_queue(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала создай анкету через /start.")
        return
    reset_views(message.from_user.id)
    await message.answer("🔄 История просмотров очищена. Показываю анкеты заново.")
    await show_next_profile(message, user)

# ==========================================
# ПРОПУСТИТЬ АНКЕТУ
# ==========================================

@dp.callback_query(
    lambda callback: (
        callback.data.startswith("skip_")
        and not callback.data.startswith("skip_like_")
    )
)
async def skip_profile(callback: CallbackQuery):
    await callback.answer("Анкета пропущена ❌")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    user = get_user(callback.from_user.id)
    if not user:
        return
    try:
        skipped_id = int(callback.data.replace("skip_", ""))
    except ValueError:
        await callback.message.answer("Ошибка анкеты.")
        return
    if skipped_id == user["telegram_id"] or not get_user(skipped_id):
        await callback.message.answer("Анкета больше недоступна.")
        return
    add_skip(user["telegram_id"], skipped_id)
    await show_next_profile(callback.message, user)

# ==========================================
# ЛАЙКНУТЬ В ОТВЕТ
# ==========================================

@dp.callback_query(
    lambda callback: callback.data.startswith("like_back_")
)
async def like_back(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("like_back_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала создай анкету.")
        return
    profile = get_user(profile_id)
    if not profile:
        await callback.answer("Эта анкета больше недоступна.")
        return
    if is_blocked(user["telegram_id"], profile_id):
        await callback.answer("Этот пользователь недоступен.")
        return
    if profile_id == user["telegram_id"]:
        await callback.answer("Нельзя лайкнуть самого себя 😄")
        return
    # Проверяем, что этот пользователь
    # действительно ранее поставил нам лайк.
    if not has_like(profile_id, user["telegram_id"]):
        await callback.answer("Этот лайк уже недоступен.")
        return
    add_like(
        from_user=user["telegram_id"],
        to_user=profile_id,
    )
    new_match = create_match(
        user_one=user["telegram_id"],
        user_two=profile_id,
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("💘 Взаимная симпатия!")
    await callback.message.answer(
        "💘 МЭТЧ!\n\n"
        f"Вы понравились друг другу с "
        f"{profile['name']}! ❤️\n\n"
        "Теперь можно начать общаться.",
        reply_markup=create_match_action_keyboard(profile_id),
    )
    # Уведомляем второго пользователя только
    # при создании нового мэтча.
    if new_match:
        try:
            match_text = (
                "💘 МЭТЧ!\n\n"
                f"Ты понравился(ась) "
                f"{user['name']}! ❤️\n\n"
                "Вы понравились друг другу.\n"
                "Теперь можно начать общаться."
            )
            if user["photo_file_id"]:
                await bot.send_photo(
                    chat_id=profile_id,
                    photo=user["photo_file_id"],
                    caption=limit_caption(match_text),
                    reply_markup=create_match_action_keyboard(
                        user["telegram_id"]
                    ),
                )
            else:
                await bot.send_message(
                    chat_id=profile_id,
                    text=match_text,
                    reply_markup=create_match_action_keyboard(
                        user["telegram_id"]
                    ),
                )
        except Exception:
            pass
    await show_next_incoming_like(callback.message, user["telegram_id"])

# ==========================================
# ПРОПУСТИТЬ ПОЛУЧЕННЫЙ ЛАЙК
# ==========================================

@dp.callback_query(
    lambda callback: callback.data.startswith("skip_like_")
)
async def skip_received_like(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("skip_like_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    user = get_user(callback.from_user.id)
    if not user or not has_like(profile_id, user["telegram_id"]):
        await callback.answer("Этот лайк уже недоступен.")
        return
    remove_like(profile_id, user["telegram_id"])
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("Лайк пропущен ❌")
    await show_next_incoming_like(callback.message, callback.from_user.id)

# ==========================================
# ЛАЙК
# ==========================================

@dp.callback_query(
    lambda callback: (
        callback.data.startswith("like_")
        and not callback.data.startswith("like_back_")
    )
)
async def like_profile(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("like_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала создай анкету.")
        return
    profile = get_user(profile_id)
    if not profile:
        await callback.answer("Эта анкета больше недоступна.")
        return
    if profile_id == user["telegram_id"]:
        await callback.answer("Нельзя лайкнуть самого себя 😄")
        return
    if is_blocked(user["telegram_id"], profile_id):
        await callback.answer("Этот пользователь недоступен.")
        return
    # --------------------------------------
    # ДОБАВЛЯЕМ ЛАЙК
    # --------------------------------------
    new_like = add_like(
        from_user=user["telegram_id"],
        to_user=profile_id,
    )
    # --------------------------------------
    # ПРОВЕРЯЕМ ВЗАИМНЫЙ ЛАЙК
    # --------------------------------------
    mutual = is_mutual_like(
        user_id=user["telegram_id"],
        other_user_id=profile_id,
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # ======================================
    # ЕСЛИ МЭТЧ
    # ======================================
    if mutual:
        new_match = create_match(
            user_one=user["telegram_id"],
            user_two=profile_id,
        )
        await callback.answer("💘 Взаимная симпатия!")
        await callback.message.answer(
            "💘 МЭТЧ!\n\n"
            f"Вы понравились друг другу с "
            f"{profile['name']}! ❤️\n\n"
            "Теперь можно начать общаться.",
            reply_markup=create_match_action_keyboard(profile_id),
        )
        # ----------------------------------
        # УВЕДОМЛЯЕМ ВТОРОГО ПОЛЬЗОВАТЕЛЯ
        # ----------------------------------
        if new_match:
            try:
                match_text = (
                    "💘 МЭТЧ!\n\n"
                    f"Ты понравился(ась) "
                    f"{user['name']}! ❤️\n\n"
                    "Вы понравились друг другу.\n"
                    "Теперь можно начать общаться."
                )
                if user["photo_file_id"]:
                    await bot.send_photo(
                        chat_id=profile_id,
                        photo=user["photo_file_id"],
                        caption=limit_caption(match_text),
                        reply_markup=create_match_action_keyboard(
                            user["telegram_id"]
                        ),
                    )
                else:
                    await bot.send_message(
                        chat_id=profile_id,
                        text=match_text,
                        reply_markup=create_match_action_keyboard(
                            user["telegram_id"]
                        ),
                    )
            except Exception:
                pass
    # ======================================
    # ОБЫЧНЫЙ ЛАЙК
    # ======================================
    else:
        await callback.answer("Лайк отправлен ❤️")
        await callback.message.answer("❤️ Лайк отправлен!")
        # ----------------------------------
        # УВЕДОМЛЯЕМ ПОЛУЧАТЕЛЯ ЛАЙКА
        # ----------------------------------
        if new_like:
            try:
                like_caption = (
                    "❤️ Тебе поставили лайк!\n\n"
                    f"👤 {user['name']}\n"
                    f"🎂 {user['age']} лет\n"
                    f"📍 {user['city']}"
                )
                if user["description"]:
                    like_caption += f"\n\n📝 {user['description']}"
                like_caption += "\n\nХочешь поставить лайк в ответ?"
                like_keyboard = create_like_back_keyboard(
                    user["telegram_id"]
                )
                if user["photo_file_id"] and len(like_caption) <= 1024:
                    await bot.send_photo(
                        chat_id=profile_id,
                        photo=user["photo_file_id"],
                        caption=like_caption,
                        reply_markup=like_keyboard,
                    )
                elif user["photo_file_id"]:
                    await bot.send_photo(
                        chat_id=profile_id,
                        photo=user["photo_file_id"],
                        caption=(
                            "❤️ Тебе поставили лайк!\n"
                            f"👤 {user['name']}, {user['age']} лет\n"
                            f"📍 {user['city']}"
                        ),
                    )
                    await bot.send_message(
                        chat_id=profile_id,
                        text=(
                            f"📝 Описание:\n\n{user['description']}\n\n"
                            "Хочешь поставить лайк в ответ?"
                        ),
                        reply_markup=like_keyboard,
                    )
                else:
                    await bot.send_message(
                        chat_id=profile_id,
                        text=like_caption,
                        reply_markup=like_keyboard,
                    )
            except Exception:
                pass
    # --------------------------------------
    # ПОКАЗЫВАЕМ СЛЕДУЮЩУЮ АНКЕТУ
    # --------------------------------------
    await show_next_profile(callback.message, user)

# ==========================================
# ЖАЛОБЫ, БЛОКИРОВКИ И УДАЛЕНИЕ МЭТЧА
# ==========================================

@dp.callback_query(lambda callback: callback.data.startswith("block_"))
async def request_block(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("block_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    if profile_id == callback.from_user.id or not get_user(profile_id):
        await callback.answer("Анкета недоступна.")
        return
    await callback.message.edit_reply_markup(
        reply_markup=create_block_confirm_keyboard(profile_id)
    )
    await callback.answer()

@dp.callback_query(lambda callback: callback.data.startswith("cancel_block_"))
async def cancel_block(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("cancel_block_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    await callback.message.edit_reply_markup(
        reply_markup=(
            create_match_action_keyboard(profile_id)
            if get_match(callback.from_user.id, profile_id)
            else create_profile_keyboard(profile_id)
        )
    )
    await callback.answer("Блокировка отменена")

@dp.callback_query(lambda callback: callback.data.startswith("confirm_block_"))
async def confirm_block(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        profile_id = int(callback.data.replace("confirm_block_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    if profile_id == callback.from_user.id or not get_user(profile_id):
        await callback.answer("Анкета недоступна.")
        return
    add_block(callback.from_user.id, profile_id)
    state_data = await state.get_data()
    if state_data.get("partner_id") == profile_id:
        await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🚫 Пользователь заблокирован. Его анкеты и сообщения больше не будут доступны.",
        reply_markup=main_keyboard,
    )
    await callback.answer("Пользователь заблокирован")

@dp.callback_query(lambda callback: callback.data.startswith("report_"))
async def report_profile(callback: CallbackQuery):
    try:
        profile_id = int(callback.data.replace("report_", ""))
    except ValueError:
        await callback.answer("Ошибка анкеты.")
        return
    reporter = get_user(callback.from_user.id)
    reported = get_user(profile_id)
    if not reporter or not reported or profile_id == callback.from_user.id:
        await callback.answer("Анкета недоступна.")
        return
    reporter_id = reporter["telegram_id"]
    reported_id = reported["telegram_id"]
    add_report(reporter_id, reported_id)
    if is_report_notified(reporter_id, reported_id):
        await callback.answer("Ты уже отправлял жалобу на эту анкету.")
        return
    if not BOT_ADMIN_ID:
        logging.error("BOT_ADMIN_ID is not configured; report stored without notification")
        await callback.answer("Жалоба сохранена, но администратор не настроен.")
        return
    report_text = (
        "⚠️ Жалоба на анкету\n\n"
        f"Отправитель ID {reporter['telegram_id']}: {reporter['name'][:100]}\n"
        f"Анкета ID {reported['telegram_id']}: {reported['name'][:100]}"
    )
    try:
        await bot.send_message(BOT_ADMIN_ID, report_text)
    except TelegramAPIError:
        logging.exception("Failed to notify admin about a user report")
        await callback.answer("Жалоба сохранена, но уведомить администратора не удалось.")
        return
    mark_report_notified(reporter_id, reported_id)
    await callback.answer("Жалоба отправлена модератору. Спасибо!")

@dp.callback_query(lambda callback: callback.data.startswith("unmatch_"))
async def request_unmatch(callback: CallbackQuery):
    try:
        other_user_id = int(callback.data.replace("unmatch_", ""))
    except ValueError:
        await callback.answer("Ошибка мэтча.")
        return
    if not get_match(callback.from_user.id, other_user_id):
        await callback.answer("Мэтч уже недоступен.")
        return
    await callback.message.edit_reply_markup(
        reply_markup=create_unmatch_confirm_keyboard(other_user_id)
    )
    await callback.answer()

@dp.callback_query(lambda callback: callback.data.startswith("cancel_unmatch_"))
async def cancel_unmatch(callback: CallbackQuery):
    try:
        other_user_id = int(callback.data.replace("cancel_unmatch_", ""))
    except ValueError:
        await callback.answer("Ошибка мэтча.")
        return
    profile = get_user(other_user_id)
    if not profile or not get_match(callback.from_user.id, other_user_id):
        await callback.answer("Мэтч уже недоступен.")
        return
    await callback.message.edit_reply_markup(
        reply_markup=create_match_action_keyboard(other_user_id)
    )
    await callback.answer("Отменено")

@dp.callback_query(lambda callback: callback.data.startswith("confirm_unmatch_"))
async def confirm_unmatch(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        other_user_id = int(callback.data.replace("confirm_unmatch_", ""))
    except ValueError:
        await callback.answer("Ошибка мэтча.")
        return
    match = get_match(callback.from_user.id, other_user_id)
    if not match:
        await callback.answer("Мэтч уже недоступен.")
        return
    delete_match(callback.from_user.id, other_user_id)
    state_data = await state.get_data()
    if state_data.get("partner_id") == other_user_id:
        await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "💔 Мэтч удалён. История переписки удалена.",
        reply_markup=main_keyboard,
    )
    try:
        await bot.send_message(
            other_user_id,
            "💔 Ваш мэтч был удалён. История переписки больше недоступна.",
        )
    except TelegramAPIError:
        logging.exception("Failed to notify user about removed match")
    await callback.answer("Мэтч удалён")

# ==========================================
# МОИ МЭТЧИ
# ==========================================

@dp.message(
    lambda message: message.text == "💞 Мои мэтчи"
)
async def my_matches(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "Сначала создай анкету.\n\n"
            "Напиши /start"
        )
        return
    matches = get_matches(message.from_user.id)
    if not matches:
        await message.answer(
            "💞 Пока мэтчей нет.\n\n"
            "Продолжай знакомиться — "
            "здесь появятся люди, которым "
            "ты тоже понравился ❤️",
            reply_markup=main_keyboard,
        )
        return
    await message.answer(
        "💞 Твои мэтчи\n\n"
        "Выбери человека, с которым хочешь "
        "пообщаться:"
    )
    for match in matches:
        unread_label = (
            f" · {match['unread_count']} новых"
            if match["unread_count"]
            else ""
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=(
                            f"💬 {match['name']}, {match['age']}"
                            f"{unread_label}"
                        ),
                        callback_data=(
                            f"chat_{match['other_user_id']}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💔 Удалить мэтч",
                        callback_data=f"unmatch_{match['other_user_id']}",
                    ),
                    InlineKeyboardButton(
                        text="🚫 Заблокировать",
                        callback_data=f"block_{match['other_user_id']}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="⚠️ Пожаловаться",
                        callback_data=f"report_{match['other_user_id']}",
                    )
                ],
            ]
        )
        if match["photo_file_id"]:
            await message.answer_photo(
                photo=match["photo_file_id"],
                caption=(
                    f"💘 {match['name']}\n"
                    f"🎂 {match['age']} лет\n"
                    f"📍 {match['city']}"
                ),
                reply_markup=keyboard,
            )
        else:
            await message.answer(
                (
                    f"💘 {match['name']}\n"
                    f"🎂 {match['age']} лет\n"
                    f"📍 {match['city']}"
                ),
                reply_markup=keyboard,
            )

# ==========================================
# ОТКРЫТЬ ЧАТ
# ==========================================

@dp.callback_query(
    lambda callback: callback.data.startswith("chat_")
)
async def open_chat(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        other_user_id = int(callback.data.replace("chat_", ""))
    except ValueError:
        await callback.answer("Ошибка чата.")
        return
    current_user_id = callback.from_user.id
    if current_user_id == other_user_id:
        await callback.answer("Нельзя открыть чат с собой.")
        return
    current_user = get_user(current_user_id)
    other_user = get_user(other_user_id)
    if not current_user or not other_user:
        await callback.answer("Пользователь не найден.")
        return
    if is_blocked(current_user_id, other_user_id):
        await callback.answer("Этот пользователь недоступен.")
        return
    match = get_match(current_user_id, other_user_id)
    if not match:
        await callback.answer("У вас нет мэтча.")
        return
    await state.clear()
    await state.update_data(
        match_id=match["id"],
        partner_id=other_user_id,
        partner_name=other_user["name"],
    )
    await state.set_state(ChatState.chatting)
    await callback.answer()
    await callback.message.answer(
        f"💬 Чат с {other_user['name']}\n\n"
        "Пиши сообщение — я передам его "
        "твоему мэтчу.\n\n"
        "Чтобы выйти из чата, нажми "
        "«↩️ Выйти из чата».",
        reply_markup=chat_keyboard,
    )
    mark_messages_read(match["id"], current_user_id)
    history = get_messages(match["id"])
    if history:
        await callback.message.answer("📜 Последние сообщения:")
        for stored_message in history:
            sender_name = (
                current_user["name"]
                if stored_message["sender_id"] == current_user_id
                else other_user["name"]
            )
            text = f"{sender_name}: {stored_message['text']}"
            for start in range(0, len(text), 3900):
                await callback.message.answer(text[start:start + 3900])

# ==========================================
# ОТПРАВКА СООБЩЕНИЯ В ЧАТ
# ==========================================

@dp.message(ChatState.chatting)
async def send_chat_message(
    message: Message,
    state: FSMContext,
):
    if message.text == "↩️ Выйти из чата":
        data = await state.get_data()
        partner_name = data.get("partner_name", "пользователем")
        await state.clear()
        await message.answer(
            f"Ты вышел из чата с {partner_name}.",
            reply_markup=main_keyboard,
        )
        return
    if not message.text:
        await message.answer(
            "Пока в чате можно отправлять "
            "только текстовые сообщения."
        )
        return
    text = message.text.strip()
    if not text:
        return
    if len(text) > 4000:
        await message.answer(
            "Сообщение слишком длинное.\n"
            "Максимум — 4000 символов."
        )
        return
    data = await state.get_data()
    match_id = data.get("match_id")
    partner_id = data.get("partner_id")
    partner_name = data.get("partner_name", "пользователь")
    if not match_id or not partner_id:
        await state.clear()
        await message.answer(
            "Чат больше недоступен.",
            reply_markup=main_keyboard,
        )
        return
    match = get_match(message.from_user.id, partner_id)
    if not match or is_blocked(message.from_user.id, partner_id):
        await state.clear()
        await message.answer(
            "❌ Этот мэтч больше недоступен.",
            reply_markup=main_keyboard,
        )
        return
    add_message(
        match_id=match_id,
        sender_id=message.from_user.id,
        receiver_id=partner_id,
        text=text,
    )
    try:
        await bot.send_message(
            partner_id,
            f"💬 Сообщение от {message.from_user.full_name}:",
        )
        await bot.send_message(
            partner_id,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Ответить",
                            callback_data=(
                                f"chat_{message.from_user.id}"
                            ),
                        )
                    ]
                ]
            ),
        )
        await message.answer(f"✅ Отправлено {partner_name}.")
    except TelegramAPIError:
        logging.exception("Failed to deliver a chat message")
        await message.answer(
            "⚠️ Не удалось доставить сообщение.\n\n"
            "Возможно, пользователь заблокировал "
            "бота или чат с ним недоступен."
        )

# ==========================================
# МОЯ АНКЕТА
# ==========================================

@dp.message(
    lambda message: message.text == "👤 Моя анкета"
)
async def my_profile(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "У тебя пока нет анкеты.\n\n"
            "Напиши /start, чтобы создать её."
        )
        return
    caption = (
        "👤 Твоя анкета\n\n"
        f"Имя: {user['name']}\n"
        f"Возраст: {user['age']}\n"
        f"Город: {user['city']}"
    )

    if user["description"]:
        caption += f"\n\n📝 {user['description']}"
    
    keyboard = create_my_profile_keyboard()
    if user["photo_file_id"]:
        await message.answer_photo(
            photo=user["photo_file_id"],
            caption=limit_caption(caption),
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            caption,
            reply_markup=keyboard,
        )

# ==========================================
# РЕДАКТИРОВАНИЕ АНКЕТЫ
# ==========================================

@dp.callback_query(
    lambda callback: callback.data == "profile_edit_name"
)
async def start_edit_name(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Анкета не найдена.")
        return
    await callback.answer("Открываю редактирование ✏️")
    await state.set_state(Registration.edit_name)
    await callback.message.answer(
        "✏️ Редактирование анкеты\n\n"
        f"Текущее имя: {user['name']}\n\n"
        "Напиши новое имя:"
    )

@dp.callback_query(
    lambda callback: callback.data == "profile_edit_description"
)
async def start_edit_description(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not get_user(callback.from_user.id):
        await callback.answer("Анкета не найдена.")
        return
    await state.set_state(Registration.edit_description)
    await callback.answer()
    await callback.message.answer(
        "📝 Напиши новое описание о себе.\n\n"
        "Чтобы удалить описание, напиши «Пропустить»."
    )

@dp.callback_query(
    lambda callback: callback.data == "profile_edit_photo"
)
async def start_edit_photo(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not get_user(callback.from_user.id):
        await callback.answer("Анкета не найдена.")
        return
    await state.set_state(Registration.edit_photo)
    await callback.answer()
    await callback.message.answer("📸 Отправь новую фотографию.")

@dp.callback_query(
    lambda callback: callback.data == "profile_edit_city"
)
async def start_edit_city(
    callback: CallbackQuery,
    state: FSMContext,
):
    if not get_user(callback.from_user.id):
        await callback.answer("Анкета не найдена.")
        return
    await state.set_state(Registration.edit_city)
    await callback.answer()
    await callback.message.answer("📍 Напиши название нового города.")

@dp.message(Registration.edit_name)
async def edit_profile_name(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer("Напиши новое имя текстом.")
        return
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "Имя слишком короткое.\n"
            "Напиши имя ещё раз."
        )
        return
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE users
            SET name = ?
            WHERE telegram_id = ?
            """,
            (name, message.from_user.id),
        )
        connection.commit()
    finally:
        connection.close()
    await state.clear()
    await message.answer(
        f"✅ Имя изменено на: {name}",
        reply_markup=main_keyboard,
    )

@dp.message(Registration.edit_description)
async def edit_profile_description(
    message: Message,
    state: FSMContext,
):
    description = (message.text or "").strip()
    if description.lower() == "пропустить":
        description = ""
    elif len(description) > 1000:
        await message.answer("Описание слишком длинное. Максимум — 1000 символов.")
        return
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE users
            SET description = ?
            WHERE telegram_id = ?
            """,
            (description, message.from_user.id),
        )
        connection.commit()
    finally:
        connection.close()
    await state.clear()
    await message.answer(
        "✅ Описание анкеты обновлено!",
        reply_markup=main_keyboard,
    )

@dp.message(Registration.edit_photo)
async def edit_profile_photo(
    message: Message,
    state: FSMContext,
):
    if not message.photo:
        await message.answer("Отправь именно фотографию через Telegram.")
        return
    update_profile_photo(message.from_user.id, message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Фотография обновлена!", reply_markup=main_keyboard)

@dp.message(Registration.edit_city)
async def edit_profile_city(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer("Напиши название города текстом.")
        return
    city = message.text.strip()
    if len(city) < 2:
        await message.answer("Название города слишком короткое. Попробуй ещё раз.")
        return
    update_profile_city(message.from_user.id, city)
    await state.clear()
    await message.answer(
        f"✅ Город обновлён: {city}",
        reply_markup=main_keyboard,
    )

# ==========================================
# УДАЛЕНИЕ АНКЕТЫ
# ==========================================

@dp.callback_query(
    lambda callback: callback.data == "delete_profile"
)
async def delete_profile_confirm(callback: CallbackQuery):
    await callback.message.edit_reply_markup(
        reply_markup=create_delete_confirm_keyboard()
    )
    await callback.answer()

@dp.callback_query(
    lambda callback: callback.data == "delete_profile_no"
)
async def delete_profile_no(callback: CallbackQuery):
    await callback.message.edit_reply_markup(
        reply_markup=create_my_profile_keyboard()
    )
    await callback.answer("Удаление отменено")

@dp.callback_query(
    lambda callback: callback.data == "delete_profile_yes"
)
async def delete_profile_yes(
    callback: CallbackQuery,
    state: FSMContext,
):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("Анкета уже удалена.")
        return
    delete_user(callback.from_user.id)
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "🗑 Анкета удалена.\n\n"
        "Все твои лайки, мэтчи, сообщения "
        "и история просмотров тоже удалены.\n\n"
        "Если захочешь вернуться — просто "
        "напиши /start ❤️",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="/start")
                ]
            ],
            resize_keyboard=True,
        ),
    )
    await callback.answer("Анкета удалена")

# ==========================================
# НАСТРОЙКИ ПОИСКА
# ==========================================

@dp.message(
    lambda message: message.text == "⚙️ Настройки поиска"
)
async def search_settings(
    message: Message,
    state: FSMContext,
):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "Сначала создай анкету.\n\n"
            "Напиши /start"
        )
        return
    gender_names = {
        "male": "👨 Парни",
        "female": "👩 Девушки",
        "all": "❤️ Все",
    }
    current_gender = gender_names.get(
        user["search_gender"],
        "Не указано",
    )
    await state.set_state(Registration.settings_gender)
    await message.answer(
        "⚙️ Настройки поиска\n\n"
        f"Сейчас ищем: {current_gender}\n"
        f"Возраст: {user['search_age_min']}–"
        f"{user['search_age_max']} лет\n"
        f"Город: {user['city']}\n\n"
        "Кого хочешь искать?",
        reply_markup=search_gender_keyboard,
    )

# ==========================================
# НАСТРОЙКИ — ПОЛ
# ==========================================

@dp.message(Registration.settings_gender)
async def settings_gender(
    message: Message,
    state: FSMContext,
):
    options = {
        "👨 Парни": "male",
        "👩 Девушки": "female",
        "❤️ Все": "all",
    }
    if message.text not in options:
        await message.answer(
            "Выбери вариант кнопкой.",
            reply_markup=search_gender_keyboard,
        )
        return
    await state.update_data(settings_gender=options[message.text])
    await state.set_state(Registration.settings_age_min)
    user = get_user(message.from_user.id)
    await message.answer(
        "🎂 От какого возраста искать?\n\n"
        f"Сейчас: {user['search_age_min']} лет\n\n"
        "Напиши новый минимальный возраст "
        "от 18 до 100."
    )

# ==========================================
# НАСТРОЙКИ — МИНИМАЛЬНЫЙ ВОЗРАСТ
# ==========================================

@dp.message(Registration.settings_age_min)
async def settings_age_min(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 18"
        )
        return
    try:
        age_min = int(message.text)
    except ValueError:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 18"
        )
        return
    if age_min < 18 or age_min > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    await state.update_data(settings_age_min=age_min)
    await state.set_state(Registration.settings_age_max)
    user = get_user(message.from_user.id)
    await message.answer(
        "🎂 До какого возраста искать?\n\n"
        f"Сейчас: {user['search_age_max']} лет\n\n"
        "Напиши новый максимальный возраст "
        "от 18 до 100."
    )

# ==========================================
# НАСТРОЙКИ — МАКСИМАЛЬНЫЙ ВОЗРАСТ
# ==========================================

@dp.message(Registration.settings_age_max)
async def settings_age_max(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 30"
        )
        return
    try:
        age_max = int(message.text)
    except ValueError:
        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 30"
        )
        return
    if age_max < 18 or age_max > 100:
        await message.answer("Возраст должен быть от 18 до 100.")
        return
    data = await state.get_data()
    age_min = data.get("settings_age_min")
    if age_min is None:
        await state.clear()
        await message.answer(
            "Произошла ошибка настроек.\n"
            "Открой настройки поиска ещё раз.",
            reply_markup=main_keyboard,
        )
        return
    if age_max < age_min:
        await message.answer(
            f"Максимальный возраст не может быть "
            f"меньше минимального ({age_min})."
        )
        return
    search_gender = data.get("settings_gender")
    if not search_gender:
        await state.clear()
        await message.answer(
            "Произошла ошибка настроек.\n"
            "Открой настройки поиска ещё раз.",
            reply_markup=main_keyboard,
        )
        return
    update_search_settings(
        telegram_id=message.from_user.id,
        search_gender=search_gender,
        search_age_min=age_min,
        search_age_max=age_max,
    )
    await state.clear()
    gender_names = {
        "male": "👨 Парни",
        "female": "👩 Девушки",
        "all": "❤️ Все",
    }
    await message.answer(
        "✅ Настройки поиска сохранены!\n\n"
        f"🔎 Ищем: {gender_names[search_gender]}\n"
        f"🎂 Возраст: {age_min}–{age_max} лет\n\n"
        "Теперь новые анкеты будут подбираться "
        "по этим настройкам.",
        reply_markup=main_keyboard,
    )

# ==========================================
# ЗАПУСК
# ==========================================

async def main():
    init_database()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())