from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def confirm_remove_channel_kb(username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"remove_confirm:{username}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="remove_cancel"),
    )
    return builder.as_markup()


def channels_list_kb(usernames: list[str]) -> InlineKeyboardMarkup:
    """Keyboard for selecting which channel to remove."""
    builder = InlineKeyboardBuilder()
    for username in usernames:
        builder.add(
            InlineKeyboardButton(
                text=f"🗑 @{username}",
                callback_data=f"remove_select:{username}",
            )
        )
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="remove_cancel"))
    builder.adjust(1)
    return builder.as_markup()
