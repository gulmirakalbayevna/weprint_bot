"""
Buyurtmalar TAYYOR deb belgilanganda, print guruhiga yuboriladigan nakleyka
PDF sini yaratadi. Bitta A4 varaqqa 3x4=12 ta UZUNASIGA (tor, baland) yorliq
joylashtiriladi - yashil/bежli rang sxemasi bilan.

MUHIM: nakleyka HAR BIR KITOB uchun ALOHIDA yasaladi (bitta buyurtmada bir
nechta kitob bo'lsa, ularning formati/pereplyoti/yetkazish turi har xil
bo'lishi mumkin - shuning uchun har biriga o'ziga mos nakleyka kerak).

Har bir nakleykada:
    WEPRINT (rangli sarlavha panel)
    buyurtma raqami
    telefon raqami
    format (o'lcham • rang)
    pereplyot turi
    yetkazish turi (olib ketish / Yandex / BTS / Pochta / Universitet)
    iliq tilak
    xatolik bo'lsa murojaat uchun kontakt

Matnlar orasidagi bo'shliq KARTA BALANDLIGIGA QARAB AVTOMATIK hisoblanadi -
shu sababli o'rtada ortiqcha bo'sh joy qolib ketmaydi va zichlik ham bir xil
saqlanadi (cols/rows o'zgarsa ham moslashadi).

MUHIM: sahifaning HAR TOMONIDAN 1 sm (10mm) chetga qoldiriladi - aks holda
qirquvchi apparat eng chekkadagi nakleykalarni to'liq/to'g'ri kesib bera
olmaydi. Har bir nakleyka atrofida (kulrang, nuqta-nuqta) qirqish chizig'i
bor - bu APPARAT UCHUN yo'l-yo'riq, shuning uchun rang emas, neytral kulrang
qoldirilgan.
"""
import config


# ============ RANG SXEMASI (to'q yashil + beж) ============
COLOR_PRIMARY = (0.153, 0.278, 0.184)     # to'q yashil - sarlavha panel, buyurtma raqami
COLOR_ACCENT = (0.541, 0.427, 0.169)      # to'q oltin/olива - format belgisi (yashil-beж bilan mos)
COLOR_BG_TINT = (0.949, 0.933, 0.878)     # iliq beж fon (karta ichi)
COLOR_TEXT_GRAY = (0.376, 0.345, 0.278)   # iliq jigarrang-kulrang matn (beжga mos)
COLOR_CUT_LINE = (0.6, 0.6, 0.6)          # qirqish chizig'i - neytral kulrang

DELIVERY_LABELS = {
    "pickup": "OFISDAN OLIB KETISH",
    "yandex": "YANDEX / UKLON",
    "viloyat_bts": "VILOYAT (BTS)",
    "viloyat_pochta": "VILOYAT (POCHTA)",
    "universitet": "UNIVERSITET",
}


def _format_label(format_key: str) -> str:
    """'a5_bw' -> 'A5 • OQ-QORA', 'a4_color' -> 'A4 • RANGLI'."""
    if not format_key:
        return ""
    size = format_key.split("_")[0].upper()  # a4 / a5
    color = "RANGLI" if format_key.endswith("color") else "OQ-QORA"
    return f"{size} • {color}"


def _delivery_label(item: dict) -> str:
    """Yetkazish turi matni - universitet bo'lsa, nomi ham qo'shiladi."""
    delivery_type = item.get("delivery_type")
    base = DELIVERY_LABELS.get(delivery_type, "")
    if delivery_type == "universitet" and item.get("university"):
        return f"{base}: {item['university']}"
    return base


def generate_labels_pdf(items: list, output_path: str, cols: int = 3, rows: int = 4):
    """
    items: har biri BITTA KITOB uchun lug'at (dict):
        {
            "order_code": "WP-00012",
            "receiver_phone": "+998901234567",
            "format_key": "a5_bw",       # config.FORMAT_NAMES kalitlaridan biri
            "binding": "prujina",        # config.BINDING_NAMES kalitlaridan biri
            "delivery_type": "yandex",   # config.DELIVERY_TYPE_NAMES kalitlaridan biri
            "university": "UWED",        # ixtiyoriy - faqat delivery_type='universitet' bo'lsa
        }
    output_path: PDF qayerga saqlanishi.
    cols, rows: bitta A4 varaqqa nechta ustun/qator yorliq. Standart 3x4=12 ta.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.colors import Color

    page_width, page_height = A4

    # MUHIM: qirquvchi apparat uchun HAR TOMONDAN kamida 1 sm (10mm) chetga
    # qoldiriladi - bu chegaradan tashqarida hech narsa chizilmaydi.
    margin = 10 * mm
    usable_w = page_width - 2 * margin
    usable_h = page_height - 2 * margin
    cell_w = usable_w / cols
    cell_h = usable_h / rows
    per_page = cols * rows

    c = canvas.Canvas(output_path, pagesize=A4)

    contact_text = f"Xatolik bo'lsa: @{config.BOT_USERNAME}"

    col_primary = Color(*COLOR_PRIMARY)
    col_accent = Color(*COLOR_ACCENT)
    col_bg = Color(*COLOR_BG_TINT)
    col_gray = Color(*COLOR_TEXT_GRAY)
    col_cut = Color(*COLOR_CUT_LINE)
    col_white = Color(1, 1, 1)

    for idx, item in enumerate(items):
        pos_in_page = idx % per_page
        if idx > 0 and pos_in_page == 0:
            c.showPage()

        col = pos_in_page % cols
        row = pos_in_page // cols

        x = margin + col * cell_w
        y = page_height - margin - (row + 1) * cell_h

        # 1) Qirqish uchun TASHQI chegara (kulrang, nuqta-nuqta) - apparat uchun yo'l-yo'riq
        c.setDash(2, 2)
        c.setStrokeColor(col_cut)
        c.setLineWidth(0.6)
        c.rect(x, y, cell_w, cell_h)
        c.setDash()

        # 2) ICHKI rangli karta (beж fon, yumaloq burchak, yashil ramka)
        inset = 3 * mm
        card_x = x + inset
        card_y = y + inset
        card_w = cell_w - 2 * inset
        card_h = cell_h - 2 * inset
        radius = 3 * mm

        c.setFillColor(col_bg)
        c.setStrokeColor(col_primary)
        c.setLineWidth(1)
        c.roundRect(card_x, card_y, card_w, card_h, radius, stroke=1, fill=1)

        # 3) Sarlavha paneli (to'q yashil, yumaloq yuqori burchak) - "WEPRINT"
        band_h = 7 * mm
        c.setFillColor(col_primary)
        c.roundRect(card_x, card_y + card_h - band_h, card_w, band_h, radius, stroke=0, fill=1)
        c.rect(card_x, card_y + card_h - band_h, card_w, band_h - radius, stroke=0, fill=1)

        center_x = card_x + card_w / 2
        c.setFillColor(col_white)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(center_x, card_y + card_h - band_h / 2 - 3.5, "WEPRINT")

        # 4) Kontent qatorlari - KARTA BALANDLIGIGA QARAB bo'shliqni AVTOMATIK
        # hisoblaymiz, shunda o'rtada ortiqcha bo'sh joy qolmaydi.
        binding_key = item.get("binding")
        binding_text = config.BINDING_NAMES.get(binding_key, binding_key or "").upper()

        lines = [
            (item.get("order_code") or "", "Helvetica-Bold", 15.5, col_primary),
            (item.get("receiver_phone") or "", "Helvetica", 10, col_gray),
            (_format_label(item.get("format_key")), "Helvetica-Bold", 10.5, col_accent),
            (binding_text, "Helvetica", 9.5, col_gray),
            (_delivery_label(item), "Helvetica-Bold", 9.5, col_primary),
            ("Yoqimli mutolaa tilaymiz!", "Helvetica-Oblique", 9, col_gray),
        ]

        top_pad = 6.5 * mm  # katta qalin buyurtma raqami panelga tegib qolmasligi uchun
        bottom_reserved = 8 * mm  # kontakt matni uchun joy
        top_y = card_y + card_h - band_h - top_pad
        bottom_y = card_y + bottom_reserved
        available_h = top_y - bottom_y
        gap = available_h / len(lines)

        cur_y = top_y
        for text, font, size, color in lines:
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawCentredString(center_x, cur_y, text)
            cur_y -= gap

        # 5) Xatolik uchun kontakt - kartaning eng pastida, kichik
        c.setFillColor(col_gray)
        c.setFont("Helvetica", 7)
        c.drawCentredString(center_x, card_y + 4 * mm, contact_text)

    c.save()
