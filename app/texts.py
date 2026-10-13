"""Тексты сообщений бота (HTML-разметка Telegram)."""

from html import escape

from app.game_data.constants import GAME_TITLE
from app.schemas import PlayerProfile
from app.utils.formatting import format_money, progress_bar

MAIN_MENU_TEXT = "🏠 <b>Главное меню</b>\nВыбери действие на клавиатуре ниже."

HELP_TEXT = (
    f"ℹ️ <b>Справка {GAME_TITLE}</b>\n"
    "\n"
    "Ты управляешь собственной автомастерской: берёшь заказы клиентов, диагностируешь "
    "машину, закупаешь запчасти в магазине, ремонтируешь и сдаёшь работу.\n"
    "\n"
    "<b>Команды:</b>\n"
    "/start — начать игру или вернуться в меню\n"
    "/menu — главное меню\n"
    "/orders — доступные заказы (обновление раз в 2 часа, уведомление придёт в чат)\n"
    "/finance — выручка, расходы и чистая прибыль\n"
    "/workshop — мастерская: принятые заказы\n"
    "/shop — магазин запчастей\n"
    "/stock — склад\n"
    "/profile — профиль игрока\n"
    "/help — эта справка"
)

NOT_REGISTERED_TEXT = "Ты ещё не в игре. Нажми /start, чтобы открыть свою мастерскую."

UNKNOWN_COMMAND_TEXT = "🤔 Неизвестная команда. Список доступных команд — /help."

UNKNOWN_MESSAGE_TEXT = (
    "Я понимаю только команды и кнопки меню. Открыть меню — /menu, справка — /help."
)

ERROR_TEXT = "⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже."


def _stats_lines(profile: PlayerProfile) -> list[str]:
    return [
        f"💰 Деньги: <b>{format_money(profile.money)}</b>",
        f"⭐ Уровень: <b>{profile.level}</b> — {escape(profile.level_title)}",
        f"🤝 Репутация: <b>{profile.reputation} / {profile.reputation_max}</b>",
    ]


def render_welcome_new(profile: PlayerProfile) -> str:
    """Приветствие после первой регистрации."""
    lines = [
        f"🔧 Добро пожаловать в <b>{GAME_TITLE}</b>, {escape(profile.display_name)}!",
        "",
        "Ты открываешь собственную автомастерскую. Всё только начинается — "
        "деньги, опыт и репутацию предстоит заработать.",
        "",
        "<b>Стартовые параметры:</b>",
        *_stats_lines(profile),
        "",
        "Пользуйся меню ниже.",
    ]
    return "\n".join(lines)


def render_welcome_back(profile: PlayerProfile) -> str:
    """Приветствие для уже зарегистрированного игрока."""
    lines = [
        f"🔧 С возвращением, {escape(profile.display_name)}!",
        "",
        *_stats_lines(profile),
    ]
    return "\n".join(lines)


def render_profile(profile: PlayerProfile) -> str:
    """Карточка профиля игрока."""
    if profile.experience_for_next_level is None:
        experience_line = f"📈 Опыт: <b>{profile.experience}</b> (максимальный уровень)"
    else:
        experience_line = (
            f"📈 Опыт: <b>{profile.experience} / {profile.experience_for_next_level}</b>"
        )

    lines = [
        "👤 <b>Профиль игрока</b>",
        "",
        f"🔧 <b>{escape(profile.display_name)}</b>",
    ]
    if profile.username:
        lines.append(f"✈️ @{escape(profile.username)}")
    lines += [
        "",
        f"💰 Деньги: <b>{format_money(profile.money)}</b>",
        f"⭐ Уровень: <b>{profile.level}</b> — {escape(profile.level_title)}",
        experience_line,
        f"🤝 Репутация: <b>{profile.reputation} / {profile.reputation_max}</b> "
        f"— {escape(profile.reputation_title)}",
        progress_bar(profile.reputation, profile.reputation_max),
        "",
        f"📅 В игре с {profile.registered_at.strftime('%d.%m.%Y')}",
    ]
    return "\n".join(lines)
