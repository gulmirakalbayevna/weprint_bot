import math
from config import PRICE_PER_PAGE_BW, PRICE_PER_PAGE_COLOR, FLAT_PRICE_LIMIT, FLAT_PRICES, COVER_PRICE_TIERS
from config import FORMAT_NAMES, BINDING_NAMES
import database as db


def _round_up_500(value: int) -> int:
    return value if value % 500 == 0 else math.ceil(value / 500) * 500


def _get_cover_price(per_volume_pages: int) -> int:
    for lo, hi, price in COVER_PRICE_TIERS:
        if lo <= per_volume_pages <= hi:
            return price
    return 0


def calc_single_copy_prices(page_count: int) -> dict:
    """
    weprint.uz saytidagi haqiqiy narx formulasi (App.js dan olingan, tasdiqlangan).
    1 nusxa uchun barcha 4 format narxini qaytaradi.
    """
    if page_count <= FLAT_PRICE_LIMIT:
        return dict(FLAT_PRICES)

    pages = page_count
    if 440 < pages < 781:
        volumes = 2
    elif pages > 780:
        volumes = math.ceil((pages - 780) / 390) + 2
    else:
        volumes = 1

    per_volume_pages = math.ceil(pages / volumes)
    cover_price = _get_cover_price(per_volume_pages)

    price_a5_bw = _round_up_500(
        (math.ceil(per_volume_pages / 4) * PRICE_PER_PAGE_BW + cover_price + 1500) * volumes
    )
    price_a5_color = _round_up_500(
        (math.ceil(per_volume_pages / 4) * PRICE_PER_PAGE_COLOR + cover_price + 2000) * volumes
    )
    price_a4_bw = _round_up_500(
        (math.ceil(per_volume_pages / 2) * PRICE_PER_PAGE_BW + cover_price + 1500) * volumes
    )
    price_a4_color = _round_up_500(
        (math.ceil(per_volume_pages / 2) * PRICE_PER_PAGE_COLOR + cover_price + 1500) * volumes
    )

    return {
        "a4_bw": price_a4_bw,
        "a4_color": price_a4_color,
        "a5_bw": price_a5_bw,
        "a5_color": price_a5_color,
    }


def get_volume_count(page_count: int) -> int:
    """Necha jildga (avtomatik) bo'linishini qaytaradi - faqat ma'lumot uchun."""
    if page_count <= 440:
        return 1
    elif page_count < 781:
        return 2
    else:
        return math.ceil((page_count - 780) / 390) + 2


def calc_book_price(page_count: int, format_key: str, copies: int) -> int:
    single_copy_prices = calc_single_copy_prices(page_count)
    return single_copy_prices[format_key] * copies


async def send_media_message(message, text: str = None, media: list = None, reply_markup=None):
    """
    UNIVERSAL FUNKSIYA — istalgan bosqichga matn + rasm/video/lokatsiya qo'shish uchun.

    text: oddiy matn (ixtiyoriy, None bo'lishi mumkin)
    media: ro'yxat (list), har bir element - lug'at (dict), quyidagi turlardan biri:
        {"type": "photo", "id": "fayl_nomi.jpg"}      -> bot papkasidagi rasm
        {"type": "photo", "id": "AgACAgI...."}         -> file_id (oldin /fileid orqali olingan)
        {"type": "video", "id": "fayl_nomi.mp4"}       -> bot papkasidagi video
        {"type": "video", "id": "BAACAgI...."}         -> file_id
        {"type": "location", "lat": 41.123, "lon": 69.456}  -> xarita joylashuvi
    reply_markup: tugmalar - eng OXIRGI muvaffaqiyatli yuborilgan xabarga biriktiriladi

    MUHIM: har bir element alohida try/except bilan yuboriladi. Agar bitta rasm/video
    (masalan noto'g'ri yoki eskirgan file_id sababli) xato bersa ham, undan keyingi
    elementlar (masalan location) baribir yuborilishda davom etadi.

    MISOL:
        await send_media_message(
            message,
            text="Manzilimiz:",
            media=[
                {"type": "photo", "id": "manzil1.jpg"},
                {"type": "photo", "id": "manzil2.jpg"},
                {"type": "location", "lat": 41.311, "lon": 69.279},
            ],
            reply_markup=some_keyboard
        )
    """
    import os
    import logging
    from aiogram.types import FSInputFile

    media = media or []
    steps = []
    if text:
        steps.append(("text", text))
    steps.extend([(m["type"], m) for m in media])

    if not steps:
        return

    markup_delivered = (reply_markup is None)

    for i, (kind, payload) in enumerate(steps):
        is_last = (i == len(steps) - 1)
        markup = reply_markup if is_last else None

        try:
            if kind == "text":
                await message.answer(payload, reply_markup=markup)
            elif kind == "photo":
                src = payload["id"]
                photo = FSInputFile(src) if os.path.exists(src) else src
                await message.answer_photo(photo=photo, reply_markup=markup)
            elif kind == "video":
                src = payload["id"]
                video = FSInputFile(src) if os.path.exists(src) else src
                await message.answer_video(video=video, reply_markup=markup)
            elif kind == "location":
                await message.answer_location(latitude=payload["lat"], longitude=payload["lon"])
            if markup is not None:
                markup_delivered = True
        except Exception as e:
            logging.exception("send_media_message: '%s' elementini yuborishda xato: %s", kind, e)
            # Bitta element ishlamasa ham, davom etamiz - keyingi elementlar
            # (masalan location) baribir yuborilishga harakat qilinadi.
            continue

    # Agar tugmalar hech qaysi elementga biriktirilmagan bo'lsa (masalan oxirgi
    # element xato bergani uchun) - ularni alohida, oxirida yuboramiz.
    if not markup_delivered:
        try:
            await message.answer("👆", reply_markup=reply_markup)
        except Exception:
            logging.exception("send_media_message: reply_markup'ni oxirida yuborishda xato")


async def send_text_or_photo(message, text: str, image=None, reply_markup=None):
    """Eski, sodda versiya (1 ta rasm uchun) - hali ham ishlaydi, orqaga moslik uchun saqlangan."""
    await send_media_message(message, text=text, media=[{"type": "photo", "id": image}] if image else None,
                              reply_markup=reply_markup)


def book_summary_text(book, order_code_seq: str) -> str:
    return (
        f"📚 Kitob №{book['seq_num']} ({order_code_seq})\n"
        f"{book['page_count']} bet\n"
        f"{FORMAT_NAMES[book['format_key']]}\n"
        f"{book['copies']} ta nusxa\n\n"
        f"💰 Narxi: {book['price']:,} so'm".replace(",", " ")
    )


def order_books_total(order_id: int) -> int:
    books = db.get_books_for_order(order_id)
    return sum(b["price"] or 0 for b in books if b["status"] == "done")


def order_summary_text(order_id: int) -> str:
    books = db.get_books_for_order(order_id)
    lines = []
    total = 0
    for b in books:
        if b["status"] != "done":
            continue
        vol = get_volume_count(b["page_count"])
        vol_text = f", {vol} jild" if vol > 1 else ""
        lines.append(f"📚 Kitob №{b['seq_num']} ({b['page_count']} bet{vol_text}): {b['price']:,} so'm".replace(",", " "))
        total += b["price"] or 0
    lines.append("────────────────")
    lines.append(f"💰 Jami: {total:,} so'm".replace(",", " "))
    return "\n".join(lines), total


def format_money(v: int) -> str:
    return f"{v:,} so'm".replace(",", " ")


async def send_to_print_group(bot, order_id: int):
    """Buyurtma to'liq tayyor bo'lgach (to'lov + yetkazish tanlangach) ikkita
    guruhga yuboriladi:
    1) PRINT_GROUP_ID - kitob fayli + info (Print tugmasi bilan, print xodimi
       shu yerda "Print qilindi" bosib, ismini yozadi).
    2) PRINTED_GROUP_ID ("Zakaz qabul guruhi") - xuddi shu fayllar, LEKIN
       HECH QANDAY TUGMASIZ - bu shunchaki zaxira/arxiv: bot vaqtincha
       ishlamay qolsa ham, qabul qilingan buyurtmalar shu yerda ko'rinib
       turadi va ish to'xtab qolmaydi.
    """
    import config
    import keyboards as kb
    order = db.get_order(order_id)
    books = db.get_books_for_order(order_id)

    await bot.send_message(config.PRINT_GROUP_ID, f"🖨 YANGI BUYURTMA — {order['order_code']}")
    if config.PRINTED_GROUP_ID:
        try:
            await bot.send_message(config.PRINTED_GROUP_ID, f"📥 QABUL QILINDI — {order['order_code']}")
        except Exception:
            pass

    for b in books:
        if b["status"] != "done":
            continue
        await bot.send_document(
            config.PRINT_GROUP_ID, b["file_id"],
            caption=f"{order['order_code']}-{b['seq_num']} — {b['file_name']}"
        )
        vol = get_volume_count(b["page_count"])
        vol_text = f" ({vol} jild)" if vol > 1 else ""
        info_text = (
            f"📚 {order['order_code']}-{b['seq_num']}\n"
            f"{b['page_count']} bet{vol_text} | {FORMAT_NAMES[b['format_key']]} | "
            f"{BINDING_NAMES[b['binding']]} | {b['copies']} dona"
        )
        # Print xodimi uchun - shu aniq faylni chop etib bo'lgach bosadigan tugma.
        # Bu FAQAT print guruh ichidagi belgi - foydalanuvchi statusiga ta'sir
        # qilmaydi (u hamon "Ishlanmoqda" ko'radi, /tayyor buyrug'i bosilguncha).
        info_msg = await bot.send_message(
            config.PRINT_GROUP_ID, info_text,
            reply_markup=kb.kb_book_print_toggle(b["id"], printed=bool(b["printed"]))
        )
        # Bu xabarning ID sini saqlab qo'yamiz - print xodimi ismini yozgach,
        # aynan shu xabarni TAHRIRLAB, ismini ichiga qo'shish uchun kerak bo'ladi.
        db.update_book(b["id"], print_info_chat_id=config.PRINT_GROUP_ID, print_info_message_id=info_msg.message_id)

        # PRINTED_GROUP_ID ("Zakaz qabul guruhi") - AYNAN SHU FAYL, lekin
        # HECH QANDAY tugmasiz - sof zaxira nusxa sifatida.
        if config.PRINTED_GROUP_ID:
            try:
                await bot.send_document(
                    config.PRINTED_GROUP_ID, b["file_id"],
                    caption=f"{order['order_code']}-{b['seq_num']} — {b['file_name']}"
                )
                await bot.send_message(config.PRINTED_GROUP_ID, info_text)
            except Exception:
                pass

    delivery_info = order['delivery_detail'] or order['university'] or ''
    delivery_label = config.DELIVERY_TYPE_NAMES.get(order['delivery_type'], order['delivery_type'])
    summary_lines = [
        f"🚚 Yetkazish: {delivery_label} {delivery_info}",
        f"📞 Oluvchi: {order['receiver_phone']}",
        f"💰 Kitoblar uchun to'landi: {format_money(order['books_total'] or 0)}",
    ]
    if order["pochta_narxi"]:
        summary_lines.append(f"📮 Pochta narxi (mijozdan ALOHIDA olinadi): {format_money(order['pochta_narxi'])}")
    await bot.send_message(config.PRINT_GROUP_ID, "\n".join(summary_lines))
    if config.PRINTED_GROUP_ID:
        try:
            await bot.send_message(config.PRINTED_GROUP_ID, "\n".join(summary_lines))
        except Exception:
            pass

    if order["receipt_file_id"]:
        if order["receipt_type"] == "photo":
            await bot.send_photo(config.PRINT_GROUP_ID, order["receipt_file_id"], caption=f"💳 {order['order_code']} — to'lov cheki")
        else:
            await bot.send_document(config.PRINT_GROUP_ID, order["receipt_file_id"], caption=f"💳 {order['order_code']} — to'lov cheki")


async def send_to_ready_group(bot, order_id: int):
    """Buyurtma TAYYOR deb belgilangach (admin /tayyor orqali), kitob fayllari
    'Tayyor kitoblar' guruhiga yuboriladi."""
    import config
    if not config.READY_GROUP_ID:
        return

    order = db.get_order(order_id)
    books = db.get_books_for_order(order_id)

    await bot.send_message(config.READY_GROUP_ID, f"📗 TAYYOR — {order['order_code']}")
    for b in books:
        if b["status"] != "done":
            continue
        await bot.send_document(
            config.READY_GROUP_ID, b["file_id"],
            caption=f"{order['order_code']}-{b['seq_num']} — {b['file_name']}"
        )

    delivery_label = config.DELIVERY_TYPE_NAMES.get(order['delivery_type'], order['delivery_type'])
    delivery_info = order['delivery_detail'] or order['university'] or ''
    await bot.send_message(
        config.READY_GROUP_ID,
        f"🚚 Yetkazish: {delivery_label} {delivery_info}\n📞 {order['receiver_phone']}"
    )


async def send_to_courier_group(bot, order_id: int):
    """Universitetga yetkaziladigan TAYYOR buyurtmalar kuryer guruhiga ham
    yuboriladi - 'Yetkazildi' tugmasi bilan."""
    import config
    import keyboards as kb
    from datetime import date

    if not config.COURIER_GROUP_ID:
        return

    order = db.get_order(order_id)

    await bot.send_message(
        config.COURIER_GROUP_ID,
        f"🚕 Universitetga olib borish\n\n"
        f"{order['order_code']}\n"
        f"{order['university']}\n"
        f"📞 {order['receiver_phone']}\n"
        f"📅 {date.today().strftime('%d.%m')}",
        reply_markup=kb.kb_courier_delivered(order_id)
    )


def build_statistika_workbook(stats: dict, period_label: str, date_from_label: str, date_to_label: str, output_path: str):
    """
    /statistika uchun batafsil Excel hisobot yaratadi (bitta varaq, bo'limlarga
    bo'lingan). Bu HISOBOT/SNAPSHOT - foydalanuvchi to'ldiradigan model emas,
    shuning uchun qiymatlar to'g'ridan-to'g'ri (formula sifatida emas) yoziladi.
    """
    import config
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Statistika"

    FONT = "Arial"
    title_font = Font(name=FONT, size=14, bold=True)
    section_font = Font(name=FONT, size=12, bold=True, color="FFFFFF")
    section_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    normal_font = Font(name=FONT, size=11)
    money_font = Font(name=FONT, size=11, bold=True)

    row = 1

    def write_title(text):
        nonlocal row
        ws.cell(row=row, column=1, value=text).font = title_font
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        row += 2

    def write_section(text):
        nonlocal row
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = section_font
        cell.fill = section_fill
        cell2 = ws.cell(row=row, column=2, value="")
        cell2.fill = section_fill
        row += 1

    def write_row(label, value, is_money=False):
        nonlocal row
        ws.cell(row=row, column=1, value=label).font = normal_font
        val_cell = ws.cell(row=row, column=2, value=value)
        val_cell.font = money_font if is_money else normal_font
        if is_money:
            val_cell.number_format = '#,##0 "so\'m"'
        row += 1

    def write_empty_row():
        nonlocal row
        row += 1

    write_title(f"📊 Statistika — {period_label}")
    write_row("Davr", f"{date_from_label} — {date_to_label}")
    write_empty_row()

    write_section("UMUMIY KO'RSATKICHLAR")
    write_row("Jami buyurtmalar", stats["order_count"])
    write_row("Jami kitoblar", stats["book_count"])
    write_empty_row()

    write_section("FORMAT BO'YICHA (kitoblar soni)")
    for key in ("a4_color", "a4_bw", "a5_color", "a5_bw"):
        write_row(FORMAT_NAMES.get(key, key), stats["format_counts"].get(key, 0))
    write_empty_row()

    write_section("PEREPLYOT BO'YICHA (kitoblar soni)")
    for key in ("termokley", "prujina"):
        write_row(BINDING_NAMES.get(key, key), stats["binding_counts"].get(key, 0))
    write_empty_row()

    write_section("YETKAZISH TURI BO'YICHA (buyurtmalar soni)")
    delivery_order = ["pickup", "yandex", "viloyat_bts", "viloyat_pochta", "universitet"]
    for key in delivery_order:
        if key in stats["delivery_counts"]:
            write_row(config.DELIVERY_TYPE_NAMES.get(key, key), stats["delivery_counts"][key])
    for key, count in stats["delivery_counts"].items():
        if key not in delivery_order:
            write_row(config.DELIVERY_TYPE_NAMES.get(key, key), count)
    write_empty_row()

    write_section("UNIVERSITET BO'YICHA (buyurtmalar soni)")
    if stats["university_counts"]:
        for uni, count in sorted(stats["university_counts"].items(), key=lambda x: -x[1]):
            write_row(uni, count)
    else:
        write_row("(ma'lumot yo'q)", "")
    write_empty_row()

    write_section("XODIMLAR STATISTIKASI (printed_by — print qilingan kitoblar)")
    if stats["printer_counts"]:
        for name, count in sorted(stats["printer_counts"].items(), key=lambda x: -x[1]):
            write_row(name, count)
    else:
        write_row("(ma'lumot yo'q)", "")

    ws.column_dimensions[get_column_letter(1)].width = 40
    ws.column_dimensions[get_column_letter(2)].width = 22

    wb.save(output_path)
    return output_path
