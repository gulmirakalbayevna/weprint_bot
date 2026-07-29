import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import socket
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

import config
from database import init_db
import handlers_admin
import handlers_user

# --- ERROR THROTTLING VA LOCK (GLOBAL O'ZGARUVCHILAR) ---
_error_lock = asyncio.Lock()
LAST_ERROR_SENT_TIME = 0
ERROR_THROTTLE_SECONDS = 60


class IPv4AiohttpSession(AiohttpSession):
    """
    Ba'zi provayder yoki serverlarda IPv6 noto'g'ri ishlanganda yuzaga keladigan
    ulanish xatoliklarining oldini olish uchun faqat IPv4 orqali ulanish majburiy qilinadi.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET


def setup_logging():
    # Log fayli 10 MB dan oshsa arxivlanadi, ko'pi bilan 5 ta fayl saqlanadi (Log rotation)
    rotating_handler = RotatingFileHandler(
        "bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            rotating_handler,
            logging.StreamHandler(),
        ],
    )


def build_storage():
    """
    FSM storage tanlash:
    REDIS_URL bo'lsa RedisStorage, aks holda MemoryStorage ishlatiladi.
    """
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage

            storage = RedisStorage.from_url(redis_url)
            logging.info("FSM storage: Redis (%s)", redis_url)
            return storage
        except Exception as e:
            logging.exception(
                "Redisga ulanib bo'lmadi, MemoryStorage'ga o'tildi: %s", e
            )

    logging.warning(
        "FSM storage: Memory (RAM) ishlatilmoqda. "
        "DIQQAT: bot qayta ishga tushsa, foydalanuvchilar holati yo'qoladi."
    )
    return MemoryStorage()


async def register_error_handler(dp: Dispatcher, bot: Bot):
    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        global LAST_ERROR_SENT_TIME

        update_id = event.update.update_id
        user_id = None
        try:
            if event.update.message:
                user_id = event.update.message.from_user.id
            elif event.update.callback_query:
                user_id = event.update.callback_query.from_user.id
        except Exception:
            logging.exception("Error handlerda user_id ni ajratib olishda xatolik")

        # Asosiy xatoni har doim logga yozamiz
        logging.exception(
            "GLOBAL XATO | update_id=%s | user_id=%s | xato: %s",
            update_id,
            user_id,
            event.exception,
        )

        # Race condition va adminga spam ketishining oldini olish uchun Lock va Throttling
        current_time = time.time()
        async with _error_lock:
            if current_time - LAST_ERROR_SENT_TIME > ERROR_THROTTLE_SECONDS:
                LAST_ERROR_SENT_TIME = current_time
                try:
                    # MUHIM: parse_mode="HTML" ni ATAYLAB o'chirib qo'yamiz -
                    # xato matnida (event.exception) '<', '>', '&' kabi
                    # belgilar bo'lsa (Python xatolarida tez-tez uchraydi,
                    # masalan 'list[int]' yoki '<class ...>'), bot standart
                    # HTML rejimida buni teg deb noto'g'ri tushunib, xato
                    # haqidagi XABARNING O'ZI yuborilmay qolar edi.
                    await bot.send_message(
                        config.ADMIN_ID,
                        f"⚠️ BOTDA KUTILMAGAN XATO!\n"
                        f"user_id={user_id}\n"
                        f"Xato: {event.exception}\n\n"
                        f"Batafsili bot.log faylida (update_id={update_id}).",
                        parse_mode=None,
                    )
                except Exception:
                    logging.exception("Adminga xato haqida bildirishnoma yuborishda xatolik yuz berdi")

        return True


async def main():
    setup_logging()

    # Unhandled asyncio exceptions (orqa fonda bajariladigan tasklar xatosi) uchun handler
    loop = asyncio.get_running_loop()

    def _asyncio_exception_handler(loop, ctx):
        exc = ctx.get("exception")
        # exc_info=exc beriladi - shunda logga XATONING TO'LIQ IZI (qaysi
        # qatorda, qaysi funksiyada yuz bergani) ham yoziladi. Oddiy
        # logging.exception() bu yerda ishlamas edi, chunki u faqat haqiqiy
        # 'except' blok ICHIDA chaqirilganda avtomatik iz oladi.
        logging.error("Asyncio exception: %s", ctx.get("message"), exc_info=exc)

    loop.set_exception_handler(_asyncio_exception_handler)

    init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=IPv4AiohttpSession(),
    )
    storage = build_storage()
    dp = Dispatcher(storage=storage)

    dp.include_router(handlers_admin.router)
    dp.include_router(handlers_user.router)

    await register_error_handler(dp, bot)

    try:
        # Webhook o'chirish (drop_pending_updates=False qilingan - xabarlar yo'qolmaydi)
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                break
            except TelegramNetworkError as e:
                logging.warning(
                    "Telegram bilan ulanib bo'lmadi (delete_webhook), "
                    "10 soniyadan keyin qayta urinaman: %s",
                    e,
                )
                await asyncio.sleep(10)

        # Polling restart sikli va barqaror ulanish parametrlari
        while True:
            try:
                await dp.start_polling(
                    bot,
                    polling_timeout=30,
                    handle_signals=True,
                )
                break
            except TelegramNetworkError as e:
                logging.warning(
                    "Polling paytida tarmoq uzildi, 10 soniyadan keyin qayta urinaman: %s",
                    e,
                )
                await asyncio.sleep(10)
            except Exception:
                logging.exception(
                    "Polling kutilmaganda to'xtadi, 10 soniyadan keyin qayta urinaman"
                )
                await asyncio.sleep(10)

    finally:
        # Graceful shutdown: Bot to'xtaganda session faqat shu yerda, bir marta yopiladi
        logging.info("Bot to'xtatilmoqda, session yopilmoqda...")
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())