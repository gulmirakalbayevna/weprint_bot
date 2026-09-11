import asyncio
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.filters import CommandStart, Command

import config
import database as db
import keyboards as kb
from states import UserFlow, AdminFlow
from utils import calc_book_price, calc_single_copy_prices, get_volume_count, order_summary_text, format_money, send_media_message
from locks import admin_queue_lock

router = Router()


# ================= START / TELEFON =================

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    existing_user = db.get_user(message.from_user.id)

    if existing_user and existing_user["phone"]:
        # Foydalanuvchi avval ro'yxatdan o'tgan - telefonni qayta so'ramaymiz
        db.upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
        await message.answer(config.TXT_MAIN_MENU, reply_markup=kb.kb_main_menu())
        await state.set_state(UserFlow.main_menu)
        return

    db.upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(config.TXT_WELCOME, reply_markup=kb.kb_phone())
    await state.set_state(UserFlow.waiting_phone)


@router.message(Command("cancel"))
@router.message(Command("stop"))
async def cmd_cancel(message: Message, state: FSMContext):
    await cancel_order(message, state)


@router.message(UserFlow.waiting_phone, F.contact)
async def got_phone(message: Message, state: FSMContext):
    db.upsert_user(message.from_user.id, message.from_user.full_name,
                    message.from_user.username, phone=message.contact.phone_number)
    await message.answer("✅ Rahmat!", reply_markup=kb.remove_kb())
    await message.answer(config.TXT_MAIN_MENU, reply_markup=kb.kb_main_menu())
    await state.set_state(UserFlow.main_menu)


# ================= ASOSIY MENYU =================

async def _block_if_mid_order(message: Message, state: FSMContext) -> bool:
    """
    True qaytarsa - foydalanuvchi hozir buyurtma jarayonining biror bosqichida
    (fayl yuborish, sahifa/format/chek kutish va h.k.), shuning uchun asosiy
    menyu tugmalari (Buyurtmalarim, Narxni hisoblash, Ma'lumotlar, qayta
    Buyurtma berish) VAQTINCHA band qilinadi - avval joriy ishni tugatishi
    kerak. Mijoz to'lovni yuborib, admin javobini kutayotgan bo'lsa (ortga
    qaytish/bekor qilish imkoniyati YO'Q), buni alohida xabar bilan tushuntiramiz.
    """
    current = await state.get_state()
    if current == UserFlow.awaiting_payment_review.state:
        await message.answer(
            "❗ Buyurtma ma'lumotlarini to'liq yakunlamasangiz, buyurtmangizni qabul qila olmaymiz.\n\n"
            "Iltimos, to'lovingiz admin tomonidan tekshirilishini kuting."
        )
        return True
    if current not in (None, UserFlow.main_menu.state):
        await message.answer(
            "⚠️ Iltimos, avval joriy ishni tugating yoki pastdagi \"❌ Bekor qilish\" tugmasini bosing."
        )
        return True
    return False


@router.message(F.text == "📦 Buyurtmalarim")
async def my_orders(message: Message, state: FSMContext):
    if await _block_if_mid_order(message, state):
        return
    orders = db.get_orders_for_user(message.from_user.id)
    if not orders:
        await message.answer("📭 Sizda hali buyurtmalar yo'q.")
        return

    # Faqat TO'LOV hali tasdiqlanmagan bosqichda o'zi bekor qila oladi.
    # Pul admin tomonidan qabul qilingandan (status='paid') keyin - endi mustaqil
    # bekor qilish YO'Q, chunki pul allaqachon qabul qilingan va buyurtma chop
    # etilayotgan bo'lishi mumkin. Bunday holatda admin bilan bog'lanish kerak.
    CANCELLABLE_STATUSES = {"awaiting_admin_review"}

    await message.answer("📦 Sizning buyurtmalaringiz:")
    for o in orders:
        code = o["order_code"] or f"So'rov #{o['id']} (hali tasdiqlanmagan)"
        label = config.ORDER_STATUS_LABELS.get(o["status"], o["status"])
        total = o["grand_total"] or o["books_total"] or 0
        text = f"{code} — {label}"
        if total:
            text += f"\n💰 {total:,} so'm".replace(",", " ")

        POST_PAYMENT_STATUSES = {"paid", "awaiting_pochta_receipt", "awaiting_admin_review_pochta"}

        if o["status"] in CANCELLABLE_STATUSES:
            await message.answer(text, reply_markup=kb.kb_cancel_specific_order(o["id"]))
        elif o["status"] in POST_PAYMENT_STATUSES:
            text += f"\n\nℹ️ To'lov qabul qilingan. O'zgartirish kerak bo'lsa, admin bilan bog'laning: @{config.SUPPORT_USERNAME}"
            await message.answer(text)
        else:
            await message.answer(text)


@router.callback_query(F.data.startswith("cancelorder:"))
async def cancel_specific_order(callback: CallbackQuery):
    """Buyurtmalarim ro'yxatidan - hali yakunlanmagan (osilib qolgan) buyurtmani
    foydalanuvchi o'zi bekor qila oladi."""
    _, order_id = callback.data.split(":")
    order_id = int(order_id)
    order = db.get_order(order_id)

    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Topilmadi", show_alert=True)
        return

    db.update_order(order_id, status="cancelled")
    await callback.answer("❌ Bekor qilindi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.edit_text(callback.message.text + "\n\n❌ BEKOR QILINDI")
    except Exception:
        pass


@router.message(F.text == "💰 Narxni hisoblash")
async def price_calc(message: Message, state: FSMContext):
    if await _block_if_mid_order(message, state):
        return
    await message.answer("Narxni saytimiz orqali hisoblashingiz mumkin 👇", reply_markup=kb.kb_price_calc())


@router.message(F.text == "ℹ️ Ma'lumotlar")
async def info(message: Message, state: FSMContext):
    if await _block_if_mid_order(message, state):
        return
    await message.answer(config.TXT_INFO, reply_markup=kb.kb_faq())


@router.callback_query(F.data.startswith("faq:"))
async def faq_answer(callback: CallbackQuery):
    _, key = callback.data.split(":")
    await callback.answer()
    item = config.FAQ_ANSWERS.get(key)
    if not item:
        await callback.message.answer("Ma'lumot topilmadi.")
        return

    text = item["text"].format(support=config.SUPPORT_USERNAME)
    media = item.get("media", [])
    await send_media_message(callback.message, text=text, media=media)


@router.message(F.text == "📚 Buyurtma berish")
async def start_order(message: Message, state: FSMContext):
    if await _block_if_mid_order(message, state):
        return
    existing = db.get_active_order_for_user(message.from_user.id)
    if existing:
        books = db.get_books_for_order(existing["id"])
        if books:
            await message.answer(
                f"⚠️ Sizda tugallanmagan buyurtma bor ({len(books)} ta kitob).\n\n"
                f"Uni davom ettirasizmi yoki yangidan boshlaysizmi?",
                reply_markup=kb.kb_resume_or_fresh(existing["id"])
            )
            return

    await begin_new_order(message, state)


async def begin_new_order(message: Message, state: FSMContext):
    order_id = db.create_order(message.from_user.id)
    await state.update_data(order_id=order_id)
    await message.answer(config.TXT_WARNING, reply_markup=kb.kb_cancel_persistent())
    await state.set_state(UserFlow.sending_books)


@router.callback_query(F.data.startswith("resume:"))
async def resume_order_choice(callback: CallbackQuery, state: FSMContext):
    _, action, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    if action == "fresh":
        # Xuddi shu sababga ko'ra (yuqoridagi cancel_order izohiga qarang) -
        # bekor qilinadigan buyurtmani callback_data dagi (eskirgan bo'lishi
        # mumkin bo'lgan) order_id o'rniga, bazadan yangidan tekshirib olamiz.
        existing = db.get_active_order_for_user(callback.from_user.id)
        if existing:
            db.update_order(existing["id"], status="cancelled")
        await callback.message.answer("🆕 Eski buyurtma bekor qilindi, yangisini boshlaymiz.")
        await begin_new_order(callback.message, state)
    else:
        await state.update_data(order_id=order_id)
        await callback.message.answer(
            "➡️ Davom etamiz. Yana kitob yuborishingiz yoki davom etish tugmasini bosishingiz mumkin.",
            reply_markup=kb.kb_cancel_persistent()
        )
        await callback.message.answer(
            "Yana kitob qo'shasizmi?",
            reply_markup=kb.kb_add_more(order_id)
        )
        await state.set_state(UserFlow.sending_books)


@router.message(F.text == "❌ Bekor qilish")
async def cancel_order(message: Message, state: FSMContext):
    # MUHIM TUZATISH: buyurtma ID sini endi FSM holatidan (vaqtinchalik
    # xotira) emas, TO'G'RIDAN-TO'G'RI BAZADAN olamiz. Sabab: agar FSM
    # holati biror sababga ko'ra yo'qolgan/eskirgan bo'lsa (masalan bot
    # qayta ishga tushirilgan bo'lsa), eski usul bilan buyurtma bazada
    # 'collecting' holatida QOLIB KETARDI - foydalanuvchiga "bekor
    # qilindi" ko'rsatilsa ham. Keyinroq "📚 Buyurtma berish" bossa, bot
    # o'sha ESKI (aslida bekor qilingan) buyurtmani "tugallanmagan
    # buyurtma" deb qayta taklif qilardi.
    existing = db.get_cancellable_order_for_user(message.from_user.id)
    order_id = existing["id"] if existing else None

    if order_id:
        order = db.get_order(order_id)
        # To'lov ALLAQACHON qabul qilingan bo'lsa (yoki undan keyingi bosqichda -
        # yetkazish tanlash, pochta to'lovi va h.k.) - ENDI mustaqil bekor qilib
        # bo'lmaydi. Aks holda pul admin tomonidan qabul qilingan bo'lsa ham,
        # buyurtma adminga ko'rinmasdan "bekor" bo'lib qolar edi.
        if order and order["status"] not in ("collecting", "awaiting_admin_review"):
            await message.answer(
                f"⚠️ Bu buyurtma uchun to'lov allaqachon qabul qilingan, shuning "
                f"uchun mustaqil bekor qila olmaysiz.\n\n"
                f"Bekor qilish yoki o'zgartirish kerak bo'lsa, adminga murojaat "
                f"qiling: @{config.SUPPORT_USERNAME}"
            )
            return
        db.update_order(order_id, status="cancelled")

    await state.clear()
    await message.answer("❌ Buyurtma bekor qilindi.", reply_markup=kb.remove_kb())
    await message.answer(config.TXT_MAIN_MENU, reply_markup=kb.kb_main_menu())
    await state.set_state(UserFlow.main_menu)


# ================= PDF/WORD QABUL QILISH =================

@router.message(UserFlow.sending_books, F.document)
async def got_document(message: Message, state: FSMContext, bot: Bot):
    # Telegram bir nechta fayl birga (bitta xabar guruhi sifatida) yuborilganda
    # ularga umumiy media_group_id beradi. Agar shu aniqlansa - HECH BIRINI
    # qabul qilmaymiz, chunki alohida-alohida qayta ishlash mumkin emas va
    # narxni to'g'ri hisoblab bo'lmaydi.
    if message.media_group_id:
        data = await state.get_data()
        if data.get("last_warned_media_group") != message.media_group_id:
            await message.answer(
                "⚠️ Iltimos, fayllarni BITTA-BITTA yuboring (bir nechtasini birdaniga "
                "tanlab yubormang).\n\nBo'lmasa buyurtmangizni admin ko'ra olmaydi."
            )
            await state.update_data(last_warned_media_group=message.media_group_id)
        return

    data = await state.get_data()
    order_id = data.get("order_id") or db.create_order(message.from_user.id)
    await state.update_data(order_id=order_id)

    # Bitta fayl to'liq tugallanmasdan (sahifa soni, format, nusxa - hammasi
    # admin tomonidan tasdiqlanmasdan) ikkinchi faylni qabul qilmaymiz -
    # bu chalkashishning oldini oladi.
    unfinished = db.get_unfinished_book_for_order(order_id)
    if unfinished:
        await message.answer(
            f"⏳ \"{unfinished['file_name']}\" fayli hali to'liq qayta ishlanmagan.\n\n"
            f"Iltimos, avval shu kitob uchun barcha ma'lumotlar (sahifa soni, format, nusxa) "
            f"tasdiqlanishini kuting, keyin yangi fayl yuboring."
        )
        return

    book_id = db.add_book(
        order_id, message.document.file_id, message.document.file_name,
        source_chat_id=message.chat.id, source_message_id=message.message_id
    )
    book = db.get_book(book_id)

    await message.answer(f"✅ Fayl qabul qilindi\n📎 {message.document.file_name}\n\n⏳ Admin tekshirmoqda...")

    # --- AI PRECHECK: fayl PDF bo'lsa, admin ishini yengillatish uchun
    # avtomatik tahlil qilamiz (sahifa soni, orientatsiya, arab/diniy belgi).
    # QISQA VAQT CHEGARASI bilan: tezkor internetda AI ulguradi, sekin
    # bo'lsa - jim voz kechiladi va admin BEKORGA KUTIB QOLMAYDI.
    if config.AI_PRECHECK_ENABLED and message.document.file_name.lower().endswith(".pdf"):
        try:
            await asyncio.wait_for(
                _run_ai_precheck(book_id, message.document.file_id, bot), timeout=60.0
            )
        except asyncio.TimeoutError:
            logging.warning(
                "AI precheck: 60 soniyada ulgurmadi (book_id=%s) - qo'lda davom etiladi",
                book_id,
            )
        except Exception:
            logging.exception(
                "AI precheck ishlamadi (book_id=%s) - qo'lda davom etiladi", book_id
            )

    # MUHIM: bu kitob endi ADMIN UCHUN UMUMIY NAVBATGA qo'shiladi (kitoblar
    # VA cheklar bitta navbatda). Agar admin band bo'lmasa, DARHOL ko'rsatiladi;
    # band bo'lsa (masalan boshqa kitob yoki chek bilan ishlayotgan bo'lsa) -
    # jim navbatda kutadi, admin bo'shagach o'z-o'zidan chiqadi. Shu bilan
    # kitoblar va to'lovlar hech qachon bir-birining ustiga chiqib ketmaydi.
    db.create_admin_task("book", book_id)
    from handlers_admin import try_dispatch_next_admin_task
    await try_dispatch_next_admin_task(bot, state.storage)


async def _run_ai_precheck(book_id: int, file_id: str, bot: Bot):
    """PDF'ni yuklab olib, AI tahlil qilib, natijani bazaga yozadi.
    (Tashqarida asyncio.wait_for bilan vaqt chegaralanadi.)"""
    import os as _os

    _os.makedirs("ai_tmp", exist_ok=True)
    tmp_path = f"ai_tmp/book_{book_id}.pdf"
    try:
        import ai_precheck

        await bot.download(file_id, destination=tmp_path)

        analysis = ai_precheck.analyze_pdf(tmp_path)
        if analysis.get("ok"):
            db.update_book(
                book_id,
                ai_analyzed=1,
                ai_page_count=analysis["page_count"],
                ai_book_type_guess=analysis["book_type_guess"],
                ai_mixed_orientation=int(analysis["is_mixed_orientation"]),
                ai_religious_flag=int(analysis["has_religious_flag"]),
            )
            logging.info(
                "AI tahlili OK (book_id=%s): %s bet, tur=%s, aralash=%s, diniy_flag=%s",
                book_id, analysis["page_count"], analysis["book_type_guess"],
                analysis["is_mixed_orientation"], analysis["has_religious_flag"],
            )
        else:
            logging.warning(
                "AI tahlili BAJARILMADI (book_id=%s): %s — qo'lda davom etiladi",
                book_id, analysis.get("reason"),
            )
    finally:
        try:
            _os.remove(tmp_path)
        except Exception:
            pass


@router.message(UserFlow.sending_books)
async def got_non_document_in_sending_books(message: Message):
    """MUHIM: yuqoridagi handler faqat F.document (fayl) ni ushlaydi. Agar
    mijoz shu bosqichda rasm, matn, stiker va h.k. yuborsa - avvalgi kodda
    HECH QANDAY handler mos kelmasdi va bot JIM qolib ketardi (mijoz hech
    qanday javob olmasdi, botni "ishlamayapti" deb o'ylashi mumkin edi).
    Endi bunday hollarda aniq yo'riqnoma beriladi."""
    await message.answer(
        "❗ Iltimos, kitobingizni FAQAT fayl (PDF yoki Word) ko'rinishida yuboring.\n\n"
        "Rasm, matn yoki boshqa turdagi xabar qabul qilinmaydi."
    )


# ================= NUSXA SONI: "Boshqa" tanlanganda son kiritish =================

@router.message(UserFlow.waiting_copies)
async def got_custom_copies(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting. Masalan: 7")
        return
    data = await state.get_data()
    book_id = data.get("copies_book_id")
    if not book_id:
        return
    await finalize_copies(message, state, bot, book_id, int(message.text))


async def finalize_copies(message: Message, state: FSMContext, bot: Bot, book_id: int, copies: int):
    book = db.get_book(book_id)
    price = calc_book_price(book["page_count"], book["format_key"], copies)
    db.update_book(book_id, copies=copies, price=price, status="done")
    book = db.get_book(book_id)

    single_price = calc_single_copy_prices(book["page_count"])[book["format_key"]]
    vol = get_volume_count(book["page_count"])
    vol_text = f" ({vol} jild)" if vol > 1 else ""

    from utils import book_summary_text
    await message.answer(
        f"📚 Kitob №{book['seq_num']}\n"
        f"{book['page_count']} bet{vol_text}\n"
        f"{config.FORMAT_NAMES[book['format_key']]}\n"
        f"{config.BINDING_NAMES[book['binding']]}\n"
        f"{copies} ta nusxa\n\n"
        f"💰 {format_money(single_price)} × {copies} = {format_money(price)}",
    )
    await message.answer(
        "Yana kitob qo'shasizmi?",
        reply_markup=kb.kb_add_more(book["order_id"])
    )
    await state.set_state(UserFlow.sending_books)


# ================= "Yana kitob qo'shish" / "Davom etish" =================

@router.callback_query(F.data.startswith("more:"))
async def more_books(callback: CallbackQuery, state: FSMContext):
    _, action, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    if action == "add":
        await callback.message.answer("📄 Keyingi kitob faylini yuboring.")
        await state.set_state(UserFlow.sending_books)
    else:
        summary, total = order_summary_text(order_id)
        db.update_order(order_id, books_total=total, grand_total=total)
        await callback.message.answer(f"🧾 Buyurtma xulosasi:\n\n{summary}")
        await show_payment_qr(callback.message, state, order_id)


# ================= YETKAZIB BERISH =================

@router.callback_query(F.data.startswith("delback:"))
async def delivery_back(callback: CallbackQuery, state: FSMContext):
    _, step, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if step == "addmore":
        await callback.message.answer(
            "Yana kitob qo'shasizmi?",
            reply_markup=kb.kb_add_more(order_id)
        )
    elif step == "delivery":
        await callback.message.answer(
            "Buyurtmani qanday qabul qilib olasiz?",
            reply_markup=kb.kb_delivery(order_id)
        )


@router.callback_query(F.data.startswith("deliv:"))
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
    _, dtype, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    # Tanlangandan keyin eski tugmalarni o'chiramiz - aks holda foydalanuvchi
    # shu eski xabardagi boshqa tugmani bosib, "orqaga" bosmasdan turib
    # tanlovni sezmasdan o'zgartirib qo'yishi mumkin edi.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if dtype == "pickup":
        # delivery_detail va university - avvalgi tanlovdan qolgan bo'lishi mumkin
        # (masalan orqaga qaytib boshqa turni tanlashda) - tozalanadi, aks holda
        # eski manzil/universitet nomi yakuniy buyurtmada "yopishib" ko'rinib qoladi.
        db.update_order(order_id, delivery_type="pickup", pochta_narxi=0, delivery_detail=None, university=None)
        await ask_receiver_phone(callback.message, state, order_id)

    elif dtype == "yandex":
        db.update_order(order_id, delivery_type="yandex", pochta_narxi=0, delivery_detail=None, university=None)
        await callback.message.answer(
            "🚕 Yandex/Uklon orqali yetkazish pullik xizmat — kitobingiz tayyor bo'lgach, "
            "taxini o'zingiz chaqirasiz. Batafsil ma'lumot uchun Ma'lumotlar bo'limidagi "
            "\"🚕 Yandex chaqirish\" tugmasidan foydalanishingiz mumkin."
        )
        await ask_receiver_phone(callback.message, state, order_id)

    elif dtype == "viloyat":
        db.update_order(order_id, university=None)
        await send_media_message(
            callback.message,
            "Qanday yuboramiz?",
            media=[{"type": "photo", "id": config.DELIVERY_INFO_IMAGE}] if config.DELIVERY_INFO_IMAGE else None,
            reply_markup=kb.kb_viloyat_type(order_id)
        )

    elif dtype == "univer":
        db.update_order(order_id, delivery_detail=None)
        await callback.message.answer("🎓 Universitetingizni tanlang:", reply_markup=kb.kb_universitet(order_id))


@router.callback_query(F.data.startswith("vtype:"))
async def choose_viloyat_type(callback: CallbackQuery, state: FSMContext):
    _, vtype, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if vtype == "bts":
        db.update_order(order_id, delivery_type="viloyat_bts", pochta_narxi=0, university=None)
        await callback.message.answer(
            "🚛 BTS orqali yetkazish haqini QABUL QILUVCHI to'laydi.\n\n📍 Aniq manzilingizni kiriting:",
            reply_markup=kb.kb_cancel_and_back()
        )
    else:
        books = db.get_books_for_order(order_id)
        # Pochta narxi KITOB soniga emas, JAMI JILD soniga qarab hisoblanadi -
        # chunki masalan 900 betlik 1 ta kitob avtomatik 3 jildga bo'linadi,
        # va jismonan pochta orqali ketadigan narsa 1 emas, 3 ta bo'lak bo'ladi.
        total_jild = sum(get_volume_count(b["page_count"]) * (b["copies"] or 1) for b in books if b["status"] == "done")
        pochta_narxi = config.get_pochta_narxi(total_jild)
        db.update_order(order_id, delivery_type="viloyat_pochta", pochta_narxi=pochta_narxi, university=None)
        await callback.message.answer(
            f"📮 Oddiy pochta narxi: {format_money(pochta_narxi)} ({total_jild} jild uchun)\n"
            f"Kitobingizni jo'natish uchun pochta haqi oldindan to'lanadi.\n\n"
            f"📍 Aniq manzilingizni kiriting:",
            reply_markup=kb.kb_cancel_and_back()
        )

    await state.update_data(order_id=order_id, delivery_mode="viloyat")
    await state.set_state(UserFlow.waiting_delivery_address)


@router.message(UserFlow.waiting_delivery_address, lambda m: bool(m.text) and not m.text.startswith("🔙"))
async def got_address(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data["order_id"]
    db.update_order(order_id, delivery_detail=message.text)
    await ask_receiver_phone(message, state, order_id)


@router.message(UserFlow.waiting_delivery_address, lambda m: not (m.text and m.text.startswith("🔙")))
async def got_address_invalid(message: Message):
    """Manzil bosqichida matn bo'lmagan narsa (rasm, fayl va h.k.) yuborilsa -
    qabul qilinmaydi, faqat matn kiritishni so'raymiz."""
    await message.answer("❗ Iltimos, manzilni FAQAT matn (yozuv) ko'rinishida yuboring — rasm yoki fayl emas.")


@router.callback_query(F.data.startswith("univer:"))
async def choose_univer(callback: CallbackQuery, state: FSMContext):
    _, uni_name, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    # Universitet tanlangandan keyin ro'yxat tugmalarini o'chiramiz - aks holda
    # foydalanuvchi eski ro'yxatdan boshqa universitetni bosib, "orqaga"siz
    # tanlovni sezmasdan almashtirib qo'yishi mumkin edi.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    db.update_order(order_id, delivery_type="universitet", university=uni_name, pochta_narxi=0, delivery_detail=None)
    await ask_receiver_phone(callback.message, state, order_id)


# ================= OLIB KETUVCHI TELEFON RAQAMI =================

async def ask_receiver_phone(message: Message, state: FSMContext, order_id: int):
    order = db.get_order(order_id)
    user = db.get_user(order["user_id"]) if order else None
    reg_phone = user["phone"] if user and user["phone"] else None

    await message.answer(
        "📞 Kim qabul qiladi?",
        reply_markup=kb.kb_receiver_phone(order_id, reg_phone)
    )
    await state.update_data(order_id=order_id)


@router.callback_query(F.data.startswith("rphone:"))
async def choose_receiver_phone(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, choice, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if choice == "self":
        order = db.get_order(order_id)
        user = db.get_user(order["user_id"]) if order else None
        phone = user["phone"] if user and user["phone"] else "—"
        await finalize_receiver_phone(callback.message, state, bot, order_id, phone)
    else:
        await callback.message.answer(
            "📞 Qabul qiluvchining telefon raqamini kiriting:",
            reply_markup=kb.kb_cancel_and_back()
        )
        await state.update_data(order_id=order_id)
        await state.set_state(UserFlow.waiting_receiver_phone)


async def finalize_receiver_phone(message: Message, state: FSMContext, bot: Bot, order_id: int, phone_text: str):
    db.update_order(order_id, receiver_phone=phone_text)
    order = db.get_order(order_id)

    if order["delivery_type"] == "viloyat_pochta" and order["pochta_narxi"]:
        # Taksichiga kitobni berish uchun taksichi OLDINDAN pul so'raydi -
        # shuning uchun oddiy pochta narxi ham buyurtma yakunlanishidan OLDIN
        # to'lanishi shart. Ikkinchi QR + admin tasdig'i talab qilinadi.
        await ask_pochta_payment(message, state, order_id)
    else:
        await finalize_order_after_delivery(state, bot, order_id)


async def ask_pochta_payment(message: Message, state: FSMContext, order_id: int):
    order = db.get_order(order_id)
    db.update_order(order_id, status="awaiting_pochta_receipt")

    await message.answer(
        f"📮 Yetkazib berish (pochta) narxi: {format_money(order['pochta_narxi'])}\n\n"
        f"Kitobingizni yetkazishimiz uchun ushbu summani OLDINDAN to'lashingiz kerak "
        f"(Buyurtmangiz Faqat Viloyat markazigacha boradi).\n\n"
        f"💳 Shu summa uchun to'lov qilib, chek (PDF yoki JPG rasm) yuboring."
    )

    caption = f"💳 Pochta narxi uchun to'lov qiling va chek yuboring.\n\n📌 Buyurtma: {order['order_code']}"
    if _qr_exists():
        await message.answer_photo(photo=FSInputFile(config.QR_CODE_IMAGE), caption=caption, reply_markup=kb.remove_kb())
    else:
        await message.answer("⚠️ To'lov QR kodi hali sozlanmagan (admin qo'shishi kerak).\n\n" + caption, reply_markup=kb.remove_kb())

    await state.update_data(order_id=order_id)
    await state.set_state(UserFlow.waiting_receipt_pochta)


@router.message(UserFlow.waiting_receipt_pochta, F.photo | F.document)
async def got_pochta_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    receipt_type = "photo" if message.photo else "document"
    db.update_order(
        order_id,
        pochta_receipt_file_id=file_id,
        pochta_receipt_type=receipt_type,
        status="awaiting_admin_review_pochta"
    )

    order = db.get_order(order_id)

    await message.answer("✅ Pochta to'lovi cheki qabul qilindi, admin tekshirmoqda. Tez orada javob beramiz!",
                          reply_markup=kb.remove_kb())

    # Xuddi oddiy chek kabi - umumiy admin navbatiga qo'shiladi.
    db.create_admin_task("receipt_pochta", order_id)
    from handlers_admin import try_dispatch_next_admin_task
    await try_dispatch_next_admin_task(bot, state.storage)

    asyncio.create_task(schedule_admin_reminder(bot, order_id, order["order_code"]))

    # MUHIM: bu yerda ham state.clear() qilinmaydi - sabab yuqoridagi
    # got_receipt funksiyasidagi izohda tushuntirilgan.
    await state.set_state(UserFlow.awaiting_payment_review)


@router.message(UserFlow.waiting_yandex_link)
async def got_yandex_link(message: Message, state: FSMContext, bot: Bot):
    """Mijoz taksi (Yandex/Uklon) havolasi + telefon raqamini yuborganda,
    shu ma'lumotni buyurtma raqami bilan birga Yandex dostavka guruhiga
    jo'natadi - guruhdagilar aynan qaysi buyurtma ekanini bilishi uchun."""
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        return

    order = db.get_order(order_id)

    if config.YANDEX_GROUP_ID:
        try:
            await bot.send_message(
                config.YANDEX_GROUP_ID,
                f"🚕 YANDEX/UKLON — {order['order_code']}\n\n"
                f"{message.text or ''}"
            )
        except Exception:
            import logging
            logging.exception("Yandex guruhiga yuborishda xato (order_id=%s)", order_id)

    await message.answer(
        "✅ Ma'lumot qabul qilindi, buyurtmangizni kuryerga beramiz. Rahmat! 🙏",
        reply_markup=kb.kb_main_menu()
    )
    await state.clear()
    await state.set_state(UserFlow.main_menu)


@router.callback_query(F.data.startswith("received:"))
async def mark_order_received(callback: CallbackQuery, bot: Bot):
    """Mijoz 'Oldim' tugmasini bosganda - buyurtma holati 'Olindi' deb
    belgilanadi. Faqat shu buyurtmaning egasi bosa oladi."""
    _, order_id = callback.data.split(":")
    order_id = int(order_id)
    order = db.get_order(order_id)
    if not order:
        await callback.answer("Topilmadi", show_alert=True)
        return

    if callback.from_user.id != order["user_id"]:
        await callback.answer("Bu tugma sizga tegishli emas", show_alert=True)
        return

    # Agar allaqachon yakunlangan bo'lsa (masalan kuryer "Yetkazildi" deb
    # belgilagan bo'lsa) - qayta yozib yubormaymiz, shunchaki tasdiqlaymiz.
    if order["status"] in ("delivered", "received"):
        await callback.answer("Bu buyurtma allaqachon yakunlangan ✅")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    db.update_order(order_id, status="received", received_at=datetime.now().isoformat())
    await callback.answer("✅ Rahmat!")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("🎉 Xaridingiz uchun rahmat! Yana kitob kerak bo'lsa, biz doim shu yerdamiz 😊")

    # Guruhdagi (Print guruh) shu buyurtmaning YAGONA status xabarini ham
    # "OLDIM" holatiga yangilaymiz - mijoz o'zi qabul qilganini xodimlar
    # ham guruhda ko'rib turishi uchun.
    try:
        from utils import update_order_status_header
        await update_order_status_header(bot, order_id, "📗", "OLDIM (mijoz qabul qildi)")
    except Exception:
        pass

    try:
        await bot.send_message(config.ADMIN_ID, f"📗 {order['order_code']} — mijoz o'zi \"Oldim\" deb belgiladi.")
    except Exception:
        pass


async def show_payment_qr(message: Message, state: FSMContext, order_id: int):
    """Barcha kitoblar tanlangach - DARHOL to'lov so'raladi (yetkazib berishdan OLDIN).
    Yetkazib berish to'lovdan KEYIN, admin chekni tasdiqlagach so'raladi. Agar
    "oddiy pochta" tanlansa, oxirida YANA bitta (pochta narxi uchun) to'lov so'raladi."""
    order = db.get_order(order_id)

    await message.answer(
        f"💰 Kitoblar uchun jami: {format_money(order['books_total'])}",
        reply_markup=kb.kb_cancel_order_only(order_id)
    )

    caption = f"💳 To'lov qilib, chek (PDF yoki JPG rasm) yuboring.\n\n📌 So'rov: #{order_id}"
    # MUHIM: reply_markup=kb.remove_kb() - oldingi bosqichlarda qolib ketgan
    # "🔙 Orqaga" tugmasini shu yerda OLIB TASHLAYMIZ. To'lov so'ralgach,
    # mijoz endi orqaga qaytolmasligi kerak - faqat chek yuborishi yoki
    # (yuqoridagi inline tugma orqali) butunlay bekor qilishi mumkin.
    if _qr_exists():
        await message.answer_photo(photo=FSInputFile(config.QR_CODE_IMAGE), caption=caption, reply_markup=kb.remove_kb())
    else:
        await message.answer("⚠️ To'lov QR kodi hali sozlanmagan (admin qo'shishi kerak).\n\n" + caption, reply_markup=kb.remove_kb())

    await state.update_data(order_id=order_id)
    await state.set_state(UserFlow.waiting_receipt)


async def finalize_order_after_delivery(state: FSMContext, bot: Bot, order_id: int):
    """Buyurtma TO'LIQ to'langach (kitoblar, va agar oddiy pochta bo'lsa - pochta
    narxi ham) chaqiriladi: yakuniy xulosani foydalanuvchiga yuboradi va PRINT
    guruhiga jo'natadi. `state` - albatta FOYDALANUVCHINING FSM konteksti bo'lishi
    kerak (admin tomonidan chaqirilganda StorageKey orqali quriladi)."""
    order = db.get_order(order_id)
    books = db.get_books_for_order(order_id)

    books_total = order["books_total"] or 0
    pochta = order["pochta_narxi"] or 0
    grand_total = books_total + pochta
    db.update_order(order_id, grand_total=grand_total, status="completed", completed_at=datetime.now().isoformat())
    order = db.get_order(order_id)

    lines = [f"✅ Buyurtmangiz to'liq rasmiylashtirildi — {order['order_code']}\n"]
    for b in books:
        if b["status"] != "done":
            continue
        vol = get_volume_count(b["page_count"])
        vol_text = f", {vol} jild" if vol > 1 else ""
        lines.append(
            f"📚 Kitob №{b['seq_num']}: {b['page_count']} bet{vol_text}, {config.FORMAT_NAMES[b['format_key']]}, "
            f"{config.BINDING_NAMES[b['binding']]}, {b['copies']} dona — {format_money(b['price'])}"
        )
    lines.append("")
    delivery_label = config.DELIVERY_TYPE_NAMES.get(order['delivery_type'], order['delivery_type'])
    delivery_info = order['delivery_detail'] or order['university'] or ''
    lines.append(f"🚚 Yetkazish: {delivery_label} {delivery_info}".rstrip())
    lines.append(f"📞 Oluvchi: {order['receiver_phone']}")
    lines.append("")
    lines.append(f"💰 Kitoblar uchun to'landi: {format_money(books_total)}")
    if pochta:
        lines.append(f"📮 Pochta narxi to'landi: {format_money(pochta)}")

    # DIQQAT: mijozga yuboriladigan barcha xabarlar try/except bilan himoyalangan.
    # Agar mijoz botni bloklagan bo'lsa (yoki boshqa xato bo'lsa), bu FUNKSIYANI
    # TO'XTATMASLIGI kerak - buyurtma baribir PRINT guruhiga yetib borishi shart,
    # aks holda kitob hech qachon chop etilmay qolib ketardi.
    try:
        await bot.send_message(order["user_id"], "\n".join(lines), reply_markup=kb.kb_main_menu())
    except Exception:
        pass

    # Kitob fayllari va cheklarni foydalanuvchining o'ziga ham yuboramiz -
    # shunda uning qo'lida ham to'liq nusxa saqlanadi (yo'qolib qolish xavfisiz).
    for b in books:
        if b["status"] != "done":
            continue
        try:
            await bot.send_document(
                order["user_id"], b["file_id"],
                caption=f"📚 {order['order_code']}-{b['seq_num']} — {b['file_name']}"
            )
        except Exception:
            pass

    if order["receipt_file_id"]:
        try:
            if order["receipt_type"] == "photo":
                await bot.send_photo(order["user_id"], order["receipt_file_id"], caption=f"💳 {order['order_code']} — kitoblar uchun to'lov chekingiz")
            else:
                await bot.send_document(order["user_id"], order["receipt_file_id"], caption=f"💳 {order['order_code']} — kitoblar uchun to'lov chekingiz")
        except Exception:
            pass

    if order["pochta_receipt_file_id"]:
        try:
            if order["pochta_receipt_type"] == "photo":
                await bot.send_photo(order["user_id"], order["pochta_receipt_file_id"], caption=f"💳 {order['order_code']} — pochta to'lovi chekingiz")
            else:
                await bot.send_document(order["user_id"], order["pochta_receipt_file_id"], caption=f"💳 {order['order_code']} — pochta to'lovi chekingiz")
        except Exception:
            pass

    # Tayyor bo'lish vaqti va murojaat - alohida, chek(lar)dan KEYINGI oxirgi xabar
    try:
        await bot.send_message(
            order["user_id"],
            f"⏱ Buyurtma 24-48 soat ichida tayyor bo'ladi.\n"
            f"❓ Buyurtmangizda xatolik bo'lsa, adminga murojaat qiling: @{config.SUPPORT_USERNAME}"
        )
    except Exception:
        pass

    await state.clear()

    # MUHIM: bu qator har doim ishga tushishi kerak - mijozga xabar borgan-bormaganidan
    # qat'i nazar, buyurtma chop etish uchun PRINT guruhiga yetib borishi shart.
    from utils import send_to_print_group
    await send_to_print_group(bot, order_id)



@router.callback_query(F.data.startswith("orderconfirm:"))
async def order_cancel(callback: CallbackQuery, state: FSMContext):
    _, decision, order_id = callback.data.split(":")
    order_id = int(order_id)
    await callback.answer()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if decision == "no":
        db.update_order(order_id, status="cancelled")
        await state.clear()
        await callback.message.answer("❌ Buyurtma bekor qilindi.", reply_markup=kb.remove_kb())
        await callback.message.answer(config.TXT_MAIN_MENU, reply_markup=kb.kb_main_menu())
        await state.set_state(UserFlow.main_menu)


# ================= ORQAGA QAYTISH =================

@router.message(UserFlow.waiting_delivery_address, F.text == "🔙 Orqaga")
async def back_from_address(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        return
    await message.answer("Yetkazib berish turini qayta tanlang 👇", reply_markup=kb.kb_cancel_persistent())
    await message.answer("Qanday qabul qilib olasiz?", reply_markup=kb.kb_delivery(order_id))
    await state.set_state(UserFlow.sending_books)


@router.message(UserFlow.waiting_receiver_phone, F.text == "🔙 Orqaga")
async def back_from_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        return
    # "Boshqa kishi" deb raqam kiritishga o'tgan bo'lsa, orqaga bosilganda
    # yetkazib berish tanloviga emas, balki "Kim olib ketadi?" ekraniga qaytamiz.
    await message.answer("⬆️ Qaytadan tanlang 👇", reply_markup=kb.kb_cancel_persistent())
    await ask_receiver_phone(message, state, order_id)
    await state.set_state(UserFlow.sending_books)


@router.message(UserFlow.waiting_receipt, F.text == "🔙 Orqaga")
async def back_from_receipt(message: Message, state: FSMContext):
    # MUHIM: to'lov so'ralgandan keyin ORQAGA QAYTISH ENDI TAQIQLANGAN -
    # mijoz kitob tarkibini o'zgartirib, chalkashlik keltirib chiqarmasligi
    # uchun. Endi faqat: chek yuborish YOKI yuqoridagi "❌ Bekor qilish"
    # (inline) tugmasi orqali butunlay bekor qilish mumkin.
    await message.answer(
        "⚠️ To'lov so'ralgandan keyin orqaga qaytib bo'lmaydi.\n\n"
        "Iltimos, chekni yuboring yoki yuqoridagi \"❌ Bekor qilish\" tugmasi orqali "
        "buyurtmani butunlay bekor qiling."
    )

'''
@router.message(UserFlow.waiting_receiver_phone)
async def got_custom_receiver_phone(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]
    await finalize_receiver_phone(message, state, bot, order_id, message.text)
'''

import re

@router.message(UserFlow.waiting_receiver_phone)
async def got_custom_receiver_phone(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer(
            "❗ Iltimos, telefon raqamini FAQAT matn ko'rinishida yuboring:\n\n"
            "+998xxxxxxxxx"
        )
        return

    phone = message.text.strip()

    if not re.fullmatch(r"\+998\d{9}", phone):
        await message.answer(
            "❌ Telefon raqamini faqat quyidagi formatda kiriting:\n\n"
            "+998xxxxxxxxx"
        )
        return

    await state.update_data(receiver_phone=phone)

    await message.answer(
        "👤 Qabul qiluvchining ismini kiriting:"
    )

    await state.set_state(UserFlow.waiting_receiver_name)

@router.message(UserFlow.waiting_receiver_name)
async def got_receiver_name(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("❗ Iltimos, ismni FAQAT matn ko'rinishida yuboring.")
        return

    data = await state.get_data()

    order_id = data["order_id"]
    phone = data["receiver_phone"]

    await finalize_receiver_phone(
        message,
        state,
        bot,
        order_id,
        f"{message.text} ({phone})"
    )

def _qr_exists():
    import os
    return os.path.exists(config.QR_CODE_IMAGE)


# ================= CHEK QABUL QILISH =================

async def schedule_admin_reminder(bot: Bot, order_id: int, order_code: str):
    """
    Agar admin ADMIN_REMINDER_MINUTES vaqt ichida chekni tekshirmasa (qabul yoki
    rad qilmasa), adminga eslatma yuboradi. Bu AVTOMATIK QABUL QILISH emas -
    faqat eslatma, chunki pulni tekshirishni baribir inson (admin) qilishi kerak.
    """
    await asyncio.sleep(config.ADMIN_REMINDER_MINUTES * 60)
    order = db.get_order(order_id)
    if order and order["status"] in ("awaiting_admin_review", "awaiting_admin_review_pochta"):
        await bot.send_message(
            config.ADMIN_ID,
            f"⏰ ESLATMA: {order_code} buyurtmasi hali tekshirilmagan!\n"
            f"Iltimos, chekni ko'rib chiqing va qabul qiling yoki rad eting."
        )


@router.message(UserFlow.waiting_receipt, F.photo | F.document)
async def got_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data["order_id"]

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    receipt_type = "photo" if message.photo else "document"
    db.update_order(order_id, receipt_file_id=file_id, receipt_type=receipt_type, status="awaiting_admin_review")
    # DIQQAT: order_code BU YERDA berilmaydi - u faqat admin buyurtmani
    # QABUL QILGANDA beriladi (admin_accept_order). Shunda WP-raqamlar
    # ketma-ketligi faqat HAQIQIY (tasdiqlangan) buyurtmalarni hisoblaydi,
    # bekor qilingan/tashlab ketilganlar "joy egallamaydi".
    pending_label = f"So'rov #{order_id}"

    order = db.get_order(order_id)

    await message.answer("✅ Chekingiz qabul qilindi, admin tekshirmoqda. Tez orada javob beramiz!",
                          reply_markup=kb.remove_kb())

    # MUHIM: chek ENDI to'g'ridan-to'g'ri yuborilmaydi - u ham kitoblar bilan
    # BIRGA, admin uchun umumiy navbatga qo'shiladi. Shunda kitob va chek
    # tekshirish hech qachon bir-birining ustiga chiqib ketmaydi - admin
    # doim faqat BITTA ish bilan shug'ullanadi.
    db.create_admin_task("receipt", order_id)
    from handlers_admin import try_dispatch_next_admin_task
    await try_dispatch_next_admin_task(bot, state.storage)

    # Admin ADMIN_REMINDER_MINUTES ichida javob bermasa, eslatma yuboriladi.
    # Bu botni bloklamaydi - fon vazifasi sifatida ishga tushadi.
    asyncio.create_task(schedule_admin_reminder(bot, order_id, pending_label))

    # MUHIM: BU YERDA state.clear() QILINMAYDI! Aks holda mijoz holati
    # "band emas" (None) ga qaytib, asosiy menyu tugmalarini erkin bosa
    # oladigan bo'lib qolar edi - to'lov hali admin tomonidan ko'rib
    # chiqilmagan bo'lsa ham. order_id ma'lumoti state.data ichida saqlanib
    # qoladi (o'chirilmaydi), faqat holat "band" deb belgilanadi.
    await state.set_state(UserFlow.awaiting_payment_review)


@router.message(UserFlow.awaiting_payment_review)
async def already_awaiting_review(message: Message):
    """Mijoz chekni allaqachon yuborgan, admin javobini kutayotgan paytda
    yana biror narsa (matn, fayl va h.k.) yuborsa - tinch xabar bilan
    ma'lumot beramiz, hech narsani qayta ishlamaymiz."""
    await message.answer(
        "⏳ Chekingiz allaqachon yuborilgan, admin javobini kutmoqdamiz. Iltimos, biroz kuting."
    )
