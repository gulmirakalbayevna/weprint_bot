"""
AI PRECHECK — kitob fayli PDF bo'lsa, admin qo'lda ish qilmasdan oldin
avtomatik tekshiradi:

  1) Arab yozuvi / diniy tarkib belgilari bormi?  (TXT_WARNING: "diniy
     manbalar qabul qilinmaydi" — bu HOZIR ham admin "❌ Rad etish" tugmasi
     orqali qo'lda hal qiladi; AI faqat DIQQATNI JALB QILADI, o'zi rad
     etmaydi.)
  2) Orientatsiya: barcha sahifalar KITOB (portrait) ko'rinishidami, ALBOM
     (landscape) ko'rinishidami, yoki ARALASHmi?
  3) Sahifalar soni.

QOIDA (asosiy tamoyil — TZ'dagi "AI operatorni almashtirmaydi" printsipi):
  - Agar fayl "toza" (arab/diniy belgi yo'q) VA orientatsiya BIR XIL
    (aralash emas) bo'lsa — bu SUBYEKTIV EMAS, OBYEKTIV fakt, shuning uchun
    handlers_admin.py bu holatda admin'dan so'ramasdan avtomatik davom
    etishi MUMKIN (config.AI_AUTO_APPROVE_ENABLED yoqilgan bo'lsa).
  - Agar arab/diniy belgi TOPILSA yoki orientatsiya ARALASH bo'lsa —
    HECH QACHON avtomatik davom etilmaydi, admin albatta o'zi ko'rib,
    qo'lda hal qiladi (faqat AI ogohlantiruvchi xabar bilan diqqatini
    tortadi).
  - PDF ochib bo'lmasa (buzilgan fayl, .docx va h.k.) — AI hech narsa
    demaydi, hamma narsa ILGARIGIDEK, to'liq qo'lda davom etadi.
"""
import re
import logging

logger = logging.getLogger("weprint.ai_precheck")

ARABIC_SCRIPT_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)

# Kengaytirilishi mumkin — ehtiyot chorasi sifatida keng tutilgan, lekin
# hech qachon YAKUNIY qaror uchun emas, faqat OGOHLANTIRISH uchun ishlatiladi.
RELIGIOUS_KEYWORDS = [
    "quran", "qur'on", "qur’on", "куръон", "коран", "hadis", "hadith", "хадис",
    "bismillah", "بسم الله", "аллах", "allah", "الله", "namaz", "намоз",
    "инжил", "injil", "bible", "тавро", "tavrot", "zabur", "забур",
]


def analyze_pdf(path: str) -> dict:
    """
    Muvaffaqiyatli bo'lsa:
        {
            "ok": True,
            "page_count": int,
            "book_type_guess": "knijniy" | "albom" | None,  # None = aralash
            "is_mixed_orientation": bool,
            "has_religious_flag": bool,
            "religious_hits": [...],
        }
    Muvaffaqiyatsiz bo'lsa (PDF emas, buzilgan va h.k.):
        {"ok": False, "reason": "..."}
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {"ok": False, "reason": "PyMuPDF (fitz) o'rnatilmagan"}

    try:
        doc = fitz.open(path)
    except Exception as e:
        return {"ok": False, "reason": f"PDF ochib bo'lmadi: {e}"}

    orientations = set()
    text_chunks = []
    try:
        for page in doc:
            rect = page.rect
            orientations.add("landscape" if rect.width > rect.height else "portrait")
            try:
                text_chunks.append(page.get_text())
            except Exception:
                pass  # skanerlangan sahifa — matnsiz bo'lishi mumkin
        page_count = doc.page_count
    finally:
        doc.close()

    is_mixed = len(orientations) > 1
    if is_mixed:
        book_type_guess = None
    elif orientations == {"landscape"}:
        book_type_guess = "albom"
    else:
        book_type_guess = "knijniy"

    full_text = "\n".join(text_chunks)
    has_arabic = bool(ARABIC_SCRIPT_RE.search(full_text))
    lowered = full_text.lower()
    religious_hits = [kw for kw in RELIGIOUS_KEYWORDS if kw.lower() in lowered]

    return {
        "ok": True,
        "page_count": page_count,
        "book_type_guess": book_type_guess,
        "is_mixed_orientation": is_mixed,
        "has_religious_flag": has_arabic or bool(religious_hits),
        "religious_hits": religious_hits,
    }


def is_safe_to_auto_approve(analysis: dict) -> bool:
    """Admin so'ramasdan avtomatik davom etish mumkinmi?"""
    return (
        analysis.get("ok")
        and not analysis.get("has_religious_flag")
        and not analysis.get("is_mixed_orientation")
        and analysis.get("book_type_guess") is not None
    )
