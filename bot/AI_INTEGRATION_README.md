# AI Precheck — mavjud WePrint botiga integratsiya

## Nima o'zgardi (4 fayl o'zgartirildi, 1 yangi fayl qo'shildi)

1. **`ai_precheck.py`** (YANGI) — PDF'ni tahlil qiladi: sahifa soni,
   orientatsiya (knijniy/albom/aralash), arab yozuvi/diniy kalit so'zlar.
2. **`database.py`** — `books` jadvaliga 6 ta yangi ustun qo'shildi
   (`ai_analyzed`, `ai_page_count`, `ai_book_type_guess`,
   `ai_mixed_orientation`, `ai_religious_flag`, `ai_auto_approved`).
   Eski ma'lumotlar BUZILMAYDI — bu xuddi sizning kodingizdagi boshqa
   `ALTER TABLE ... ADD COLUMN` qatorlari kabi, mavjud bazaga xavfsiz
   qo'shiladi.
3. **`handlers_user.py`** — `got_document` funksiyasida, kitob PDF bo'lsa,
   uni vaqtinchalik yuklab olib (`ai_tmp/` papkaga), tahlil qilib, natijani
   bazaga yozadi va faylni o'chirib tashlaydi. Bitta joyga ~25 qator kod
   qo'shildi, boshqa hech narsa o'zgarmagan.
4. **`handlers_admin.py`** — `_present_admin_task` funksiyasining "book"
   qismiga ikkita narsa qo'shildi:
   - Agar `config.AI_AUTO_APPROVE_ENABLED = True` bo'lsa VA fayl toza
     (arab/diniy yo'q) VA orientatsiya bir xil bo'lsa — **admin'dan
     so'ramasdan** sahifa soni + Knijniy/Albom turini AI o'zi belgilaydi,
     to'g'ridan-to'g'ri formatga o'tkazadi, adminga faqat **xabar** (tugmasiz,
     javob talab qilmaydi) yuboradi.
   - Aks holda (yoki `AI_AUTO_APPROVE_ENABLED = False` bo'lsa) — hammasi
     ILGARIGIDEK, admin qo'lda sahifa/tur kiritadi, LEKIN agar AI arab/diniy
     belgi yoki aralash orientatsiya sezsa, ⚠️ ALOHIDA ogohlantiruvchi xabar
     yuboriladi va sahifa soni bo'yicha AI'ning taxminini ham ko'rsatadi
     (admin baribir o'zi tasdiqlaydi/to'g'irlaydi).
5. **`config.py`** — 2 ta yangi sozlama:
   ```python
   AI_PRECHECK_ENABLED = True    # tahlil umuman ishlasinmi
   AI_AUTO_APPROVE_ENABLED = False  # admin'ni butunlay chetlab o'tishga ruxsat berilsinmi
   ```

## MUHIM: xavfsiz standart holat

`AI_AUTO_APPROVE_ENABLED` **standart holatda `False`** qilib qo'ydim.
Ya'ni hozircha botni shu holatda ishga tushirsangiz ham, **hech narsa
avtomatik o'zgarmaydi** — faqat AI orqa fonda tahlil qiladi va admin
ekraniga qo'shimcha ogohlantirish/taxmin ko'rsatadi. Siz bir necha kunlik
buyurtmalarda AI qanchalik to'g'ri ishlashini kuzatib, ishonch hosil
qilgach, `.env` faylda `AI_AUTO_APPROVE_ENABLED=1` qilib, avtomatik
o'tishni yoqasiz.

## O'rnatish

```bash
pip install PyMuPDF
```

(Boshqa hech qanday yangi kutubxona kerak emas — `python-telegram-bot`
emas, sizning botingiz `aiogram` ishlatadi, men shu bilan mos yozdim.)

## Sinov tartibi (tavsiya)

1. Avval `AI_AUTO_APPROVE_ENABLED=0` bilan bir necha kun ishlating —
   admin ekranida AI'ning taxminlari (sahifa soni, ogohlantirishlar)
   qanchalik to'g'ri ekanini solishtirib ko'ring, lekin qaror baribir
   sizda qoladi.
2. Ishonch hosil qilgach, `AI_AUTO_APPROVE_ENABLED=1` qiling — endi toza
   fayllar avtomatik o'tadi, faqat arab/diniy yoki aralash orientatsiyali
   fayllar sizga chiqadi.
3. Har doim: agar biror kitobda AI xato qilgan bo'lsa-yu, u avtomatik
   o'tib ketgan bo'lsa — hamon fayl mijozga chop etilmaguncha jismoniy
   qo'lingizda, shuning uchun oxirgi nazorat baribir sizda qoladi.

## Fayllar

Ushbu papkada — sizning ORIGINAL fayllaringiz + yuqoridagi o'zgarishlar.
O'zingizning ishlab turgan botingizga ustidan almashtirishdan oldin,
farqni ko'rish uchun `diff` bilan solishtirib chiqishni tavsiya qilaman
(masalan `diff eski_handlers_admin.py handlers_admin.py`).
