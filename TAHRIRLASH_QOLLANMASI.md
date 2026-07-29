# O'ZINGIZ TAHRIRLASHINGIZ MUMKIN BO'LGAN JOYLAR

Barcha matnlar **bitta faylda** — `bot/config.py`. Uni Notepad bilan oching.

## ✅ XAVFSIZ TAHRIR QILISH MUMKIN BO'LGAN QISMLAR

- `TXT_WELCOME`, `TXT_MAIN_MENU`, `TXT_WARNING`, `TXT_INFO` — bot yuboradigan matnlar
- `FAQ_ANSWERS` — ish vaqti, manzil va boshqa tez-tez so'raladigan savollar javoblari
- `PRICE_PER_PAGE_BW`, `PRICE_PER_PAGE_COLOR`, `FLAT_PRICES`, `COVER_PRICE_TIERS` — narxlar (faqat raqamlarni o'zgartiring)
- `POCHTA_NARXLARI` — pochta narxlari
- `UNIVERSITETLAR` — ro'yxat

**Qoida:** tirnoq (`"`) va vergul (`,`) larni saqlab qoling, faqat ular orasidagi matn/raqamni o'zgartiring.

## ⚠️ RASM VA QR KOD FAYLLARI HAQIDA MUHIM ESLATMA

`qr_code.jpg` va `a4_a5_farqi.jpg` kabi rasm fayllari **albatta `bot/` papkasi ichida** bo'lishi kerak (`config.py`, `main.py` bilan bir joyda) — asosiy loyiha papkasida emas. Botni siz `bot/` papkasiga kirib ishga tushirasiz, shuning uchun u rasmlarni faqat o'sha yerdan qidiradi.

## ❌ TEGMASLIGINGIZ KERAK BO'LGAN FAYLLAR

`database.py`, `handlers_user.py`, `handlers_admin.py`, `keyboards.py`, `utils.py`, `main.py`, `states.py` — bu yerlarda kod mantiqi bor, o'zgartirish kerak bo'lsa menga yozing.

## O'ZGARTIRGANDAN KEYIN

1. `config.py` ni saqlang (`Ctrl+S`)
2. CMD da botni to'xtating (`Ctrl+C`), qayta ishga tushiring: `python main.py`
3. Xato chiqsa (`SyntaxError`) — tirnoq/vergul joyini tekshiring, yoki xato matnini menga yuboring

Tekshirish uchun: `python -m py_compile config.py` — hech narsa chiqmasa, fayl sog'lom.

## AGAR BOT "QOTIB QOLSA"

Odatda sabab shu: biror handler ichida kutilmagan xato (`Traceback`) chiqadi va CMD oynasida qizil matn ko'rinadi, lekin dastur o'zi to'xtamaydi — shunchaki o'sha bitta amal bajarilmay qoladi. **CMD oynasini albatta kuzatib turing** — u yerda "Traceback" so'zi bilan boshlangan xato chiqsa, o'sha matnni nusxalab oling va yuboring, shundan aniq nima ishlamaganini bilib bo'ladi.

Agar CMD oynasi butunlay muzlab qolsa (hech narsa chiqmaydi, javob bermaydi) — bu ko'proq kompyuterning uyquga ketishi, Wi-Fi uzilishi yoki Windows yangilanishi kabi tashqi sabablarga bog'liq bo'lishi mumkin. Uzoq muddat va barqaror ishlashi uchun, botni doimiy uy kompyuterida emas, **VPS (server)** da ishga tushirish tavsiya etiladi — bu haqda alohida so'rang, yordam beraman.
