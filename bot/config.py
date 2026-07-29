import os
from dotenv import load_dotenv

load_dotenv()

# ============ ASOSIY SOZLAMALAR ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "SIZNING_BOT_TOKENINGIZ")

# Admin (buyurtmalarni qabul qiluvchi, tekshiruvchi shaxs) Telegram ID si
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Print xodimlari ishlaydigan guruh ID si (faqat TO'LANGAN buyurtmalar shu yerga tushadi)
PRINT_GROUP_ID = int(os.getenv("PRINT_GROUP_ID", "0"))

#Zakaz qabul guruhi - buyurtma TASDIQLANGANDA (to'lov+yetkazish tanlangach),
# kitob fayllari shu yerga ham AVTOMATIK, HECH QANDAY TUGMASIZ yuboriladi.
# Bu sof zaxira/arxiv: bot vaqtincha ishlamay qolsa ham, qabul qilingan
# buyurtmalar shu yerda ko'rinib turadi va ish to'xtab qolmaydi.
PRINTED_GROUP_ID = int(os.getenv("PRINTED_GROUP_ID", "0"))

# Kitoblar chop etilib TAYYOR bo'lgach jo'natiladigan guruh
READY_GROUP_ID = int(os.getenv("READY_GROUP_ID", "0"))

# Universitetga yetkaziladigan (delivery_type='universitet') tayyor buyurtmalar
# qo'shimcha ravishda shu kuryer guruhiga ham avtomatik yuboriladi
COURIER_GROUP_ID = int(os.getenv("COURIER_GROUP_ID", "0"))

# Yandex/Uklon orqali yetkaziladigan buyurtmalar TAYYOR bo'lganda, mijoz
# yuborgan taksi ma'lumotlari (buyurtma raqami, telefon, taksi havolasi) shu
# guruhga yuboriladi
YANDEX_GROUP_ID = int(os.getenv("YANDEX_GROUP_ID", "0"))

# To'lov uchun QR kod rasm manzili (fayl nomi bot papkasida bo'lishi kerak)
QR_CODE_IMAGE = os.getenv("QR_CODE_IMAGE", "qr_code.jpg")

# Narxni hisoblash sayti
PRICE_CALC_URL = os.getenv("PRICE_CALC_URL", "https://weprint.uz")

# Savol-javob / murojaat uchun aloqa username (@ belgisisiz yozing)
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "weprint_support")

# Botning o'zi (nakleykalarda "xatolik bo'lsa shu botga yozing" deb ko'rsatish uchun)
BOT_USERNAME = os.getenv("BOT_USERNAME", "weprint_orders_bot")

# Admin chekni shuncha daqiqada tekshirmasa, eslatma yuboriladi (AVTOMATIK
# QABUL QILINMAYDI - faqat eslatma, pulni tekshirish baribir admin qo'lida qoladi).
ADMIN_REMINDER_MINUTES = 20

# ============ NARXLAR (weprint.uz saytining haqiqiy formulasi asosida) ============
PRICE_PER_PAGE_BW = 260       # 1 bet, oq-qora
PRICE_PER_PAGE_COLOR = 370    # 1 bet, rangli

# 52 betgacha bo'lgan kitoblar uchun FIKS (o'zgarmas) narx:
FLAT_PRICE_LIMIT = 52
FLAT_PRICES = {
    "a4_bw": 21500,
    "a4_color": 24000,
    "a5_bw": 18500,
    "a5_color": 20000,
}

# Muqova (cover) narxi - jild ichidagi sahifa soniga qarab (52 betdan ko'p kitoblar uchun)
COVER_PRICE_TIERS = [
    (53, 129, 16500),
    (130, 200, 17500),
    (201, 300, 18500),
    (301, 400, 19500),
    (401, 440, 20500),
]

FORMAT_NAMES = {
    "a4_bw": "A4, oq-qora",
    "a4_color": "A4, rangli",
    "a5_bw": "A5, oq-qora",
    "a5_color": "A5, rangli",
}

# ============ PEREPLYOT ============
BINDING_NAMES = {
    "termokley": "Termokley",
    "prujina": "Prujinali",
}

# Yetkazib berish turi kodlarining o'qilishi oson nomlari (admin/print guruhga chiqadigan xabarlarda)
DELIVERY_TYPE_NAMES = {
    "pickup": "🏢 Ofisdan olaman",
    "yandex": "🚕 Yandex/Uklon",
    "viloyat_bts": "🚛 Viloyat (BTS)",
    "viloyat_pochta": "📮 Viloyat (Oddiy pochta)",
    "universitet": "🎓 Universitet",
}

# ============ BUYURTMA STATUSLARI (foydalanuvchiga ko'rsatiladigan nomlar) ============
ORDER_STATUS_LABELS = {
    "awaiting_admin_review": "🔵 To'lov tekshirilmoqda",
    "paid": "🟣 Yetkazishni tanlash kerak",
    "awaiting_pochta_receipt": "📩 Pochta to'lovi kutilmoqda",
    "awaiting_admin_review_pochta": "🟡 Pochta to'lovi tekshirilmoqda",
    "completed": "🟡 Ishlanmoqda",
    "ready": "🟢 Tayyor",
    "delivered": "✅ Yetkazildi",
    "received": "✅ Olindi",
    "cancelled": "⚫️ Bekor qilingan",
}

# ============ ODDIY POCHTA NARXI (kitoblar soniga qarab) ============
# (min_jild, max_jild): narx — KITOB soniga emas, JAMI JILD soniga qarab!
# (masalan 900 betlik 1 ta kitob = 3 jild, demak shu yerda "3" hisobga olinadi)
POCHTA_NARXLARI = [
    (1, 1, 22000),
    (2, 2, 24000),
    (3, 3, 26000),
    (4, 4, 28000),
    (5, 6, 30000),   
]

def get_pochta_narxi(kitoblar_soni: int) -> int:
    for lo, hi, narx in POCHTA_NARXLARI:
        if lo <= kitoblar_soni <= hi:
            return narx
    return POCHTA_NARXLARI[-1][2]

# ============ UNIVERSITETLAR ============
UNIVERSITETLAR = ["UWED", "SAMPI", "Yangi Toshmi", "Eski Toshmi", "Jahon tillari", "Yuridik", "CAU", "Stomatologiya", "KIUT", "Islom Akademiyasi"]

# Format tanlash paytida avtomatik yuboriladigan tushuntiruvchi rasm (bot papkasiga joylang)
FORMAT_INFO_IMAGE = os.getenv("FORMAT_INFO_IMAGE", "format_info.jpg")

# ============ FORMAT BOSQICHI (A4/A5, rangli/oq-qora) ============
# Bu bosqichda ko'rsatiladigan matn va media(lar) - istalgancha rasm/video qo'shishingiz mumkin.
# Bo'sh ro'yxat qoldirsangiz - hech narsa yuborilmaydi, faqat tugmalar chiqadi.
# Agar bo'sh bo'lsa va FORMAT_INFO_IMAGE/ALBOM_INFO_VIDEO sozlangan bo'lsa, o'shalar ishlatiladi
# (eski sozlamalar bilan moslik uchun).
FORMAT_STEP_TEXT_KNIJNIY = "Formatni tanlang:"
FORMAT_STEP_TEXT_ALBOM = "📘 Albom formatidagi kitoblar faqat A4 formatda chop etiladi.\n\nFormatni tanlang:"
FORMAT_STEP_MEDIA = [
    # {"type": "photo", "id": "FILE_ID"},
    # {"type": "video", "id": "FILE_ID"},
]
FORMAT_STEP_MEDIA_ALBOM = [
    # {"type": "video", "id": "FILE_ID"},
]

# ============ PEREPLYOT BOSQICHI (Termokley/Prujina) - endi ALOHIDA bosqich ============
BINDING_STEP_TEXT = "Pereplyotni tanlang:"
BINDING_STEP_MEDIA = [
    # {"type": "photo", "id": "FILE_ID"},
    # {"type": "video", "id": "FILE_ID"},
]

# "Viloyat" tanlanganda (BTS/Oddiy pochta savoli bilan birga) avtomatik yuboriladigan rasm
# None qoldiring - rasm yo'q, yoki fayl nomi/file_id yozing
DELIVERY_INFO_IMAGE = "AgACAgIAAxkBAAIBVmphtf0G5wtr-tbTvOB_PflLzymHAAJ2FmsbzOEQSxvrCnA5AAFTuQEAAwIAA3kAAz0E"

# Albom turidagi kitob tanlanganda yuboriladigan video (fayl nomi yoki file_id)
ALBOM_INFO_VIDEO = "BAACAgIAAxkBAAIBYWphtnBcRDkAAS6cD-Jt_LI9_ucyCAAC-y4AAkjLaUkJvIsekuQf6T0E"

# "ℹ️ Batafsil" tugmasi bosilganda ko'rsatiladigan qo'shimcha matnlar
FORMAT_DETAILED_INFO = (
    "ℹ️ Format haqida batafsil:\n\n"
    "📄 A4 — to'liq list hajmi\n"
    "📄 A5 — list hajmining yarmiga teng"
)
# "Batafsil" matniga qo'shimcha rasm(lar) (ixtiyoriy) - bo'sh ro'yxat qoldirsangiz
# faqat matn chiqadi. Bir nechta rasm qo'shmoqchi bo'lsangiz, shu ro'yxatga
# vergul bilan qo'shib boring: ["file_id_1", "file_id_2"]
FORMAT_DETAILED_IMAGES = ["AgACAgIAAxkBAAIEmmpjSEHim3p2Uu-Ec8agVmRO9NL2AAKFGWsbQVcgS1wVT7aAB7VLAQADAgADeAADPQQ",
                          "AgACAgIAAxkBAAIDNGpi7Ew0QVmup-czl88sw1aGYL5YAAL8GGsbQVcYSy8mU6HHzLmFAQADAgADeQADPQQ"
                          ]

# Pereplyot (Termokley/Prujina) "ℹ️ Batafsil" bosilganda ko'rsatiladigan matn va rasm(lar)
BINDING_DETAILED_INFO = (
    "ℹ️ Pereplyot haqida batafsil:\n\n"
    "📚 Termokley — kleyli, a5 format uchun maslahat bermaymiz, o'qish uchun biroz noqulay, lekin a4 formatda termokletli qilmoqchi bo'lsangiz bo'ladi\n"
    "🌀 Prujinali — a4 va a5 format uchun sahifalarni to'liq ochib o'qish, yozishga ham qulay va mustahkam"
)
BINDING_DETAILED_IMAGES = [
    # "file_id_1", "file_id_2"
]

DELIVERY_DETAILED_INFO = (
    "ℹ️ BTS va Oddiy pochta farqi:\n\n"
    "🚛 BTS — yetkazish haqini QABUL QILUVCHI to'laydi.\n"
    "📮 Oddiy pochta — yetkazish narxi buyurtma summasiga qo'shiladi (kitoblar soniga qarab hisoblanadi). "
    "Narxlar jadvalini yuqoridagi rasmdan ko'rishingiz mumkin."
)
# "Batafsil" matniga qo'shimcha rasm (ixtiyoriy) - bo'sh qoldirsangiz faqat matn chiqadi.
DELIVERY_DETAILED_IMAGE = None

# Albomniy kitob tanlanganda "ℹ️ Batafsil" bosilsa chiqadigan matn (video ALBOM_INFO_VIDEO
# bilan birga yuboriladi, agar u sozlangan bo'lsa).
ALBOM_DETAILED_INFO = (
    "ℹ️ Albom formati haqida batafsil:\n\n"
    "📘 Kitobning elektron faylida bitta betning ichida ikkita sahifa bo'lsa, chop qilingan kitob ham xuddi shu ko'rinishda chiqadi.\n"
    "📄 Faqat A4 formatda chop etiladi.\n"
    "📚 Agar kitob oddiy ko'rinishda chiqishini xohlasangiz, elektron faylning formatini internetdagi saytlar yoki dasturlar yordamida o'zgartirib,bizga qayta yuboring."
)

# ============ FAQ (Ma'lumotlar bo'limi) ============
# Har bir FAQ elementi: {"text": "...", "media": [...]}
# media - ro'yxat, ichida bir nechta rasm/video/lokatsiya bo'lishi mumkin (yoki bo'sh ro'yxat/[])
# Har bir element: {"type": "photo", "id": "fayl_nomi.jpg" yoki "file_id"}
#                  {"type": "video", "id": "fayl_nomi.mp4" yoki "file_id"}
#                  {"type": "location", "lat": 41.123, "lon": 69.456}
# file_id olish uchun: adminning shaxsiy chatida botga /fileid buyrug'ini yozing, keyin fayl yuboring
FAQ_ANSWERS = {
    "hours": {
        "text": "🕐 Ish vaqtimiz:\n\nDushanba - Juma: 08:00 - 21:00\nShanba - Yakshanba: 12:00 - 21:00",
        "media": [],
    },
    "merge": {
        "text": (
            "📎 Bir nechta kitobni birlashtirish:\n\n"
            "Agar bir nechta PDF faylni bitta kitob qilib chop etishni xohlasangiz, "
            "quyidagi bepul saytlardan foydalanib birlashtirishingiz mumkin:\n\n"
            "🔗 https://www.ilovepdf.com/merge_pdf\n"
            "🔗 https://smallpdf.com/merge-pdf\n\n"
            "Birlashtirilgan faylni shu botga yuboring."
        ),
        "media": [
        {"type": "photo", "id": "AgACAgIAAxkBAAIBU2phte4aAj_OT1G_b8AD0vpZk7nGAAJ0FmsbzOEQS0R1BFc5aNA8AQADAgADeQADPQQ"}
    ],
    },
    "trim": {
        "text": (
            "✂️ Keraksiz sahifalarni olib tashlash:\n\n"
            "Agar faylingizda keraksiz (bo'sh yoki ortiqcha) sahifalar bo'lsa, "
            "quyidagi saytlar orqali ularni olib tashlashingiz mumkin:\n\n"
            "🔗 https://www.ilovepdf.com/remove_pages\n"
            "🔗 https://smallpdf.com/delete-pages-from-pdf"
        ),
        "media": [
        {"type": "photo", "id": "AgACAgIAAxkBAAIBVWphtfqtpZBygSs-OF9BnRo7Vh-3AAJ1FmsbzOEQS8_O-4mdmwnzAQADAgADeQADPQQ"}
    ],
    },
    "address": {
        "text": (
            "📍 Manzilimiz:\n\n"
            "Xalqlar do'stligi metrodan 300 metr uzoqlikda, Internation o'quv markazi orqasi "
            "yoki Narxoz orqa darvozasiga yaqin.\n\n"
            "📞 Bog'lanish: @{support}"
        ),
        "media": [
            # Pastdagi ikkala qatorga /fileid orqali olingan file_id larni qo'ying:
            {"type": "photo", "id": "AgACAgIAAxkBAAIBu2ph5eg_elgMLbj6ExpeePHUJpoKAAKeFmsbQVcQSyuBYiqdGe4oAQADAgADeQADPQQ"},
            {"type": "photo", "id": "AgACAgIAAxkBAAIDMWpi6-IAAWVzNCWPz_G3zzVOdrPgcgAC-xhrG0FXGEsCmU3OagoXOAEAAwIAA3kAAz0E"},
            {"type": "location", "lat": 41.310391, "lon": 69.246070},  # koordinatalarni almashtiring
        ],
    },
    "ready_time": {
        "text": "⏱ Buyurtma 24-48 soat ichida tayyor bo'ladi. Shoshilinch buyurtmalar uchun admin bilan bog'laning.",
        "media": [],
    },
    "yandex_call": {
        "text": (
            "🚕 YANDEX/UKLON orqali chaqirish:\n\n"
            "YANDEX ga kiritish uchun raqam: +998977234353\n\n"
            "Yandex yoki Uklon ilovasidan Dostavka bo'limi orqali, jo'natuvchi nomiga bizning "
            "WEPRINT manzilimizni, qabul qiluvchiga esa o'z manzilingizni kiritasiz.\n\n"
            "Iltimos hamma ma'lumotlarni yuboring:"
            "• Buyurtma raqami:\n"
            "• Telefon raqamingiz:\n"
            "• Dostavka (Yandex/Uklon) havolasi\n\n"
        ),
        "media": [
            {"type": "photo", "id": "AgACAgIAAxkBAAIDL2pi68z8RwZHIMWTsle4umlM1eTiAAL6GGsbQVcYS2JzP9f0G4sxAQADAgADeQADPQQ"},
        ],
    },
}

# ============ MATNLAR ============
TXT_WELCOME = "👋 WEPRINT botiga xush kelibsiz!\n\n📱 Davom etish uchun telefon raqamingizni yuboring."
TXT_MAIN_MENU = "Quyidagi bo'limlardan birini tanlang 👇"
TXT_WARNING = (
    "❗️ Diqqat, buyurtma berishdan oldin o'qing:\n\n"
    "❌ Diniy manbalar qabul qilinmaydi.\n"
    "❌ Mualliflik huquqini buzuvchi kitoblar qabul qilinmaydi.\n\n"
    "📄 Faqat BITTA Pdf yoki Word fayl yuboring."
)
TXT_INFO = (
    "ℹ️ WEPRINT haqida ma'lumot:\n\n"
    "📍 Biz kitob, referat, diplom va boshqa hujjatlaringizni sifatli chop etamiz.\n"
    "💳 To'lov 100% oldindan.\n"
    "⏱ Buyurtma tayyorlanish vaqti: odatda 24-48 soat ichida.\n"
    "    @weprint kanalimizda kitoblar sifatini ko'rishingiz mumkin\n\n"
    "Katta hajmda kitob buyurtma qilmoqchi bo'lsangiz, admin bilan bog'laning."
)
