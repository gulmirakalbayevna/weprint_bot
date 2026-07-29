from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import FORMAT_NAMES, BINDING_NAMES, UNIVERSITETLAR, PRICE_CALC_URL


def kb_phone():
    b = ReplyKeyboardBuilder()
    b.add(KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True))
    return b.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_main_menu():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📚 Buyurtma berish"))
    b.row(KeyboardButton(text="📦 Buyurtmalarim"))
    b.row(KeyboardButton(text="💰 Narxni hisoblash"), KeyboardButton(text="ℹ️ Ma'lumotlar"))
    return b.as_markup(resize_keyboard=True)


def kb_price_calc():
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="🌐 Narxni hisoblash", url=PRICE_CALC_URL))
    return b.as_markup()


def kb_admin_book_type(book_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="📕 Knijniy", callback_data=f"btype:knijniy:{book_id}")
    b.button(text="📘 Albomniy", callback_data=f"btype:albom:{book_id}")
    b.button(text="❌ Rad etish", callback_data=f"btype:reject:{book_id}")
    b.adjust(2, 1)
    return b.as_markup()


def kb_format_only(book_id: int, prices: dict, albom: bool = False):
    """4 tugma (yoki albom uchun 2 ta) - har birida narx ko'rsatiladi (weprint.uz saytidagidek)."""
    b = InlineKeyboardBuilder()
    keys = ["a4_color", "a4_bw"] if albom else ["a4_color", "a4_bw", "a5_color", "a5_bw"]
    for fmt_key in keys:
        label = f"{FORMAT_NAMES[fmt_key]} — {prices[fmt_key]:,} so'm".replace(",", " ")
        b.button(text=label, callback_data=f"fmt:{fmt_key}:{book_id}")
    moreinfo_kind = "albom" if albom else "format"
    b.button(text="ℹ️ Batafsil", callback_data=f"moreinfo:{moreinfo_kind}:{book_id}")
    if albom:
        b.adjust(2, 1)
    else:
        b.adjust(2, 2, 1)
    return b.as_markup()


def kb_binding_only(book_id: int):
    """Pereplyot alohida bosqich - 2 tugma + Batafsil + Orqaga."""
    b = InlineKeyboardBuilder()
    b.button(text=BINDING_NAMES["termokley"], callback_data=f"bind:termokley:{book_id}")
    b.button(text=BINDING_NAMES["prujina"], callback_data=f"bind:prujina:{book_id}")
    b.button(text="ℹ️ Batafsil", callback_data=f"moreinfo:binding:{book_id}")
    b.button(text="🔙 Orqaga", callback_data=f"bindback:{book_id}")
    b.adjust(2, 1, 1)
    return b.as_markup()


def kb_copies(book_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="1️⃣", callback_data=f"copies:1:{book_id}")
    b.button(text="2️⃣", callback_data=f"copies:2:{book_id}")
    b.button(text="3️⃣", callback_data=f"copies:3:{book_id}")
    b.button(text="✏️ Boshqa", callback_data=f"copies:other:{book_id}")
    b.button(text="🔙 Orqaga", callback_data=f"copyback:{book_id}")
    b.adjust(3, 1, 1)
    return b.as_markup()


def kb_add_more(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Yana kitob qo'shish", callback_data=f"more:add:{order_id}")
    b.button(text="➡️ Davom etish", callback_data=f"more:continue:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_faq():
    b = InlineKeyboardBuilder()
    b.button(text="🕐 Ish vaqtimiz", callback_data="faq:hours")
    b.button(text="📎 Kitoblarni birlashtirish", callback_data="faq:merge")
    b.button(text="✂️ Keraksiz betlarni olib tashlash", callback_data="faq:trim")
    b.button(text="📍 Manzil", callback_data="faq:address")
    b.button(text="⏱ Tayyor bo'lish vaqti", callback_data="faq:ready_time")
    b.button(text="🚕 Yandex chaqirish", callback_data="faq:yandex_call")
    b.adjust(1)
    return b.as_markup()


def kb_delivery(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🏢 Olib ketaman", callback_data=f"deliv:pickup:{order_id}")
    b.button(text="🚕 Yandex", callback_data=f"deliv:yandex:{order_id}")
    b.button(text="📦 Viloyat", callback_data=f"deliv:viloyat:{order_id}")
    b.button(text="🎓 Universitet", callback_data=f"deliv:univer:{order_id}")
    b.button(text="🔙 Orqaga", callback_data=f"delback:addmore:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_viloyat_type(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🚛 BTS", callback_data=f"vtype:bts:{order_id}")
    b.button(text="📮 Oddiy pochta", callback_data=f"vtype:pochta:{order_id}")
    b.button(text="ℹ️ Batafsil", callback_data=f"moreinfo:delivery:{order_id}")
    b.button(text="🔙 Orqaga", callback_data=f"delback:delivery:{order_id}")
    b.adjust(2, 1, 1)
    return b.as_markup()


def kb_universitet(order_id: int):
    b = InlineKeyboardBuilder()
    for u in UNIVERSITETLAR:
        b.button(text=u, callback_data=f"univer:{u}:{order_id}")
    b.adjust(2)
    return b.as_markup()


def kb_statistika_period():
    b = InlineKeyboardBuilder()
    b.button(text="📅 Bugun", callback_data="statperiod:today")
    b.button(text="🗓 Shu hafta", callback_data="statperiod:week")
    b.button(text="🗓 Shu oy", callback_data="statperiod:month")
    b.button(text="📆 Sana oralig'i", callback_data="statperiod:custom")
    b.adjust(1)
    return b.as_markup()


def kb_admin_accept(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Qabul qilish", callback_data=f"accept:ok:{order_id}")
    b.button(text="❌ Chek to'liq emas", callback_data=f"accept:no:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_admin_accept_pochta(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Pochta to'lovini qabul qilish", callback_data=f"acceptpochta:ok:{order_id}")
    b.button(text="❌ Chek to'liq emas", callback_data=f"acceptpochta:no:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_cancel_order_only(order_id: int):
    """Buyurtma xulosasi + QR ekranida - faqat bekor qilish imkoniyati.
    Xatolik bo'lmasa, foydalanuvchi shunchaki to'lab, chek yuboradi (bu o'zi tasdiq)."""
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bekor qilish", callback_data=f"orderconfirm:no:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_receiver_phone(order_id: int, reg_phone: str = None):
    b = InlineKeyboardBuilder()
    if reg_phone:
        b.button(text=f"✅ O'zim — {reg_phone}", callback_data=f"rphone:self:{order_id}")
    b.button(text="👤 Boshqa kishi", callback_data=f"rphone:other:{order_id}")
    b.button(text="🔙 Orqaga", callback_data=f"delback:delivery:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_cancel_persistent():
    b = ReplyKeyboardBuilder()
    b.add(KeyboardButton(text="❌ Bekor qilish"))
    return b.as_markup(resize_keyboard=True)


def kb_cancel_and_back():
    """Manzil/telefon kiritish bosqichlarida ishlatiladi - orqaga qaytish imkoniyati bilan."""
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🔙 Orqaga"))
    b.row(KeyboardButton(text="❌ Bekor qilish"))
    return b.as_markup(resize_keyboard=True)


def kb_resume_or_fresh(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="➡️ Davom ettirish", callback_data=f"resume:continue:{order_id}")
    b.button(text="🆕 Yangidan boshlash", callback_data=f"resume:fresh:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_ready_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Hammasini tayyor deb belgilash", callback_data="readybatch:yes")
    b.button(text="❌ Bekor qilish", callback_data="readybatch:no")
    b.adjust(1)
    return b.as_markup()


def kb_book_print_toggle(book_id: int, printed: bool):
    """Print guruhida har bir kitob fayli ostida - print holatini
    ✅ (qilindi) / 🕐 (hali yo'q) ko'rinishida almashtirib turadigan tugma."""
    b = InlineKeyboardBuilder()
    label = "✅ Print qilindi" if printed else "🕐 Print qilinishi kerak"
    b.button(text=label, callback_data=f"toggleprint:{book_id}")
    b.adjust(1)
    return b.as_markup()

def kb_already_printed():
    b = InlineKeyboardBuilder()
    b.button(
        text="✅ Allaqachon print qilingan",
        callback_data="printed_done"
    )
    return b.as_markup()


def kb_courier_delivered(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Yetkazildi", callback_data=f"delivered:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_order_received(order_id: int):
    """Mijozning o'ziga - buyurtma TAYYOR xabari bilan birga boradi.
    Bosilsa, mijoz o'z qo'li bilan kitobni olganini tasdiqlaydi."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Oldim", callback_data=f"received:{order_id}")
    b.adjust(1)
    return b.as_markup()


def kb_cancel_specific_order(order_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bu buyurtmani bekor qilish", callback_data=f"cancelorder:{order_id}")
    b.adjust(1)
    return b.as_markup()


def remove_kb():
    return ReplyKeyboardRemove()
