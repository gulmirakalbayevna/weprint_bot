# ============================================================================
# BU FAYL ALOHIDA ISHLATISH UCHUN EMAS — mazmunini main.py (yoki bot.py,
# botni ishga tushiradigan asosiy faylingiz) ichiga QO'SHING.
#
# NEGA KERAK: handlers_admin.py va handlers_user.py da qo'shilgan try/except
# bloklari faqat "kutilgan" joylardagi xatolarni ushlaydi va logga yozadi.
# Lekin agar boshqa (bashorat qilinmagan) joyda xato chiqsa, aiogram uni
# hech kimga ko'rsatmasdan "yutib yuborishi" mumkin — shuning uchun butun
# botga BITTA marta shu global handler o'rnatiladi. Shundan keyin HECH QANDAY
# xato izsiz yo'qolmaydi — hammasi bot.log fayliga yoziladi.
# ============================================================================

import logging
from aiogram.types import ErrorEvent

# 1) Logging'ni FAYLGA yozadigan qilib sozlang (agar hali sozlanmagan bo'lsa).
#    Buni main.py ning ENG BOSHIDA, dp/bot yaratilishidan oldin qo'ying:
#
# logging.basicConfig(
#     level=logging.INFO,
#     filename="bot.log",
#     encoding="utf-8",
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
# )

# 2) Dispatcher yaratilgandan keyin (dp = Dispatcher() dan keyin), shuni qo'shing:
#
# @dp.errors()
# async def global_error_handler(event: ErrorEvent):
#     """
#     Botning ISTALGAN handlerida chiqadigan, kutilmagan (try/except bilan
#     ushlanmagan) barcha xatolarni ushlaydi. Shu bo'lmasa, xato hech qayerda
#     ko'rinmay, foydalanuvchi shunchaki "javob kelmadi" deb qoladi.
#     """
#     logging.exception(
#         "GLOBAL XATO | update_id=%s | xato: %s",
#         event.update.update_id,
#         event.exception,
#     )
#
#     # Kimning so'rovida xato chiqqanini aniqlashga harakat qilamiz (logga qo'shimcha)
#     user_id = None
#     try:
#         if event.update.message:
#             user_id = event.update.message.from_user.id
#         elif event.update.callback_query:
#             user_id = event.update.callback_query.from_user.id
#     except Exception:
#         pass
#     logging.error(f"GLOBAL XATO tegishli user_id={user_id}")
#
#     # Ixtiyoriy, lekin TAVSIYA ETILADI: adminga DARHOL bildirishnoma.
#     # Shunda "kimningdir xabari yetib bormadi" holatini SIZ EMAS, BOT o'zi
#     # sizga aytadi - foydalanuvchi shikoyat qilishini kutib o'tirmaysiz.
#     try:
#         from aiogram import Bot
#         import config
#         # `bot` obyekti global bo'lsa shu yerdan foydalaning, aks holda
#         # dispatcher ishga tushirilgan joydagi bot nomini shu yerga yozing.
#         await bot.send_message(
#             config.ADMIN_ID,
#             f"⚠️ BOTDA KUTILMAGAN XATO!\nuser_id={user_id}\nXato: {event.exception}\n\n"
#             f"Batafsili bot.log faylida."
#         )
#     except Exception:
#         pass
#
#     return True  # xato "hazm qilindi" deb belgilaymiz, bot ishlashda davom etadi
