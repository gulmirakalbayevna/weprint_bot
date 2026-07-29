import sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = "weprint.db"


def get_conn():
    # timeout=30: baza band bo'lsa (boshqa yozuv ketayotgan bo'lsa) darhol xato
    # chiqarish o'rniga 30 soniyagacha kutadi - "database is locked" xatosining oldini oladi.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    # WAL rejimi: bir vaqtda o'qish va yozish operatsiyalari bir-biriga xalaqit bermaydi.
    # Bir nechta foydalanuvchi bir vaqtda botga yozganda muhim.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone TEXT,
            full_name TEXT,
            username TEXT
        )""")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT UNIQUE,
            user_id INTEGER,
            status TEXT DEFAULT 'collecting',
            binding TEXT,
            delivery_type TEXT,
            delivery_detail TEXT,
            university TEXT,
            receiver_phone TEXT,
            pochta_narxi INTEGER DEFAULT 0,
            books_total INTEGER DEFAULT 0,
            grand_total INTEGER DEFAULT 0,
            receipt_file_id TEXT,
            receipt_type TEXT,       -- photo yoki document
            pochta_receipt_file_id TEXT,   -- pochta narxi uchun IKKINCHI chek
            pochta_receipt_type TEXT,      -- photo yoki document
            completed_at TEXT,        -- buyurtma to'liq shakllangan payt (status='completed' bo'lgan vaqt)
            ready_at TEXT,             -- print qilinib TAYYOR deb belgilangan vaqt
            delivered_at TEXT,         -- kuryer "Yetkazildi" bosgan vaqt
            created_at TEXT
        )""")

        # Eski (allaqachon yaratilgan) bazalarga yangi ustunlarni qo'shish uchun
        # migratsiya - "CREATE TABLE IF NOT EXISTS" eski jadvalga yangi ustun
        # qo'shmaydi, shuning uchun buni qo'lda qilamiz. Ustun allaqachon bo'lsa,
        # xatoni jim yutamiz.
        for column_def in [
            "ALTER TABLE orders ADD COLUMN pochta_receipt_file_id TEXT",
            "ALTER TABLE orders ADD COLUMN pochta_receipt_type TEXT",
            "ALTER TABLE orders ADD COLUMN completed_at TEXT",
            "ALTER TABLE orders ADD COLUMN ready_at TEXT",
            "ALTER TABLE orders ADD COLUMN delivered_at TEXT",
            "ALTER TABLE orders ADD COLUMN received_at TEXT",
        ]:
            try:
                cur.execute(column_def)
            except sqlite3.OperationalError:
                pass  # ustun allaqachon mavjud

        # UMUMIY ADMIN NAVBATI: kitob (sahifa/tur so'rash) va chek tekshirish
        # (oddiy yoki pochta to'lovi) BITTA FIFO navbatda saqlanadi - shunda
        # admin bir vaqtning o'zida faqat BITTA vazifa bilan ishlaydi, ular
        # bir-biriga aralashib ketmaydi (turi qandayligidan qat'i nazar).
        cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,      -- 'book' | 'receipt' | 'receipt_pochta'
            ref_id INTEGER,      -- book_id ('book' uchun) yoki order_id (chek turlarida)
            created_at TEXT
        )""")
        conn.commit()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            seq_num INTEGER,
            file_id TEXT,
            file_name TEXT,
            page_count INTEGER,
            book_type TEXT,          -- knijniy / albom
            format_key TEXT,         -- a4_bw, a4_color, a5_bw, a5_color
            binding TEXT,            -- termokley / prujina
            copies INTEGER,
            price INTEGER,
            status TEXT DEFAULT 'awaiting_admin',  -- awaiting_admin, awaiting_format, awaiting_copies, done, rejected
            printed INTEGER DEFAULT 0,  -- print xodimi "Print qilindi" bosganmi (0/1) - faqat print guruh uchun, userga ta'sir qilmaydi
            printed_by TEXT,            -- print qilgan xodimning yozgan ismi
            source_chat_id INTEGER,     -- fayl qaysi chatdan kelgan (keyinroq forward qilish uchun)
            source_message_id INTEGER,  -- o'sha xabarning ID si
            print_info_chat_id INTEGER,    -- PRINT guruhidagi "info" xabari qaysi chatda
            print_info_message_id INTEGER, -- o'sha "info" xabarining ID si (keyinroq tahrirlash uchun)
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )""")
        conn.commit()

        # books jadvaliga yangi ustunlarni eski bazalarga ham qo'shish
        for column_def in [
            "ALTER TABLE books ADD COLUMN printed INTEGER DEFAULT 0",
            "ALTER TABLE books ADD COLUMN printed_by TEXT",
            "ALTER TABLE books ADD COLUMN source_chat_id INTEGER",
            "ALTER TABLE books ADD COLUMN source_message_id INTEGER",
            "ALTER TABLE books ADD COLUMN print_info_chat_id INTEGER",
            "ALTER TABLE books ADD COLUMN print_info_message_id INTEGER",
        ]:
            try:
                cur.execute(column_def)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # ustun allaqachon mavjud


def create_admin_task(task_type: str, ref_id: int) -> int:
    """Admin uchun umumiy navbatga yangi vazifa qo'shadi ('book', 'receipt' yoki
    'receipt_pochta'). Vazifalar FIFO tartibida (id bo'yicha) ko'rsatiladi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "INSERT INTO admin_tasks (task_type, ref_id, created_at) VALUES (?,?,?)",
            (task_type, ref_id, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid


def get_next_admin_task():
    """Navbatdagi eng eski vazifani qaytaradi (hali o'chirilmagan)."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_tasks ORDER BY id ASC LIMIT 1")
        return cur.fetchone()


def delete_admin_task(task_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM admin_tasks WHERE id=?", (task_id,))
        conn.commit()


def upsert_user(user_id, full_name, username, phone=None):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone():
            if phone:
                cur.execute("UPDATE users SET phone=?, full_name=?, username=? WHERE user_id=?",
                            (phone, full_name, username, user_id))
        else:
            cur.execute("INSERT INTO users (user_id, phone, full_name, username) VALUES (?,?,?,?)",
                        (user_id, phone, full_name, username))
        conn.commit()


def get_user(user_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()


def create_order(user_id) -> int:
    """Foydalanuvchi uchun yangi 'collecting' statusidagi buyurtma yaratadi va order_id qaytaradi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        # BEGIN IMMEDIATE: "bormi tekshirish" va "yo'q bo'lsa yaratish" orasiga
        # boshqa so'rov kirib, ikkita 'collecting' buyurtma yaratib yubormasligi uchun.
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT id FROM orders WHERE user_id=? AND status='collecting'", (user_id,))
        row = cur.fetchone()
        if row:
            conn.commit()
            return row["id"]
        cur.execute(
            "INSERT INTO orders (user_id, status, created_at) VALUES (?, 'collecting', ?)",
            (user_id, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid


def get_order(order_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        return cur.fetchone()


def get_active_order_for_user(user_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id=? AND status='collecting'", (user_id,))
        return cur.fetchone()


def get_cancellable_order_for_user(user_id):
    """cancel_order uchun MAXSUS funksiya - mijoz hali ham MUSTAQIL bekor
    qila oladigan buyurtmani topadi. get_active_order_for_user dan farqi:
    u faqat 'collecting' holatini qamrab oladi (buyurtma "resume" qilish
    uchun to'g'ri), lekin cancel_order o'zining ichida 'awaiting_admin_review'
    (chek yuborilgan, admin hali tasdiqlamagan) holatini ham bekor qilishga
    ruxsat beradi - shuning uchun uni ANIQ TOPA OLISHI ham kerak edi. Aks
    holda: mijoz chek yuborgach "Bekor qilish" bossa, bot "bekor qilindi"
    deb YOLG'ON aytar edi, lekin bazada buyurtma o'zgarmasdan qolib, keyinroq
    "tugallanmagan buyurtma" sifatida qayta chiqib kelaverar edi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE user_id=? AND status IN ('collecting','awaiting_admin_review') "
            "ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        return cur.fetchone()


def add_book(order_id, file_id, file_name, source_chat_id=None, source_message_id=None) -> int:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        # BEGIN IMMEDIATE: "sanash" va "yozish" orasiga boshqa so'rov kirib,
        # ikkita kitob bir xil seq_num olib qolmasligi uchun (race condition oldini olish).
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT COUNT(*) as c FROM books WHERE order_id=?", (order_id,))
        seq = cur.fetchone()["c"] + 1
        cur.execute(
            "INSERT INTO books (order_id, seq_num, file_id, file_name, status, source_chat_id, source_message_id) "
            "VALUES (?,?,?,?, 'awaiting_admin', ?, ?)",
            (order_id, seq, file_id, file_name, source_chat_id, source_message_id)
        )
        conn.commit()
        return cur.lastrowid


def get_book(book_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE id=?", (book_id,))
        return cur.fetchone()


def update_book(book_id, **fields):
    if not fields:
        return
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        cur.execute(f"UPDATE books SET {set_clause} WHERE id=?", (*fields.values(), book_id))
        conn.commit()


def get_unfinished_book_for_order(order_id):
    """
    Shu buyurtma uchun hali to'liq tugallanmagan (sahifa/format/nusxa hammasi
    tasdiqlanib 'done' bo'lmagan yoki 'rejected' qilinmagan) kitob bormi - tekshiradi.
    Foydalanuvchi bitta faylni tugatmasdan ikkinchisini yuborishini bloklash uchun ishlatiladi.
    """
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM books WHERE order_id=? AND status NOT IN ('done', 'rejected') "
            "ORDER BY id DESC LIMIT 1",
            (order_id,)
        )
        return cur.fetchone()


def get_next_awaiting_admin_book():
    """Navbatda turgan (hali sahifa soni kiritilmagan) eng eski kitobni qaytaradi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE status='awaiting_admin' ORDER BY id ASC LIMIT 1")
        return cur.fetchone()


def get_books_for_order(order_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM books WHERE order_id=? AND status != 'rejected' ORDER BY seq_num", (order_id,))
        return cur.fetchall()


def update_order(order_id, **fields):
    if not fields:
        return
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        cur.execute(f"UPDATE orders SET {set_clause} WHERE id=?", (*fields.values(), order_id))
        conn.commit()


def get_orders_for_user(user_id, limit=10):
    """Foydalanuvchining oxirgi buyurtmalari - faqat 'collecting' (hali
    tasdiqlanmagan, tugallanmagan savat) bundan mustasno. Bekor qilingan
    buyurtmalar ham ko'rsatiladi (ORDER_STATUS_LABELS orqali "Bekor qilingan"
    deb chiqadi), shunda foydalanuvchi ularni yo'qolib qolmaganini ko'radi.

    Faqat OXIRGI 30 KUNLIK buyurtmalar ko'rsatiladi - ro'yxat cheksiz
    o'sib ketmasligi uchun. Ma'lumotning o'zi bazadan o'chirilmaydi (statistika
    uchun saqlanadi), faqat ro'yxatda ko'rsatilmaydi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE user_id=? AND status != 'collecting' "
            "AND created_at >= datetime('now', '-30 days') "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        return cur.fetchall()


def get_completed_orders_in_range(lo_date: str, hi_date: str):
    """status='completed' (hali 'ready' emas) bo'lgan, completed_at sanasi
    [lo_date, hi_date] oralig'ida bo'lgan buyurtmalar - printerchi ular uchun
    'tayyor' deb belgilash imkoniyatiga ega bo'ladi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE status='completed' AND date(completed_at) BETWEEN ? AND ? ORDER BY completed_at",
            (lo_date, hi_date)
        )
        return cur.fetchall()


def finalize_order_code(order_id) -> str:
    """
    Buyurtmaga WP-00001 kabi kod beradi. MUHIM: bu funksiya faqat admin
    buyurtmani QABUL QILGANDA chaqirilishi kerak.

    IDEMPOTENT: agar shu buyurtmada ALLAQACHON kod bo'lsa - qayta yozmaydi.

    KOLLIZIYAGA CHIDAMLI: eski test ma'lumotlari yoki boshqa sabablarga ko'ra
    band bo'lib qolgan raqamlarni HISOBGA OLADI - shunchaki sanash (COUNT)
    o'rniga, barcha mavjud kodlarni tekshirib, band bo'lmagan birinchi raqamni
    topadi. Shu sabab UNIQUE xatosi endi HECH QACHON chiqmaydi.
    """
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        # BEGIN IMMEDIATE: "borligini tekshirish" va "yo'q bo'lsa yaratish"
        # orasiga boshqa so'rov kirib, xato/dublikat kod berilmasligi uchun.
        cur.execute("BEGIN IMMEDIATE")

        cur.execute("SELECT order_code FROM orders WHERE id=?", (order_id,))
        row = cur.fetchone()
        if row and row["order_code"]:
            conn.commit()
            return row["order_code"]

        cur.execute("SELECT order_code FROM orders WHERE order_code IS NOT NULL")
        existing_codes = {r["order_code"] for r in cur.fetchall()}

        # Eng katta mavjud raqamdan +1 dan boshlaymiz (COUNT emas - COUNT
        # bo'shliqlar/eski ma'lumotlar bo'lsa noto'g'ri natija berishi mumkin edi).
        seq = 1
        for existing_code in existing_codes:
            try:
                n = int(existing_code.split("-")[1])
                seq = max(seq, n + 1)
            except (IndexError, ValueError):
                continue

        # Har ehtimolga qarshi - band bo'lmagan raqam topilguncha oshiraveramiz.
        # Bu qator amalda deyarli hech qachon 1 martadan ortiq aylanmaydi,
        # lekin xato chiqmasligini 100% kafolatlaydi.
        while f"WP-{seq:05d}" in existing_codes:
            seq += 1
        code = f"WP-{seq:05d}"

        cur.execute("UPDATE orders SET order_code=? WHERE id=?", (code, order_id))
        conn.commit()
        return code


def get_stats(date_from: str, date_to: str):
    """Berilgan sana oralig'ida (created_at bo'yicha) TASDIQLANGAN (order_code
    bor) buyurtmalar, kitoblar soni va umumiy summani qaytaradi."""
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as order_count, COALESCE(SUM(grand_total),0) as total_sum "
            "FROM orders WHERE order_code IS NOT NULL AND date(created_at) BETWEEN ? AND ?",
            (date_from, date_to)
        )
        row = cur.fetchone()

        cur.execute(
            "SELECT COUNT(*) as book_count FROM books b "
            "JOIN orders o ON b.order_id = o.id "
            "WHERE o.order_code IS NOT NULL AND date(o.created_at) BETWEEN ? AND ? AND b.status='done'",
            (date_from, date_to)
        )
        book_count = cur.fetchone()["book_count"]

        return {
            "order_count": row["order_count"],
            "total_sum": row["total_sum"],
            "book_count": book_count,
        }


def get_detailed_stats(date_from: str, date_to: str):
    """
    Berilgan sana oralig'i (created_at bo'yicha, kunlar INKLUZIV) uchun
    BATAFSIL statistika - faqat TASDIQLANGAN (order_code bor) buyurtmalar
    hisobga olinadi:

    - format bo'yicha kitoblar soni (a4_bw, a4_color, a5_bw, a5_color)
    - pereplyot bo'yicha kitoblar soni (termokley, prujina)
    - universitet bo'yicha buyurtmalar soni (delivery_type='universitet')
    - yetkazish turi bo'yicha buyurtmalar soni (pickup/yandex/viloyat_bts/
      viloyat_pochta/universitet)
    - xodimlar (printed_by) bo'yicha - kim nechta kitob "Print qilindi" deb
      belgilagan
    - jami buyurtmalar, jami kitoblar, jami tushum, o'rtacha buyurtma summasi
    """
    with closing(get_conn()) as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*) as order_count, COALESCE(SUM(grand_total),0) as total_sum "
            "FROM orders WHERE order_code IS NOT NULL AND date(created_at) BETWEEN ? AND ?",
            (date_from, date_to)
        )
        row = cur.fetchone()
        order_count = row["order_count"]
        total_sum = row["total_sum"]
        avg_order = round(total_sum / order_count) if order_count else 0

        cur.execute(
            "SELECT COUNT(*) as c FROM books b JOIN orders o ON b.order_id = o.id "
            "WHERE o.order_code IS NOT NULL AND date(o.created_at) BETWEEN ? AND ? AND b.status='done'",
            (date_from, date_to)
        )
        book_count = cur.fetchone()["c"]

        cur.execute(
            "SELECT b.format_key as k, COUNT(*) as c FROM books b "
            "JOIN orders o ON b.order_id = o.id "
            "WHERE o.order_code IS NOT NULL AND date(o.created_at) BETWEEN ? AND ? AND b.status='done' "
            "GROUP BY b.format_key",
            (date_from, date_to)
        )
        format_counts = {r["k"]: r["c"] for r in cur.fetchall() if r["k"]}

        cur.execute(
            "SELECT b.binding as k, COUNT(*) as c FROM books b "
            "JOIN orders o ON b.order_id = o.id "
            "WHERE o.order_code IS NOT NULL AND date(o.created_at) BETWEEN ? AND ? AND b.status='done' "
            "GROUP BY b.binding",
            (date_from, date_to)
        )
        binding_counts = {r["k"]: r["c"] for r in cur.fetchall() if r["k"]}

        cur.execute(
            "SELECT university as k, COUNT(*) as c FROM orders "
            "WHERE order_code IS NOT NULL AND date(created_at) BETWEEN ? AND ? "
            "AND delivery_type='universitet' GROUP BY university",
            (date_from, date_to)
        )
        university_counts = {(r["k"] or "—"): r["c"] for r in cur.fetchall()}

        cur.execute(
            "SELECT delivery_type as k, COUNT(*) as c FROM orders "
            "WHERE order_code IS NOT NULL AND date(created_at) BETWEEN ? AND ? "
            "AND delivery_type IS NOT NULL GROUP BY delivery_type",
            (date_from, date_to)
        )
        delivery_counts = {r["k"]: r["c"] for r in cur.fetchall()}

        cur.execute(
            "SELECT b.printed_by as k, COUNT(*) as c FROM books b "
            "JOIN orders o ON b.order_id = o.id "
            "WHERE o.order_code IS NOT NULL AND date(o.created_at) BETWEEN ? AND ? "
            "AND b.printed=1 AND b.printed_by IS NOT NULL AND b.printed_by != '' "
            "GROUP BY b.printed_by",
            (date_from, date_to)
        )
        printer_counts = {r["k"]: r["c"] for r in cur.fetchall()}

        return {
            "order_count": order_count,
            "total_sum": total_sum,
            "book_count": book_count,
            "avg_order": avg_order,
            "format_counts": format_counts,
            "binding_counts": binding_counts,
            "university_counts": university_counts,
            "delivery_counts": delivery_counts,
            "printer_counts": printer_counts,
        }
