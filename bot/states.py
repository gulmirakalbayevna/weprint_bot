from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    waiting_phone = State()
    main_menu = State()
    sending_books = State()          # PDF yuborish bosqichi
    waiting_copies = State()         # nusxa sonini kutish (Boshqa: tanlansa)
    waiting_delivery_address = State()
    waiting_price_calc_pages = State()
    waiting_receiver_phone = State()
    waiting_receiver_name = State()   # qabul qiluvchi telefon+ISMINI kiritish (yangi qo'shilgan)
    waiting_receipt = State()
    waiting_receipt_pochta = State()  # oddiy pochta narxi uchun IKKINCHI chekni kutish
    awaiting_payment_review = State()  # chek yuborildi, admin ko'rib chiqishini kutmoqda - bu ham "band" holat
    waiting_yandex_link = State()     # buyurtma TAYYOR bo'lgach, taksi havolasini kutish


class AdminFlow(StatesGroup):
    waiting_page_count = State()     # admin sahifa sonini kiritmoqda
    waiting_book_type = State()      # sahifa soni kiritilgan, lekin hali Knijniy/Albom tanlanmagan -
                                      # bu davrda ham admin "band" hisoblanadi, keyingi kitob yuborilmaydi
    waiting_file_for_id = State()    # admin /fileid buyrug'idan keyin fayl kutilmoqda
    waiting_ready_date_range = State()  # /tayyor buyrug'idan keyin sana oralig'ini kutish
    waiting_ready_confirm = State()     # sana oralig'i tasdiqlanishini kutish
    waiting_printer_name = State()      # "Print qilindi" bosilgach, xodim ismini kutish
    reviewing_receipt = State()         # chek (oddiy yoki pochta) ko'rib chiqilmoqda - admin "band"
    waiting_stat_date_range = State()   # /statistika -> "Sana oralig'i" tanlangach, sana kutilmoqda
