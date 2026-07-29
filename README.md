# WEPRINT Telegram Bot

## Nima qiladi
- Foydalanuvchidan telefon raqam, PDF fayl(lar), sahifa soni (admin kiritadi), format, nusxa soni, pereplyot, yetkazib berish ma'lumotlarini yig'adi
- Narxni **avtomatik** hisoblaydi (sahifa soni × format narxi × nusxa soni)
- Chek qabul qilib, adminga tekshirish uchun yuboradi
- Admin "✅ Qabul qilish" bossa — buyurtma **PRINT guruhiga** avtomatik yuboriladi (PDF + barcha info)
- Har bir kitob `WP-00051-1`, `WP-00051-2` kabi ikki qavatli kod oladi

## O'rnatish

```bash
cd weprint_bot
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Sozlash

1. `.env.example` faylini `.env` deb nusxalang:
   ```bash
   cp .env.example .env
   ```
2. `.env` faylini oching va quyidagilarni to'ldiring:
   - `BOT_TOKEN` — @BotFather dan olingan token
   - `ADMIN_ID` — sizning Telegram ID raqamingiz (@userinfobot orqali bilib oling)
   - `PRINT_GROUP_ID` — print operatorlar guruhi ID si (botni guruhga admin qilib qo'shing, keyin ID sini oling)
   - `QR_CODE_IMAGE` — to'lov QR kodi rasm fayli (`bot/` papkasiga joylashtiring)

3. `bot/config.py` faylida narxlarni o'zingizga moslab sozlang:
   - `PRICE_PER_PAGE` — har bir format uchun 1 sahifa narxi
   - `POCHTA_NARXLARI` — kitoblar soniga qarab oddiy pochta narxi
   - `UNIVERSITETLAR` — ro'yxatni kerakli universitetlar bilan to'ldiring

## Ishga tushirish

```bash
cd bot
python main.py
```

## Muhim eslatmalar

- **Bitta admin uchun mo'ljallangan.** Agar bir vaqtning o'zida bir nechta kitob fayli kelsa, ular navbatga qo'yiladi — admin bittasini tugatgach (sahifa sonini kiritib, turini tanlagach) bot avtomatik keyingisini so'raydi.
- Ma'lumotlar bazasi — `weprint.db` (SQLite), avtomatik yaratiladi.
- To'lov: hozircha faqat QR-kod (Paynet/Click/Payme) rasm ko'rinishida yuboriladi va chek qo'lda tekshiriladi. Avtomatik to'lov integratsiyasi yo'q.
- Botni guruhga qo'shganingizda, guruh ID sini olish uchun botga guruhda biror xabar yozdirib, so'ng `getUpdates` orqali yoki @RawDataBot yordamida ID ni ko'rishingiz mumkin. Guruh ID lari odatda `-100` bilan boshlanadi.
- Production uchun `python main.py` o'rniga `systemd` service yoki `screen`/`tmux`/`pm2` orqali doimiy ishlashini ta'minlang.

## Loyiha tuzilishi

```
weprint_bot/
├── bot/
│   ├── main.py           # botni ishga tushiradi
│   ├── config.py         # narxlar, ID lar, matnlar
│   ├── database.py       # SQLite bilan ishlash
│   ├── states.py         # FSM holatlari
│   ├── keyboards.py      # barcha tugmalar
│   ├── utils.py          # narx hisoblash funksiyalari
│   ├── handlers_user.py  # foydalanuvchi flow
│   └── handlers_admin.py # admin flow (sahifa, tur, tasdiqlash)
├── requirements.txt
├── .env.example
└── README.md
```
