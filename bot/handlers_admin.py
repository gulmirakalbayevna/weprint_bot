from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, ForceReply
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.filters import Command
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError

import asyncio
import config
import database as db
import keyboards as kb
from states import AdminFlow, UserFlow
from utils import calc_book_price, calc_single_copy_prices, get_volume_count, format_money, send_media_message

router = Router()


def admin_only(message_or_cb):
    uid = message_or_cb.from_user.id
    return uid == config.ADMIN_ID


from locks import admin_queue_lock


def _plain(text: str) -> str:
    """HTML rejimida xato chiqmasligi uchun (bot standart HTML parse_mode
    bilan ishlaydi) - fayl nomi yoki foydalanuvchi ismida '<', '>', '&' kabi
    maxsus belgilar bo'lsa, ular HTML teg deb noto'g'ri talqin qilinib,
    "can't parse entities" xatosiga sabab bo'lishi mumkin edi. Shu funksiya
    bunday belgilarni oddiy matnga aylantiradi."""
    if not text:
        return text
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def try_dispatch_next_admin_task(bot: Bot, storage):
    """
    ADMIN UCHUN UMUMIY NAVBAT — bu butun tizimning yuragi.

    Ilgari kitob (sahifa/tur so'rash) va chek tekshirish (to'lov/pochta)
    IKKITA MUSTAQIL oqim edi - shuning uchun ular bir-biriga aralashib,
    admin bitta ishni tugatmasdan boshqasi kelib qolar edi.

    ENDI: ikkalasi ham BITTA `admin_tasks` jadvalida, FIFO navbatda turadi.
    Admin har doim FAQAT BITTA vazifa bilan "band" bo'ladi (buni FSM holati
    orqali bilamiz - agar holat None bo'lmasa, admin band, hech narsa
    yubormaymiz). Joriy vazifa TO'LIQ tugagach (kitob turi tanlangach, yoki
    chek qabul/rad etilgach) - shu funksiya QAYTA chaqiriladi va navbatdagi
    ish (u kitobmi, chekmi - farqi yo'q) endigina ko'rsatiladi.
    """
    admin_key = StorageKey(bot_id=bot.id, chat_id=config.ADMIN_ID, user_id=config.ADMIN_ID)
    admin_state = FSMContext(storage=storage, key=admin_key)

    async with admin_queue_lock:
        current = await admin_state.get_state()
        if current is not None:
            return  # admin band - vazifa navbatda jim kutadi
        task = db.get_next_admin_task()
        if not task:
            return
        db.delete_admin_task(task["id"])
        claimed = dict(task)

    # Tarmoq so'rovlari (fayl yuborish va h.k.) lock TASHQARISIDA bajariladi -
    # aks holda uzoq davom etsa, boshqa hech kim (masalan got_document) lock'ni
    # ololmay "osilib" qolishi mumkin edi.
    try:
        await _present_admin_task(bot, admin_state, claimed)
    except Exception as e:
        # MUHIM: bu yerda ISTALGAN kutilmagan xato (masalan tarmoq, yoki
        # ism/fayl nomidagi maxsus belgi HTML xatosiga sabab bo'lsa) admin
        # holatini ABADIY "band" qilib qo'ymasligi kerak - bo'lmasa har safar
        # qo'lda /clearadmin bosish kerak bo'lib qolar edi. Shuning uchun:
        # xatoni logga yozamiz, adminga ogohlantiramiz, holatni tozalaymiz va
        # NAVBATDAGI vazifaga o'tamiz - navbat o'zi tuzalib ketadi.
        import logging
        logging.exception(
            "try_dispatch_next_admin_task: vazifani ko'rsatishda xato (task_type=%s, ref_id=%s): %s",
            claimed["task_type"], claimed["ref_id"], e
        )
        try:
            await bot.send_message(
                config.ADMIN_ID,
                f"⚠️ Bitta vazifani ko'rsatishda xato chiqdi (o'tkazib yuborildi): {e}"
            )
        except Exception:
            pass
        await admin_state.clear()
        await try_dispatch_next_admin_task(bot, storage)


async def _present_admin_task(bot: Bot, admin_state: FSMContext, claimed: dict):
    """Navbatdan olingan bitta vazifani (kitob yoki chek) adminga ko'rsatadi."""
    if claimed["task_type"] == "book":
        book = db.get_book(claimed["ref_id"])
        if not book or book["status"] != "awaiting_admin":
            # Kitob allaqachon boshqa yo'l bilan hal qilingan - keyingisiga o'tamiz
            await try_dispatch_next_admin_task(bot, admin_state.storage)
            return
        order = db.get_order(book["order_id"])
        if order and order["status"] == "cancelled":
            db.update_book(book["id"], status="rejected")
            await try_dispatch_next_admin_task(bot, admin_state.storage)
            return

        # --- AI AVTO-TASDIQLASH: fayl "toza" va orientatsiya bir xil bo'lsa,
        # config.AI_AUTO_APPROVE_ENABLED yoqilgan bo'lsa, admin'dan SO'RAMASDAN
        # sahifa soni + Knijniy/Albom turini AI o'zi belgilaydi va formatga o'tadi.
        if (
            getattr(config, "AI_AUTO_APPROVE_ENABLED", False)
            and book["ai_analyzed"]
            and not book["ai_religious_flag"]
            and not book["ai_mixed_orientation"]
            and book["ai_book_type_guess"] in ("knijniy", "albom")
        ):
            db.update_book(
                book["id"],
                page_count=book["ai_page_count"],
                book_type=book["ai_book_type_guess"],
                status="awaiting_format",
                ai_auto_approved=1,
            )
            type_label = "📕 Knijniy" if book["ai_book_type_guess"] == "knijniy" else "📘 Albomniy"
            try:
                await bot.send_message(
                    config.ADMIN_ID,
                    f"🤖 AI avtomatik qayta ishladi — №{book['seq_num']} ({_plain(book['file_name'])})\n"
                    f"{book['ai_page_count']} bet, {type_label}\n"
                    f"(Diqqat talab qilinmadi — orientatsiya bir xil, diniy/arab belgisi topilmadi)"
                )
            except Exception:
                pass

            await send_format_step(bot, order["user_id"], book["id"])
            await try_dispatch_next_admin_task(bot, admin_state.storage)
            return

        await admin_state.set_state(AdminFlow.waiting_page_count)
        await admin_state.update_data(book_id=book["id"])

        if book["source_chat_id"] and book["source_message_id"]:
            try:
                await bot.forward_message(config.ADMIN_ID, book["source_chat_id"], book["source_message_id"])
            except Exception:
                try:
                    await bot.send_document(config.ADMIN_ID, book["file_id"], caption=_plain(f"📎 {book['file_name']}"))
                except Exception:
                    pass

        hint = ""
        if book["ai_analyzed"]:
            warnings = []
            if book["ai_religious_flag"]:
                warnings.append(
                    "🕌⚠️ AI OGOHLANTIRISHI: ushbu faylda arab yozuvi yoki diniy "
                    "tarkib belgilari topilgan bo'lishi mumkin. DIQQAT bilan tekshiring!"
                )
            if book["ai_mixed_orientation"]:
                warnings.append(
                    "📐⚠️ AI OGOHLANTIRISHI: PDF sahifalari ARALASH (ham kitob, "
                    "ham albom ko'rinishida). Turini diqqat bilan tanlang."
                )
            if warnings:
                try:
                    await bot.send_message(config.ADMIN_ID, "\n\n".join(warnings))
                except Exception:
                    pass
            if book["ai_page_count"]:
                hint = f"\n\n🤖 AI aniqlagan sahifalar soni (tasdiqlang yoki to'g'irlang): {book['ai_page_count']}"

        await bot.send_message(
            config.ADMIN_ID,
            f"➡️ Navbatdagi kitob: №{book['seq_num']} ({_plain(book['file_name'])})\n"
            f"Sahifa sonini kiriting:{hint}"
        )

    elif claimed["task_type"] in ("receipt", "receipt_pochta"):
        order = db.get_order(claimed["ref_id"])
        if not order:
            await try_dispatch_next_admin_task(bot, admin_state.storage)
            return

        is_pochta = (claimed["task_type"] == "receipt_pochta")
        expected_status = "awaiting_admin_review_pochta" if is_pochta else "awaiting_admin_review"
        if order["status"] != expected_status:
            # Chek allaqachon boshqa yo'l bilan hal qilingan (masalan mijoz
            # buyurtmani bekor qilgan) - keyingi vazifaga o'tamiz.
            await try_dispatch_next_admin_task(bot, admin_state.storage)
            return

        user = db.get_user(order["user_id"])
        uname = f"@{user['username']}" if user and user["username"] else "—"
        full_name = _plain(user["full_name"]) if user and user["full_name"] else ""

        await admin_state.set_state(AdminFlow.reviewing_receipt)
        await admin_state.update_data(order_id=order["id"], receipt_kind=claimed["task_type"])

        if is_pochta:
            await bot.send_message(
                config.ADMIN_ID,
                f"📮 POCHTA TO'LOVI — {order['order_code']}\n"
                f"👤 {full_name} ({uname})\n"
                f"💰 Pochta narxi: {format_money(order['pochta_narxi'])}"
            )
            file_id = order["pochta_receipt_file_id"]
            receipt_type = order["pochta_receipt_type"]
            markup = kb.kb_admin_accept_pochta(order["id"])
        else:
            books = db.get_books_for_order(order["id"])
            order_label = order["order_code"] or f"So'rov #{order['id']}"
            lines = [f"🆕 YANGI TO'LOV — {order_label}", f"👤 {full_name} ({uname})", ""]
            for b in books:
                if b["status"] != "done":
                    continue
                lines.append(
                    f"📚 №{b['seq_num']}: {b['page_count']} bet, {config.FORMAT_NAMES[b['format_key']]}, "
                    f"{config.BINDING_NAMES[b['binding']]}, {b['copies']} dona — {format_money(b['price'])}"
                )
            lines.append("")
            lines.append(f"💰 Kitoblar uchun: {format_money(order['books_total'])}")
            lines.append("\nℹ️ Yetkazib berish hali tanlanmagan - to'lov tasdiqlangach mijoz o'zi tanlaydi.")
            await bot.send_message(config.ADMIN_ID, "\n".join(lines))
            file_id = order["receipt_file_id"]
            receipt_type = order["receipt_type"]
            markup = kb.kb_admin_accept(order["id"])

        try:
            if receipt_type == "photo":
                await bot.send_photo(config.ADMIN_ID, file_id, reply_markup=markup)
            else:
                await bot.send_document(config.ADMIN_ID, file_id, reply_markup=markup)
        except Exception:
            pass


# ================= /statistika — kunlik/oylik hisobot =================

@router.message(Command("statistika"), F.chat.id == config.ADMIN_ID)
async def cmd_statistika(message: Message):
    await message.answer("📊 Qaysi davr uchun statistika kerak?", reply_markup=kb.kb_statistika_period())


async def _send_statistika_report(bot: Bot, chat_id: int, date_from, date_to, period_label: str):
    """Berilgan sana oralig'i uchun batafsil statistikani matn + Excel fayl
    ko'rinishida yuboradi. `date_from`/`date_to` - `datetime.date` obyektlari."""
    import os
    from utils import build_statistika_workbook

    stats = db.get_detailed_stats(date_from.isoformat(), date_to.isoformat())

    text_lines = [
        f"📊 Statistika — {period_label} ({date_from.strftime('%d.%m')} — {date_to.strftime('%d.%m')})\n",
        f"📦 Jami buyurtmalar: {stats['order_count']}",
        f"📚 Jami kitoblar: {stats['book_count']}",
        f"💰 Jami tushum: {format_money(stats['total_sum'])}",
        f"📈 O'rtacha buyurtma: {format_money(stats['avg_order'])}",
    ]
    await bot.send_message(chat_id, "\n".join(text_lines))

    import tempfile
    output_path = os.path.join(tempfile.gettempdir(), f"statistika_{date_from.isoformat()}_{date_to.isoformat()}.xlsx")
    build_statistika_workbook(
        stats,
        period_label=period_label,
        date_from_label=date_from.strftime('%d.%m.%Y'),
        date_to_label=date_to.strftime('%d.%m.%Y'),
        output_path=output_path,
    )
    try:
        await bot.send_document(chat_id, FSInputFile(output_path), caption="📊 Batafsil statistika (Excel)")
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


@router.callback_query(F.data.startswith("statperiod:"))
async def choose_statperiod(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not admin_only(callback):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    _, period = callback.data.split(":")
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    from datetime import date, timedelta
    today = date.today()

    if period == "today":
        await _send_statistika_report(bot, callback.from_user.id, today, today, "Bugun")
    elif period == "week":
        week_start = today - timedelta(days=today.weekday())  # Dushanba
        await _send_statistika_report(bot, callback.from_user.id, week_start, today, "Shu hafta")
    elif period == "month":
        month_start = today.replace(day=1)
        await _send_statistika_report(bot, callback.from_user.id, month_start, today, "Shu oy")
    elif period == "custom":
        await callback.message.answer("📆 Sana oralig'ini yuboring (masalan: 01.07-28.07 yoki bitta kun: 24.07):")
        await state.set_state(AdminFlow.waiting_stat_date_range)


@router.message(AdminFlow.waiting_stat_date_range, F.chat.id == config.ADMIN_ID)
async def got_stat_date_range(message: Message, state: FSMContext, bot: Bot):
    from datetime import date
    text = (message.text or "").strip()
    year = date.today().year

    m = _DATE_RANGE_RE.match(text)
    if m:
        d1, mo1, d2, mo2 = map(int, m.groups())
        try:
            lo = date(year, mo1, d1)
            hi = date(year, mo2, d2)
        except ValueError:
            await message.answer("❗ Sana noto'g'ri. Masalan: 01.07-28.07")
            return
    else:
        m2 = _SINGLE_DATE_RE.match(text)
        if not m2:
            await message.answer("❗ Format noto'g'ri. Masalan: 01.07-28.07 yoki 24.07")
            return
        d1, mo1 = map(int, m2.groups())
        try:
            lo = hi = date(year, mo1, d1)
        except ValueError:
            await message.answer("❗ Sana noto'g'ri.")
            return

    if hi < lo:
        lo, hi = hi, lo

    await state.clear()
    await _send_statistika_report(bot, message.from_user.id, lo, hi, "Tanlangan davr")


# ================= /fileid — rasm yoki video ID sini olish =================

@router.message(Command("fileid"), F.chat.id == config.ADMIN_ID)
async def cmd_fileid(message: Message, state: FSMContext):
    await message.answer("📎 Endi menga rasm (yoki video) yuboring — men uning file_id sini qaytaraman.")
    await state.set_state(AdminFlow.waiting_file_for_id)


@router.message(AdminFlow.waiting_file_for_id, F.chat.id == config.ADMIN_ID)
async def got_file_for_id(message: Message, state: FSMContext):
    await state.clear()
    if message.photo:
        file_id = message.photo[-1].file_id
        kind = "rasm"
    elif message.video:
        file_id = message.video.file_id
        kind = "video"
    elif message.document:
        file_id = message.document.file_id
        kind = "fayl"
    else:
        await message.answer("❗ Iltimos, rasm, video yoki fayl yuboring.")
        return

    await message.answer(
        f"✅ {kind} qabul qilindi.\n\n"
        f"📋 file_id (nusxalab config.py ga qo'ying):\n\n"
        f"<code>{file_id}</code>",
        parse_mode="HTML"
    )

# ================= ADMIN HOLATINI TOZALASH =================

@router.message(Command("clearadmin"), F.chat.id == config.ADMIN_ID)
async def cmd_clearadmin(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await message.answer("✅ Admin holati tozalandi.")
    await try_dispatch_next_admin_task(bot, state.storage)

# ================= NAVBATDAGI KITOBNI QO'LDA YUBORISH =================

@router.message(Command("navbat"), F.chat.id == config.ADMIN_ID)
async def cmd_navbat(message: Message, bot: Bot, state: FSMContext):
    """Qo'lda navbatni "surish" - agar biror sabab bilan avtomatik ishlamay
    qolsa. Endi bu ham UMUMIY navbatdan (kitob YOKI chek) foydalanadi."""
    current = await state.get_state()
    if current is not None:
        await message.answer("⚠️ Siz hozir band ko'rinasiz (avval joriy ishni tugating).")
        return
    await try_dispatch_next_admin_task(bot, state.storage)


# ================= SAHIFA SONI (admin private chatda yozadi) =================

@router.message(AdminFlow.waiting_page_count, F.chat.id == config.ADMIN_ID)
async def admin_enter_pages(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("❗ Faqat raqam kiriting. Masalan: 126")
        return

    data = await state.get_data()
    book_id = data.get("book_id")
    if not book_id:
        return

    page_count = int(message.text)
    db.update_book(book_id, page_count=page_count, status="awaiting_type")
    book = db.get_book(book_id)

    await message.answer(
        f"✅ {page_count} bet qabul qilindi.\nKitob turini tanlang:",
        reply_markup=kb.kb_admin_book_type(book_id)
    )

    # MUHIM: navbatdagi kitobni HALI YUBORMAYMIZ - avval shu kitob uchun
    # Knijniy/Albom turi tanlanishi (yoki rad etilishi) kerak. "Band"
    # holatini davom ettiramiz, faqat endi sahifa sonini emas, balki tur
    # tanlanishini kutamiz (choose_book_type ichida navbat davom ettiriladi).
    await state.set_state(AdminFlow.waiting_book_type)
    await state.update_data(book_id=book_id)


# ================= KITOB TURI: Knijniy / Albom / Rad etish =================

@router.callback_query(F.data.startswith("btype:"))
async def choose_book_type(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not admin_only(callback):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    _, btype, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    order = db.get_order(book["order_id"])
    user_id = order["user_id"]

    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if btype == "reject":
        db.update_book(book_id, status="rejected", book_type="rejected")
        await callback.message.answer("❌ Kitob rad etildi.")
        await bot.send_message(
            user_id,
            f"❌ Afsuski, «{book['file_name']}» kitobingiz qabul qilinmadi "
            f"(diniy kitob yoki mualliflik huquqi cheklovi sabab bo'lishi mumkin).\n\n"
            f"❓ Savolingiz bo'lsa, murojaat qiling: @{config.SUPPORT_USERNAME}"
        )

        # MIJOZ TARAFIDA HAM AVTOMATIK TOZALASH: mijoz "Bekor qilish"ni o'zi
        # bosishi SHART EMAS. Agar buyurtmada boshqa tasdiqlangan kitob
        # bo'lmasa - butun buyurtma bekor qilinadi va mijoz asosiy menyuga
        # qaytariladi; bo'lsa - qolgan kitoblar bilan davom etish taklif qilinadi.
        remaining = [b for b in db.get_books_for_order(book["order_id"]) if b["status"] == "done"]
        user_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
        user_fsm = FSMContext(storage=state.storage, key=user_key)

        if not remaining:
            db.update_order(book["order_id"], status="cancelled")
            await user_fsm.clear()
            try:
                await bot.send_message(user_id, config.TXT_MAIN_MENU, reply_markup=kb.kb_main_menu())
            except Exception:
                pass
            await user_fsm.set_state(UserFlow.main_menu)
        else:
            try:
                await bot.send_message(user_id, "Yana kitob qo'shasizmi?", reply_markup=kb.kb_add_more(book["order_id"]))
            except Exception:
                pass
            await user_fsm.set_state(UserFlow.sending_books)

        # Rad etilgach ham, shu kitob uchun admin vazifasi tugadi -
        # navbatdagi kitobga o'tamiz. MUHIM: avval state.clear() - aks holda
        # admin hali "waiting_book_type" holatida qolib, dispatcher uni
        # "band" deb hisoblab, HECH NARSA yubormay qolar edi (aynan shu xato
        # tufayli har safar /clearadmin bosish kerak bo'lib qolgan edi).
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return

    db.update_book(book_id, book_type=btype, status="awaiting_format")
    await callback.message.answer(f"✅ Belgilandi: {'📕 Knijniy' if btype=='knijniy' else '📘 Albomniy'}")

    await send_format_step(bot, user_id, book_id)

    # Tur tanlandi - shu kitob uchun ADMIN vazifasi to'liq tugadi (format/
    # nusxa/yetkazishni endi FOYDALANUVCHI o'zi tanlaydi). Shuning uchun
    # AYNAN SHU YERDA navbatdagi kitobni admin ga yuboramiz - lekin avval
    # holatni albatta tozalash SHART (yuqoridagi izohga qarang).
    await state.clear()
    await try_dispatch_next_admin_task(bot, state.storage)


async def send_format_step(bot: Bot, user_id: int, book_id: int):
    """Format bosqichi - 4 (yoki albom uchun 2) tugma, har birida NARX ko'rsatiladi."""
    import os
    book = db.get_book(book_id)
    is_albom = (book["book_type"] == "albom")
    prices = calc_single_copy_prices(book["page_count"])

    format_kb = kb.kb_format_only(book_id, prices, albom=is_albom)
    base_text = config.FORMAT_STEP_TEXT_ALBOM if is_albom else config.FORMAT_STEP_TEXT_KNIJNIY
    caption = f"{book['page_count']} bet\n{base_text}"

    media = list(config.FORMAT_STEP_MEDIA_ALBOM if is_albom else config.FORMAT_STEP_MEDIA)

    # Eski (yagona) sozlamalar bilan moslik: agar yangi ro'yxat bo'sh bo'lsa,
    # eski FORMAT_INFO_IMAGE / ALBOM_INFO_VIDEO ishlatiladi.
    if not media:
        if is_albom and config.ALBOM_INFO_VIDEO:
            media = [{"type": "video", "id": config.ALBOM_INFO_VIDEO}]
        elif not is_albom and os.path.exists(config.FORMAT_INFO_IMAGE):
            media = [{"type": "photo", "id": config.FORMAT_INFO_IMAGE}]

    await send_media_message(
        _BotMessageProxy(bot, user_id), text=caption, media=media, reply_markup=format_kb
    )


class _BotMessageProxy:
    """send_media_message funksiyasi .answer/.answer_photo/.answer_video/.answer_location
    metodlari bor 'message' obyektini kutadi. Bu proxy - bot.send_xxx(chat_id, ...) larni
    xuddi shunday chaqiruvga aylantiradi, shunda bitta funksiya ham callback.message,
    ham to'g'ridan-to'g'ri user_id bilan ishlay oladi."""
    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id

    async def answer(self, text, reply_markup=None):
        await self.bot.send_message(self.chat_id, text, reply_markup=reply_markup)

    async def answer_photo(self, photo, reply_markup=None):
        await self.bot.send_photo(self.chat_id, photo, reply_markup=reply_markup)

    async def answer_video(self, video, reply_markup=None):
        await self.bot.send_video(self.chat_id, video, reply_markup=reply_markup)

    async def answer_location(self, latitude, longitude):
        await self.bot.send_location(self.chat_id, latitude, longitude)


# ================= "ℹ️ Batafsil" TUGMASI =================

@router.callback_query(F.data.startswith("moreinfo:"))
async def more_info(callback: CallbackQuery):
    _, kind, _id = callback.data.split(":")
    await callback.answer()
    if kind == "format":
        media = [{"type": "photo", "id": img} for img in config.FORMAT_DETAILED_IMAGES if img]
        await send_media_message(callback.message, text=config.FORMAT_DETAILED_INFO, media=media)
    elif kind == "binding":
        media = [{"type": "photo", "id": img} for img in config.BINDING_DETAILED_IMAGES if img]
        await send_media_message(callback.message, text=config.BINDING_DETAILED_INFO, media=media)
    elif kind == "albom":
        media = [{"type": "video", "id": config.ALBOM_INFO_VIDEO}] if config.ALBOM_INFO_VIDEO else None
        await send_media_message(callback.message, text=config.ALBOM_DETAILED_INFO, media=media)
    elif kind == "delivery":
        media = [{"type": "photo", "id": config.DELIVERY_DETAILED_IMAGE}] if config.DELIVERY_DETAILED_IMAGE else None
        await send_media_message(callback.message, text=config.DELIVERY_DETAILED_INFO, media=media)


# ================= FORMAT TANLASH (1-bosqich) =================

@router.callback_query(F.data.startswith("fmt:"))
async def choose_format(callback: CallbackQuery, bot: Bot):
    _, format_key, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    single_price = calc_single_copy_prices(book["page_count"])[format_key]
    await callback.message.answer(
        f"✅ Tanlandi: {config.FORMAT_NAMES[format_key]} — {format_money(single_price)}"
    )

    if book["book_type"] == "albom":
        # Albom kitoblar har doim prujinali bo'ladi - pereplyot so'ralmaydi.
        db.update_book(book_id, format_key=format_key, binding="prujina", status="awaiting_copies")
        await callback.message.answer(
            f"📚 Albom kitoblar prujinali muqovada chop etiladi.\n\nNechta nusxa kerak?",
            reply_markup=kb.kb_copies(book_id)
        )
        return

    db.update_book(book_id, format_key=format_key, status="awaiting_binding")
    await send_binding_step(bot, callback.from_user.id, book_id)


async def send_binding_step(bot: Bot, user_id: int, book_id: int):
    """Pereplyot bosqichi (2-bosqich) - Termokley/Prujina, alohida media bilan."""
    binding_kb = kb.kb_binding_only(book_id)
    await send_media_message(
        _BotMessageProxy(bot, user_id),
        text=config.BINDING_STEP_TEXT,
        media=list(config.BINDING_STEP_MEDIA),
        reply_markup=binding_kb
    )


@router.callback_query(F.data.startswith("bindback:"))
async def binding_back(callback: CallbackQuery, bot: Bot):
    """Pereplyot bosqichidan orqaga - formatni qayta tanlash."""
    _, book_id = callback.data.split(":")
    book_id = int(book_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await send_format_step(bot, callback.from_user.id, book_id)


# ================= PEREPLYOT TANLASH (2-bosqich) =================

@router.callback_query(F.data.startswith("bind:"))
async def choose_binding(callback: CallbackQuery):
    _, binding_key, book_id = callback.data.split(":")
    book_id = int(book_id)
    db.update_book(book_id, binding=binding_key, status="awaiting_copies")
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        f"✅ Tanlandi: {config.BINDING_NAMES[binding_key]}\n\nNechta nusxa kerak?",
        reply_markup=kb.kb_copies(book_id)
    )


# ================= NUSXA SONI =================

@router.callback_query(F.data.startswith("copyback:"))
async def copies_back(callback: CallbackQuery, bot: Bot):
    """Nusxa bosqichidan orqaga - pereplyot bosqichiga (albom uchun esa to'g'ridan-to'g'ri formatga) qaytadi."""
    _, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if book["book_type"] == "albom":
        await send_format_step(bot, callback.from_user.id, book_id)
    else:
        await send_binding_step(bot, callback.from_user.id, book_id)


@router.callback_query(F.data.startswith("copies:"))
async def choose_copies(callback: CallbackQuery, state: FSMContext):
    _, val, book_id = callback.data.split(":")
    book_id = int(book_id)
    await callback.answer()

    if val == "other":
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer("✏️ Nusxa sonini kiriting (raqam bilan):")
        await state.update_data(copies_book_id=book_id)
        await state.set_state(UserFlow.waiting_copies)
        return

    # Eski tugmalarni o'chiramiz - tasodifiy qayta bosishning oldini olish uchun
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    copies = int(val)
    book = db.get_book(book_id)
    price = calc_book_price(book["page_count"], book["format_key"], copies)
    db.update_book(book_id, copies=copies, price=price, status="done")
    book = db.get_book(book_id)

    single_price = calc_single_copy_prices(book["page_count"])[book["format_key"]]
    vol = get_volume_count(book["page_count"])
    vol_text = f" ({vol} jild)" if vol > 1 else ""

    await callback.message.answer(
        f"📚 Kitob №{book['seq_num']}\n"
        f"{book['page_count']} bet{vol_text}\n"
        f"{config.FORMAT_NAMES[book['format_key']]}\n"
        f"{config.BINDING_NAMES[book['binding']]}\n"
        f"{copies} ta nusxa\n\n"
        f"💰 {format_money(single_price)} × {copies} = {format_money(price)}"
    )
    await callback.message.answer(
        "Yana kitob qo'shasizmi?",
        reply_markup=kb.kb_add_more(book["order_id"])
    )


# ================= YAKUNIY QABUL QILISH (chek tekshirilgach) =================

@router.callback_query(F.data.startswith("accept:"))
async def admin_accept_order(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not admin_only(callback):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    _, decision, order_id = callback.data.split(":")
    order_id = int(order_id)
    order = db.get_order(order_id)
    user_id = order["user_id"]
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Himoya: agar mijoz admin bosishidan OLDIN buyurtmani o'zi bekor qilgan
    # bo'lsa (yoki boshqa admin allaqachon ko'rib chiqqan bo'lsa) - to'xtatamiz,
    # aks holda bekor qilingan buyurtma "to'landi" deb qayta jonlantirilib qolardi.
    # MUHIM: har qanday holatda ham navbatni davom ettiramiz - aks holda admin
    # "reviewing_receipt" holatida abadiy qotib qolib, navbat to'xtab qolar edi.
    if order["status"] == "cancelled":
        await callback.message.answer("⚠️ Bu buyurtma mijoz tomonidan allaqachon bekor qilingan. Hech narsa qilinmadi.")
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return
    if order["status"] != "awaiting_admin_review":
        await callback.message.answer(
            f"⚠️ Bu buyurtma allaqachon ko'rib chiqilgan (joriy holat: {order['status']}). Hech narsa qilinmadi."
        )
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return

    if decision == "no":
        db.update_order(order_id, status="collecting", receipt_file_id=None)

        # Mijozning botdagi holatini qayta "chek kutilmoqda" rejimiga o'tkazamiz -
        # aks holda mijoz yangi chek yuborsa, bot buni tanimay qoladi (adminga ko'rinmaydi).
        user_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
        user_fsm = FSMContext(storage=state.storage, key=user_key)
        await user_fsm.set_state(UserFlow.waiting_receipt)
        await user_fsm.update_data(order_id=order_id)

        await bot.send_message(user_id, "⚠️ Iltimos, to'lovni to'liq amalga oshiring, yoki to'liq chekni (sana, vaqt va qabul qiluvchi ko'rsatilsin) qayta yuboring.")
        await callback.message.answer("❌ Rad etildi, mijozga xabar yuborildi.")
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return

    db.update_order(order_id, status="paid")
    # Rasmiy buyurtma raqami AYNAN SHU YERDA beriladi - admin tasdiqlagan
    # buyurtmalar bo'yicha ketma-ket, bekor qilingan/kutilayotganlar hisobga kirmaydi.
    order_code = db.finalize_order_code(order_id)
    await bot.send_message(
        user_id,
        f"✅ To'lovingiz tasdiqlandi!\n📌 Buyurtma raqamingiz: {order_code}\n\n"
        f"Endi buyurtmani qanday olib olishingizni tanlang 👇"
    )
    await bot.send_message(user_id, "Qanday olib olasiz?", reply_markup=kb.kb_delivery(order_id))
    await callback.message.answer(f"✅ To'lov qabul qilindi — {order_code}. Mijoz endi yetkazishni tanlaydi.")

    # YANGI: agar mijoz yetkazish/qabul qiluvchi ma'lumotlarini TO'LIQ
    # kiritmasdan "osilib" qolsa - 10 daqiqadan keyin ogohlantirish, yana
    # 10 daqiqadan keyin (jami 20) adminga xabar boradi.
    asyncio.create_task(schedule_delivery_reminder(bot, order_id, user_id, order_code))

    # Chek vazifasi to'liq tugadi - navbatdagi ish (kitob yoki chek) ko'rsatiladi.
    await state.clear()
    await try_dispatch_next_admin_task(bot, state.storage)


async def schedule_delivery_reminder(bot: Bot, order_id: int, user_id: int, order_code: str):
    """To'lov qabul qilingach, agar mijoz yetkazish/qabul qiluvchi
    ma'lumotlarini 10 daqiqada TO'LIQ kiritmasa - ogohlantirish yuboriladi.
    Yana 10 daqiqadan keyin ham tugallanmasa - adminga xabar beriladi
    (buyurtma AVTOMATIK bekor qilinmaydi, faqat xabardor qilinadi)."""
    await asyncio.sleep(600)  # 10 daqiqa
    order = db.get_order(order_id)
    if not order or order["status"] in ("completed", "cancelled"):
        return
    try:
        await bot.send_message(
            user_id,
            "❗ Hamma savollarga javob bering, bo'lmasa buyurtmangiz qabul qilinmaydi "
            "va tayyorlanmaydi."
        )
    except Exception:
        pass

    await asyncio.sleep(600)  # yana 10 daqiqa (jami 20)
    order = db.get_order(order_id)
    if not order or order["status"] in ("completed", "cancelled"):
        return
    try:
        user = db.get_user(user_id)
        uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
        full_name = user["full_name"] if user and user.get("full_name") else "Noma'lum"
        await bot.send_message(
            config.ADMIN_ID,
            f"⚠️ {order_code} — mijoz ({full_name}, {uname}) buyurtmani hali "
            f"oxirigacha yetkazmadi (yetkazish/qabul qiluvchi ma'lumotlari to'liq emas). "
            f"Buyurtma HALI QABUL QILINMAGAN holatda qolmoqda."
        )
    except Exception:
        pass


# ================= POCHTA TO'LOVINI TASDIQLASH (ikkinchi chek) =================

@router.callback_query(F.data.startswith("acceptpochta:"))
async def admin_accept_pochta(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not admin_only(callback):
        await callback.answer("Ruxsat yo'q", show_alert=True)
        return

    _, decision, order_id = callback.data.split(":")
    order_id = int(order_id)
    order = db.get_order(order_id)
    user_id = order["user_id"]
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if order["status"] == "cancelled":
        await callback.message.answer("⚠️ Bu buyurtma mijoz tomonidan allaqachon bekor qilingan. Hech narsa qilinmadi.")
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return
    if order["status"] != "awaiting_admin_review_pochta":
        await callback.message.answer(
            f"⚠️ Bu buyurtma allaqachon ko'rib chiqilgan (joriy holat: {order['status']}). Hech narsa qilinmadi."
        )
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return

    user_key = StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id)
    user_fsm = FSMContext(storage=state.storage, key=user_key)

    if decision == "no":
        db.update_order(order_id, status="awaiting_pochta_receipt", pochta_receipt_file_id=None)

        # Mijozning botdagi holatini qayta "pochta chekini kutish" rejimiga
        # o'tkazamiz - aks holda yangi chek yuborsa, bot buni tanimay qoladi.
        await user_fsm.set_state(UserFlow.waiting_receipt_pochta)
        await user_fsm.update_data(order_id=order_id)

        await bot.send_message(
            user_id,
            "⚠️ Pochta to'lovi cheki to'liq emas yoki noto'g'ri. Iltimos, to'lovni to'liq "
            "amalga oshirib, chekni qayta yuboring."
        )
        await callback.message.answer("❌ Pochta cheki rad etildi, mijozga xabar yuborildi.")
        await state.clear()
        await try_dispatch_next_admin_task(bot, state.storage)
        return

    await callback.message.answer("✅ Pochta to'lovi tasdiqlandi. Buyurtma yakunlanmoqda...")

    # Buyurtmani TO'LIQ yakunlaymiz: foydalanuvchiga xulosa yuboriladi va
    # PRINT guruhiga jo'natiladi. `state` sifatida mijozning FSM konteksti
    # (yuqorida StorageKey orqali qurilgan) uzatiladi - admin emas!
    from handlers_user import finalize_order_after_delivery
    await finalize_order_after_delivery(user_fsm, bot, order_id)

    # Chek vazifasi to'liq tugadi - navbatdagi ish (kitob yoki chek) ko'rsatiladi.
    await state.clear()
    await try_dispatch_next_admin_task(bot, state.storage)


# ================= PRINT XODIMI: FAYL PRINT QILINDI/QILINMADI =================

@router.callback_query(
    F.data.startswith("toggleprint:"),
    F.message.chat.id == config.PRINT_GROUP_ID
)
async def toggle_print_status(callback: CallbackQuery, state: FSMContext):
    """Print guruhidagi tugma bosilganda - darhol belgilanmaydi, avval bosgan
    xodimdan ISMINI yozib yuborishini so'raymiz (chunki xodimlarning alohida
    Telegram akkaunti yo'q). ForceReply orqali - xodimning klaviaturasi
    avtomatik "javob berish" rejimiga o'tadi, alohida bosish shart emas."""
    _, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    if not book:
        await callback.answer("Topilmadi", show_alert=True)
        return

    if book["printed"]:
        await callback.answer("Bu kitob allaqachon print qilingan!", show_alert=True)
        return

    await callback.answer()

    # DIQQAT: bu holat PRINT_GROUP_ID chatidagi, tugmani bosgan ANIQ shaxsga
    # tegishli (FSM state har doim chat+user bo'yicha alohida saqlanadi) -
    # guruhdagi boshqa kishilar bunga aralashmaydi.
    await state.set_state(AdminFlow.waiting_printer_name)
    await state.update_data(printing_book_id=book_id)

    prompt = await callback.message.answer(
        f"✍️ Kitob #{book['seq_num']} — ismingizni yozing:",
        reply_markup=ForceReply(input_field_placeholder="Ismingiz:")
    )
    # So'rov xabarining ID sini saqlaymiz - ism yozilgach buni o'chirib,
    # guruhda ortiqcha xabar qolmasligi uchun.
    await state.update_data(prompt_message_id=prompt.message_id)


@router.message(AdminFlow.waiting_printer_name, F.chat.id == config.PRINT_GROUP_ID)
async def got_printer_name(message: Message, state: FSMContext, bot: Bot):
    """Xodim ismini ForceReply orqali yozgandan keyin:
    1) Kitob 'print qilindi' deb belgilanadi, ism bazaga saqlanadi.
    2) Asl "info" xabari (tugma bilan) TAHRIRLANADI - ism o'sha xabarning
       ICHIGA qo'shiladi, yangi xabar yubormaymiz.
    3) So'rov va javob xabarlari O'CHIRILADI - guruhda ortiqcha narsa
       qolmasligi, faqat bitta yangilangan xabar ko'rinishi uchun."""
    data = await state.get_data()
    book_id = data.get("printing_book_id")
    prompt_message_id = data.get("prompt_message_id")
    if not book_id:
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("❗ Iltimos, ismingizni matn ko'rinishida yozing.")
        return

    await state.clear()

    book = db.get_book(book_id)
    if not book or book["printed"]:
        # Bu yerga kelish mumkin: ikkita xodim BIR XIL kitobga deyarli bir
        # vaqtda "Print qilinishi kerak" bosgan, va boshqasi ulgurib ismini
        # yozib bo'lgan. Ma'lumot buzilmaydi (faqat birinchisi qabul qilinadi),
        # lekin bu xodimga ham xabar beramiz va uning xabarlarini tozalaymiz.
        try:
            already_by = book["printed_by"] if book else "boshqa xodim"
            await message.answer(f"ℹ️ Bu kitobni allaqachon {already_by} print qilib bo'lgan.")
        except Exception:
            pass
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        if prompt_message_id:
            try:
                await bot.delete_message(message.chat.id, prompt_message_id)
            except Exception:
                pass
        return

    db.update_book(book_id, printed=1, printed_by=name)
    book = db.get_book(book_id)

    # Asl "info" xabarini tahrirlaymiz - ism shu xabarning o'ziga qo'shiladi.
    # MUHIM: tugmalarni BUTUNLAY olib tashlamaymiz - muqova/upakovka
    # tugmalari hali kerak bo'lishi mumkin, shuning uchun ularni SAQLAB
    # qolamiz, faqat "Print qilindi" holatini yangilaymiz.
    if book["print_info_chat_id"] and book["print_info_message_id"]:
        order = db.get_order(book["order_id"])
        vol = get_volume_count(book["page_count"])
        vol_text = f" ({vol} jild)" if vol > 1 else ""
        info_text = (
            f"📚 {order['order_code']}-{book['seq_num']}\n"
            f"{book['page_count']} bet{vol_text} | {config.FORMAT_NAMES[book['format_key']]} | "
            f"{config.BINDING_NAMES[book['binding']]} | {book['copies']} dona\n\n"
            f"✅ Print qildi: {name}"
        )
        try:
            await bot.edit_message_text(
                chat_id=book["print_info_chat_id"],
                message_id=book["print_info_message_id"],
                text=info_text,
                reply_markup=kb.kb_book_toggles(
                    book_id,
                    printed=True,
                    cover_printed=bool(book["cover_printed"]) if "cover_printed" in book.keys() else False,
                    packaging_done=bool(book["packaging_done"]) if "packaging_done" in book.keys() else False,
                )
            )
        except Exception:
            pass

    # Buyurtmaning YAGONA guruhdagi rangli status xabarini yangilaymiz
    # (🔴 -> 🟡 -> 🟢, barcha kitoblar print qilingan-qilinmaganiga qarab).
    from utils import refresh_order_print_status
    await refresh_order_print_status(bot, book["order_id"])

    # Tozalik uchun - so'rov ("ismingizni yozing") va xodimning javob xabarini
    # o'chiramiz, guruhda ortiqcha xabar qolib ketmasligi uchun.
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    if prompt_message_id:
        try:
            await bot.delete_message(message.chat.id, prompt_message_id)
        except Exception:
            pass


@router.callback_query(
    F.data.startswith("togglecover:"),
    F.message.chat.id == config.PRINT_GROUP_ID
)
async def toggle_cover_status(callback: CallbackQuery):
    """Muqova chiqarilganini belgilash - ism talab qilmaydi, lekin BIR
    MARTALIK: bir marta "chiqarildi" deb belgilangach, ORQAGA QAYTARIB
    BO'LMAYDI (print tugmasi kabi)."""
    _, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    if not book:
        await callback.answer("Topilmadi", show_alert=True)
        return

    if book["cover_printed"]:
        await callback.answer("Bu kitob uchun muqova allaqachon chiqarilgan!", show_alert=True)
        return

    db.update_book(book_id, cover_printed=1)
    book = db.get_book(book_id)
    await callback.answer("✅ Muqova chiqarildi deb belgilandi")

    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb.kb_book_toggles(
                 book_id,
                 printed=bool(book["printed"]),
                 cover_printed=True,
                 packaging_done=bool(book["packaging_done"]) if "packaging_done" in book.keys() else False,
            )
        )
    except Exception:
        pass
@router.callback_query(
    F.data.startswith("togglepack:"),
    F.message.chat.id == config.PRINT_GROUP_ID
)
async def toggle_packaging_status(callback: CallbackQuery):
    """Upakovka qilinganini belgilash - ism talab qilmaydi, lekin BIR
    MARTALIK: bir marta "qilindi" deb belgilangach, ORQAGA QAYTARIB
    BO'LMAYDI (print tugmasi kabi)."""
    _, book_id = callback.data.split(":")
    book_id = int(book_id)
    book = db.get_book(book_id)
    if not book:
        await callback.answer("Topilmadi", show_alert=True)
        return

    if book["packaging_done"]:
        await callback.answer("Bu kitob uchun upakovka allaqachon qilingan!", show_alert=True)
        return

    db.update_book(book_id, packaging_done=1)
    book = db.get_book(book_id)
    await callback.answer("✅ Upakovka qilindi deb belgilandi")

    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb.kb_book_toggles(
                book_id,
                printed=bool(book["printed"]),
                cover_printed=bool(book["cover_printed"]) if "cover_printed" in book.keys() else False,
                packaging_done=True,
            )
        )
    except Exception:
        pass


# ================= KURYER: YETKAZILDI =================

@router.callback_query(F.data.startswith("delivered:"), F.message.chat.id == config.COURIER_GROUP_ID)
async def mark_delivered(callback: CallbackQuery, bot: Bot):
    _, order_id = callback.data.split(":")
    order_id = int(order_id)
    order = db.get_order(order_id)
    if not order:
        await callback.answer("Topilmadi", show_alert=True)
        return

    from datetime import datetime as dt
    db.update_order(order_id, status="delivered", delivered_at=dt.now().isoformat())
    await callback.answer("✅ Yetkazildi deb belgilandi")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    from utils import update_order_status_header
    await update_order_status_header(bot, order_id, "📬", "MIJOZGA YETKAZILDI")

    try:
        await bot.send_message(
            order["user_id"],
            f"🎉 Buyurtmangiz yetkazildi — {order['order_code']}!\nXaridingiz uchun rahmat 🙏"
        )
    except Exception:
        pass


# ================= "TAYYOR" - PRINT GURUHIDA SANA ORALIG'I BO'YICHA BELGILASH =================

import re
from datetime import date

_DATE_RANGE_RE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})\s*$')
_SINGLE_DATE_RE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})\s*$')


@router.message(Command("tayyor"), F.chat.id == config.PRINT_GROUP_ID)
async def cmd_ready(message: Message, state: FSMContext):
    prompt = await message.answer(
        "📅 Sana oralig'ini yuboring (masalan: 24.07-26.07)\n"
        "Yoki bitta kun uchun: 24.07"
    )
    await state.set_state(AdminFlow.waiting_ready_date_range)
    # Barcha oraliq xabarlarni keyin o'chirish uchun ID larni saqlaymiz
    await state.update_data(cleanup_msg_ids=[message.message_id, prompt.message_id])


@router.message(AdminFlow.waiting_ready_date_range, F.chat.id == config.PRINT_GROUP_ID)
async def got_ready_date_range(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()
    year = date.today().year

    m = _DATE_RANGE_RE.match(text)
    if m:
        d1, mo1, d2, mo2 = map(int, m.groups())
        try:
            lo = date(year, mo1, d1)
            hi = date(year, mo2, d2)
        except ValueError:
            msg = await message.answer("❗ Sana noto'g'ri. Masalan: 24.07-26.07")
            asyncio.create_task(_delayed_delete(message.chat.id, [message.message_id, msg.message_id], delay=10, bot=bot))
            return
    else:
        m2 = _SINGLE_DATE_RE.match(text)
        if not m2:
            msg = await message.answer("❗ Format noto'g'ri. Masalan: 24.07-26.07 yoki 24.07")
            asyncio.create_task(_delayed_delete(message.chat.id, [message.message_id, msg.message_id], delay=10, bot=bot))
            return
        d1, mo1 = map(int, m2.groups())
        try:
            lo = hi = date(year, mo1, d1)
        except ValueError:
            msg = await message.answer("❗ Sana noto'g'ri.")
            asyncio.create_task(_delayed_delete(message.chat.id, [message.message_id, msg.message_id], delay=10, bot=bot))
            return

    if hi < lo:
        lo, hi = hi, lo

    orders = db.get_completed_orders_in_range(lo.isoformat(), hi.isoformat())
    not_printed_orders = db.get_not_fully_printed_orders_in_range(lo.isoformat(), hi.isoformat())

    if not orders:
        if not_printed_orders:
            codes = ", ".join(o["order_code"] for o in not_printed_orders)
            msg = await message.answer(
                f"📭 Bu oraliqda TO'LIQ tayyor (print + muqova + upakovka) buyurtma topilmadi.\n\n"
                f"⚠️ {len(not_printed_orders)} ta buyurtma hali barcha kitoblarida "
                f"\"✅ Print qilindi\", \"✅ Muqova chiqarildi\" va \"✅ Upakovka qilindi\" "
                f"UCHALASI HAM belgilanmagani uchun tayyorga kiritilmadi: {codes}"
            )
        else:
            msg = await message.answer("📭 Bu oraliqda tayyor qilinadigan buyurtma topilmadi.")
        asyncio.create_task(_delayed_delete(message.chat.id, [message.message_id, msg.message_id], delay=10, bot=bot))
        await state.clear()
        return

    order_ids = [o["id"] for o in orders]
    lines = [f"📦 {lo.strftime('%d.%m')} - {hi.strftime('%d.%m')} oralig'ida {len(order_ids)} ta buyurtma topildi:\n"]
    for o in orders:
        lines.append(f"• {o['order_code']}")

    # MUHIM: agar shu oraliqda "completed" statusidagi, lekin hali BARCHA
    # kitoblari print qilinmagan buyurtmalar bo'lsa - adminga alohida
    # ko'rsatamiz, shunda "nega bu buyurtma ro'yxatda yo'q" degan savol
    # tug'ilmaydi (masalan kimdir hali kitob yuborib, print qilinmagan bo'lsa).
    if not_printed_orders:
        lines.append(
            f"\n⚠️ Hali barcha kitoblarida print+muqova+upakovka UCHALASI HAM "
            f"bajarilmagani uchun KIRITILMADI ({len(not_printed_orders)} ta):"
        )
        for o in not_printed_orders:
            lines.append(f"• {o['order_code']}")

    data = await state.get_data()
    cleanup_ids = data.get("cleanup_msg_ids", [])
    cleanup_ids.append(message.message_id)  # foydalanuvchi kiritgan sana

    list_msg = await message.answer("\n".join(lines))
    cleanup_ids.append(list_msg.message_id)

    confirm_msg = await message.answer(
        "Barchasini TAYYOR deb belgilab, mijozlarga xabar yuboraymi?",
        reply_markup=kb.kb_ready_confirm()
    )
    cleanup_ids.append(confirm_msg.message_id)

    await state.update_data(ready_order_ids=order_ids, cleanup_msg_ids=cleanup_ids)
    await state.set_state(AdminFlow.waiting_ready_confirm)


async def _send_ready_message_to_customer(bot: Bot, storage, order, oid: int) -> tuple[bool, str]:
    """Mijozga "✅ Buyurtmangiz tayyor!" xabarini yuboradi.

    Bu funksiya /tayyor (ready_batch_confirm) va /qaytaryubor
    (cmd_resend_ready_notifications) ikkalasida ISHLATILADI - shu bilan
    yuborish mantiqi BITTA joyda saqlanadi.

    MUHIM: mijoz botni bloklamagan, hech narsaga tegmagan bo'lsa ham xabar
    ketmasligining eng ko'p uchraydigan sababi - Telegramning "flood
    control" (bir vaqtda juda ko'p xabar yuborilganda serverning vaqtincha
    "kut" deb qaytargan javobi, TelegramRetryAfter). Bu XATO EMAS, VAQTINCHA
    HOLAT - shuning uchun bu yerda serverning aytgan vaqtini kutib, 3
    martagacha AVTOMATIK qayta uriniladi. Oldingi versiyada bu xato ham
    boshqa xatolar bilan bir xil "except Exception: pass" ostida yo'qolib
    ketardi va hech qachon qayta urinilmasdi.

    Qaytaradi: (muvaffaqiyatli_bo'ldimi, agar_yo'q_bo'lsa_sabab_belgisi)
    sabab_belgisi: "" (muvaffaqiyatli) | "blocked" | "other"
    """
    for attempt in range(3):
        try:
            if order["delivery_type"] == "yandex":
                user_key = StorageKey(bot_id=bot.id, chat_id=order["user_id"], user_id=order["user_id"])
                user_fsm = FSMContext(storage=storage, key=user_key)
                await user_fsm.set_state(UserFlow.waiting_yandex_link)
                await user_fsm.update_data(order_id=oid)

                await bot.send_message(
                    order["user_id"],
                    f"✅ Buyurtmangiz tayyor!\n\n📌 Buyurtma raqami: {order['order_code']}\n\n"
                    f"🚕 Pastdagi Ma'lumotlar tugmasini bosib <Yandex chaqirish> bo'limi orqali dostavka chaqiring.\n\n"
                    f"Buyurtma ma'lumotlarini to'liq yubormasangiz, buyurtmangizni bera olmaymiz. Vaqtingizni qadrlang !:\n"
                    f"Kitobni qo'lingizga olgach, pastdagi tugmani bosing 👇",
                    reply_markup=kb.kb_order_received(oid)
                )
            else:
                await bot.send_message(
                    order["user_id"],
                    f"✅ Buyurtmangiz tayyor!\n\n📌 Buyurtma raqami: {order['order_code']}\n\n"
                    f"Kutib qolamiz 😊",
                    reply_markup=kb.kb_order_received(oid)
                )
            return True, ""
        except TelegramRetryAfter as e:
            import logging
            logging.warning(
                "Flood control (retry_after=%s) - kutib qayta urinamiz | order_id=%s | order_code=%s | urinish=%s",
                e.retry_after, oid, order["order_code"], attempt + 1,
            )
            await asyncio.sleep(e.retry_after + 0.5)
            continue
        except TelegramNetworkError as e:
            import logging
            logging.warning(
                "Tarmoq xatosi, 2 soniyadan keyin qayta urinamiz | order_id=%s | order_code=%s | urinish=%s | xato: %s",
                oid, order["order_code"], attempt + 1, e,
            )
            await asyncio.sleep(2)
            continue
        except TelegramForbiddenError:
            import logging
            logging.warning(
                "Mijoz botni bloklagan, 'tayyor' xabari yetmadi | order_id=%s | order_code=%s | user_id=%s",
                oid, order["order_code"], order["user_id"],
            )
            return False, "blocked"
        except Exception as e:
            import logging
            logging.exception(
                "Mijozga 'tayyor' xabarini yuborib bo'lmadi | order_id=%s | order_code=%s | user_id=%s | xato: %s",
                oid, order["order_code"], order["user_id"], e,
            )
            return False, "other"

    # Uchta urinishdan keyin ham flood control/tarmoq xatosi davom etsa
    import logging
    logging.error(
        "3 marta urinishdan keyin ham yuborib bo'lmadi | order_id=%s | order_code=%s",
        oid, order["order_code"],
    )
    return False, "other"


@router.callback_query(F.data.startswith("readybatch:"), F.message.chat.id == config.PRINT_GROUP_ID)
async def ready_batch_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, action = callback.data.split(":")
    await callback.answer()

    data = await state.get_data()
    cleanup_ids = data.get("cleanup_msg_ids", [])
    chat_id = callback.message.chat.id

    # Barcha oraliq xabarlarni o'chirish (buyruq, so'rov, sana, ro'yxat, tasdiqlash)
    for msg_id in cleanup_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    # Tugmalar biriktirilgan o'z xabarini ham o'chirish
    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.clear()

    if action == "no":
        await bot.send_message(chat_id, "❌ Bekor qilindi.")
        return

    order_ids = data.get("ready_order_ids", [])
    if not order_ids:
        await bot.send_message(chat_id, "❗ Ma'lumot topilmadi, qaytadan /tayyor buyrug'ini bering.")
        return

    from utils import send_to_ready_group, send_to_courier_group
    from datetime import datetime as dt

    sent = 0
    failed_orders = []
    ready_orders = []
    for oid in order_ids:
        order = db.get_order(oid)
        db.update_order(oid, status="ready", ready_at=dt.now().isoformat())
        order = db.get_order(oid)  # yangilangan holatni qayta o'qiymiz
        ready_orders.append(order)

        success, reason = await _send_ready_message_to_customer(bot, state.storage, order, oid)
        if success:
            sent += 1
            db.update_order(oid, ready_notify_failed=0)
        else:
            label = f"{order['order_code']} (bloklagan)" if reason == "blocked" else order["order_code"]
            failed_orders.append(label)
            db.update_order(oid, ready_notify_failed=1)

        # Ketma-ket ko'p mijozga bir zumda yozish Telegramning flood-control
        # chegarasiga urilib qolishi mumkin - shu sababli har bir yuborishdan
        # keyin qisqa tanaffus qilamiz (bu deyarli sezilmaydi, lekin flood
        # xatosi ehtimolini sezilarli kamaytiradi).
        await asyncio.sleep(0.08)

        try:
            await send_to_ready_group(bot, oid)
        except Exception:
            import logging
            logging.exception("send_to_ready_group xato (order_id=%s)", oid)

        if order["delivery_type"] == "universitet":
            try:
                await send_to_courier_group(bot, oid)
            except Exception:
                import logging
                logging.exception("send_to_courier_group xato (order_id=%s)", oid)

    result_lines = [f"✅ {sent}/{len(order_ids)} mijozga xabar yuborildi. Tayyor guruhiga jo'natildi."]
    if failed_orders:
        result_lines.append(
            f"\n⚠️ {len(failed_orders)} ta mijozga xabar YUBORILMADI (ehtimol botni bloklagan): "
            + ", ".join(failed_orders)
        )
        result_lines.append("\nQayta urinish uchun: /qaytaryubor")
    result_msg = await bot.send_message(chat_id, "\n".join(result_lines))

    # Natija xabarini o'chirish - lekin faqat XATOSIZ holatda (guruh
    # tozalikni saqlasin). Agar biror mijozga xabar yuborilmagan bo'lsa,
    # admin ko'rib qolishi uchun xabar O'CHIRILMAYDI.
    if not failed_orders:
        asyncio.create_task(_delayed_delete(chat_id, [result_msg.message_id], delay=15, bot=bot))

    # Nakleyka PDF sini yaratib, PRINT guruhiga yuboramiz - chop etib,
    # qirqib, har bir kitobga yopishtirish uchun.
    #
    # MUHIM: nakleyka HAR BIR KITOB uchun ALOHIDA yasaladi (bitta buyurtmada
    # bir nechta kitob bo'lsa, ularning formati/pereplyoti har xil bo'lishi
    # mumkin - shuning uchun har biriga o'z formatiga mos nakleyka kerak).
    try:
        import os
        from labels import generate_labels_pdf

        label_items = []
        for order in ready_orders:
            for b in db.get_books_for_order(order["id"]):
                if b["status"] != "done":
                    continue
                label_items.append({
                    "order_code": order["order_code"],
                    "receiver_phone": order["receiver_phone"],
                    "format_key": b["format_key"],
                    "binding": b["binding"],
                    "delivery_type": order["delivery_type"],
                    "university": order["university"],
                    "delivery_detail": order["delivery_detail"],
                })

        os.makedirs("labels_tmp", exist_ok=True)
        pdf_path = f"labels_tmp/nakleyka_{dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        generate_labels_pdf(label_items, pdf_path)

        from aiogram.types import FSInputFile
        await bot.send_document(
            config.PRINT_GROUP_ID,
            FSInputFile(pdf_path),
            caption=f"🏷 Nakleykalar — {len(label_items)} ta kitob ({len(ready_orders)} ta buyurtma). Chop etib, qirqib, kitoblarga yopishtiring."
        )
    except Exception as e:
        import logging
        logging.exception("Nakleyka PDF yaratishda xato: %s", e)
        await bot.send_message(chat_id, "⚠️ Nakleyka PDF yaratishda xatolik yuz berdi (loglarga qarang).")


# ================= "TAYYOR" XABARI YETMAGAN MIJOZLARGA QAYTA YUBORISH =================

@router.message(Command("qaytaryubor"), F.chat.id == config.PRINT_GROUP_ID)
async def cmd_resend_ready_notifications(message: Message, bot: Bot, state: FSMContext):
    """/tayyor bosilganda ba'zi mijozlarga "✅ Buyurtmangiz tayyor!" xabari
    YETMAGAN bo'lishi mumkin (eng ko'p uchraydigan sabab: mijoz botni
    bloklab qo'ygan). Bunday buyurtmalar `ready_notify_failed=1` deb
    belgilanadi (qarang: ready_batch_confirm). Bu buyruq o'sha
    buyurtmalarning HAMMASIGA xabarni QAYTA yuborishga urinadi."""
    failed_orders = db.get_ready_notify_failed_orders()
    if not failed_orders:
        await message.answer("✅ Hozircha yuborilmay qolgan 'tayyor' xabari yo'q.")
        return

    resent = []
    still_failed = []

    for order in failed_orders:
        oid = order["id"]
        success, reason = await _send_ready_message_to_customer(bot, state.storage, order, oid)
        if success:
            db.update_order(oid, ready_notify_failed=0)
            resent.append(order["order_code"])
        else:
            label = f"{order['order_code']} (bloklagan)" if reason == "blocked" else order["order_code"]
            still_failed.append(label)
        await asyncio.sleep(0.08)

    lines = []
    if resent:
        lines.append(f"✅ {len(resent)} ta mijozga xabar QAYTA yuborildi: " + ", ".join(resent))
    if still_failed:
        lines.append(
            f"\n❌ {len(still_failed)} ta mijozga HALI HAM yuborib bo'lmadi "
            f"(botni bloklagan bo'lishi mumkin, mijozga boshqa yo'l bilan xabar berish kerak): "
            + ", ".join(still_failed)
        )
    await message.answer("\n".join(lines))


# ================= YORDAMCHI: kechikib o'chirish =================

async def _delayed_delete(chat_id: int, message_ids: list, delay: int = 10, bot: Bot = None):
    """Xabarlarni N soniyadan keyin o'chirish (guruhda tozalik uchun)."""
    await asyncio.sleep(delay)
    if bot is None:
        return
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
