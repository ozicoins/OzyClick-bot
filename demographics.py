"""
demographics.py — hesap (çerez) DEMOGRAFİ katmanı.

İş mantığı: rakip kampanyalar reklamı YAŞ+CİNSİYET ile hedefler; hedefe UYMAYAN
hesaba mobil SERP'te o reklam GÖRÜNMEZ. Bu yüzden bot, her hesabın demografisini
BİLMELİ ve hedef segmente uyanı seçmeli ("unknown" olanı hedefli koşuda elemeli).

Demografi ETİKETİ üç kaynaktan okunur (öncelik sırası):
  1) Çerez JSON'una gömülü:  {"demographic": {"age": "...", "gender": "..."}}  (veya top-level age/gender)
  2) Sidecar dosya:          <cerez>.meta.json  →  {"demographic": {...}} veya {"age","gender"}
  3) Dosya adı kuralı:       ..._k_25-34.json / ..._female_35-44.json  (delimited token'lar)

Yaşlandırılmış hazır mailler demografiyi Google TARAFINDA taşır → read_demographic_via_adcenter()
ile bir kez okunup sidecar'a yazılır (kalıcı, çereze dokunmaz). Sonra seçim hep etiketten yapılır.

Bu modül tarayıcı/ağ bağımlılığı OLMADAN import edilebilir (ad-center okuyucu hariç, o async).
"""

import os
import re
import json

AGE_BUCKETS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
GENDERS = ("female", "male", "unknown")
UNKNOWN = "unknown"

# ---- dosya-adı token eşlemeleri (delimited: _,-,.,baş/son ile çevrili olmalı) ----
_GENDER_TOKENS = {
    "female": "female", "woman": "female", "women": "female", "f": "female",
    "kadin": "female", "kadın": "female", "k": "female", "w": "female", "bayan": "female",
    "male": "male", "man": "male", "men": "male", "m": "male",
    "erkek": "male", "e": "male", "bay": "male",
}


# ============================== NORMALİZASYON ==============================
def age_to_bucket(n) -> str:
    """Ham yaş (int) → kova. Aralık dışı/geçersiz → 'unknown'."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return UNKNOWN
    if n < 18:
        return UNKNOWN
    for lo, hi, b in ((18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"),
                      (45, 54, "45-54"), (55, 64, "55-64")):
        if lo <= n <= hi:
            return b
    return "65+" if n >= 65 else UNKNOWN


def normalize_age(raw) -> str:
    """Ham yaş değerini (int / '25-34' / '25 - 34 yaş' / '65+' / '31') kanonik kovaya çevirir."""
    if raw is None:
        return UNKNOWN
    if isinstance(raw, (int, float)):
        return age_to_bucket(raw)
    s = str(raw).strip().lower().replace("–", "-").replace("—", "-")
    if not s or s in ("unknown", "bilinmiyor", "belirsiz", "n/a", "-"):
        return UNKNOWN
    if "65" in s and "+" in s:
        return "65+"
    m = re.search(r"(\d{2})\s*-\s*(\d{2})", s)      # "25-34", "25 - 34 yaş"
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        mid = (lo + hi) // 2
        # verilen aralığın orta noktasını kovala (Google bazen 26-33 gibi verir)
        b = age_to_bucket(mid)
        if b != UNKNOWN:
            return b
        # tam kova eşleşmesi
        cand = f"{lo}-{hi}"
        return cand if cand in AGE_BUCKETS else UNKNOWN
    m = re.search(r"\b(\d{1,3})\b", s)              # tek sayı → kova
    if m:
        return age_to_bucket(m.group(1))
    return UNKNOWN


def normalize_gender(raw) -> str:
    """Ham cinsiyeti (tr/en, kısaltma) → 'female'|'male'|'unknown'."""
    if raw is None:
        return UNKNOWN
    s = str(raw).strip().lower()
    if not s or s in ("unknown", "bilinmiyor", "belirsiz", "diğer", "other", "n/a", "-", "?"):
        return UNKNOWN
    # AÇIK alan değeri: 'K'/'E' (Türkçe kısaltma), 'f'/'m', 'kadın'/'erkek'... hepsi map'lenir.
    # (Tek-harf guard'ı KALDIRILDI: {"gender":"K"} unknown'a düşüyordu → cinsiyet hedefinde eleniyordu.)
    if s in _GENDER_TOKENS:
        return _GENDER_TOKENS[s]
    if s in ("female", "kadın", "kadin", "woman", "bayan"):
        return "female"
    if s in ("male", "erkek", "man", "bay"):
        return "male"
    return UNKNOWN


def normalize_demo(age=None, gender=None, source="") -> dict:
    return {"age": normalize_age(age), "gender": normalize_gender(gender), "source": source or ""}


def is_known(demo: dict) -> bool:
    """En az bir boyutu (yaş VEYA cinsiyet) bilinen hesap 'bilinen' sayılır."""
    if not demo:
        return False
    return demo.get("age", UNKNOWN) != UNKNOWN or demo.get("gender", UNKNOWN) != UNKNOWN


def demo_label(demo: dict) -> str:
    """Panelde/CSV'de göstermek için kısa etiket: 'K·25-34' / 'E·?' / '?'."""
    if not demo:
        return "?"
    g = demo.get("gender", UNKNOWN)
    a = demo.get("age", UNKNOWN)
    gl = {"female": "K", "male": "E"}.get(g, "?")
    al = a if a != UNKNOWN else "?"
    return f"{gl}·{al}" if (gl != "?" or al != "?") else "?"


# ============================== ETİKET KAYNAKLARI ==============================
def _demo_from_dict(d: dict) -> dict:
    """Çerez/sidecar dict'inden demografi çıkar. Gömülü 'demographic' veya top-level age/gender."""
    if not isinstance(d, dict):
        return normalize_demo(source="")
    dm = d.get("demographic")
    if isinstance(dm, dict):
        return normalize_demo(dm.get("age"), dm.get("gender"), dm.get("source") or "embedded")
    # top-level alanlar
    age = d.get("age") if d.get("age") is not None else d.get("age_range")
    gen = d.get("gender") if d.get("gender") is not None else d.get("sex")
    if age is not None or gen is not None:
        return normalize_demo(age, gen, "embedded")
    return normalize_demo(source="")


def _demo_from_filename(path: str) -> dict:
    """Dosya adındaki delimited token'lardan demografi (kova + cinsiyet). Konservatif."""
    base = os.path.basename(path)
    stem = os.path.splitext(base)[0].replace("–", "-").replace("—", "-")   # #17: en/em-dash → '-'
    toks = [t for t in re.split(r"[^0-9A-Za-zçğıöşüÇĞİÖŞÜ+]+", stem) if t]
    age = UNKNOWN
    gender = UNKNOWN
    # SADECE tam kova ("25-34"/"65+") kabul edilir. Bare 2-haneli token (order-24, backup_45)
    # ARTIK yaş sayılmaz (uydurma kova bug'ı: '..._45_...' → 45-54 yanlıştı).
    # 65+ zorunlu '+' (bare '65' yaş sanılmaz: #6) + lookaround bitişik HARFİ de reddeder
    # ('promo25-34batch' eşleşmez ama '_25-34' eşleşir: #15).
    m = re.search(r"(?<![0-9A-Za-zçğıöşüÇĞİÖŞÜ])(18-24|25-34|35-44|45-54|55-64|65\+)(?![0-9A-Za-zçğıöşüÇĞİÖŞÜ])", stem)
    if m:
        age = normalize_age(m.group(1))
    for t in toks:
        tl = t.lower()
        # Cinsiyet token'ı: çok-harfli (erkek/kadın/female) HER ZAMAN; tek-harf (k/e/m/f/w) YALNIZ
        # bir yaş kovası da bulunduysa (belgelenmiş '_k_25-34' kuralı) → 'e_ticaret' false-positive'i biter.
        if gender == UNKNOWN and tl in _GENDER_TOKENS and (len(tl) > 1 or age != UNKNOWN):
            gender = _GENDER_TOKENS[tl]
    if age == UNKNOWN and gender == UNKNOWN:
        return normalize_demo(source="")
    return normalize_demo(age, gender, "filename")


def sidecar_path(path: str) -> str:
    """<cerez>.meta.json (çereze dokunmadan demografi saklamak için)."""
    return os.path.splitext(path)[0] + ".meta.json"


def _demo_from_sidecar(path: str) -> dict:
    sp = sidecar_path(path)
    try:
        if os.path.isfile(sp):
            with open(sp, "r", encoding="utf-8") as f:
                return _demo_from_dict(json.load(f))
    except Exception:
        pass
    return normalize_demo(source="")


def demographic_from_data(data: dict, path: str = "") -> dict:
    """Yüklü çerez dict'i + yol → demografi. Yaş ve cinsiyet AYRI AYRI birleştirilir:
    her boyut için ilk BİLEN kaynak (öncelik: gömülü > sidecar > dosya-adı). Böylece gömülü
    yalnız yaş taşısa bile sidecar'daki cinsiyet OKUNUR (kısmi-etiket bug'ı çözüldü)."""
    out = _demo_from_dict(data or {})
    out = {"age": out.get("age", UNKNOWN), "gender": out.get("gender", UNKNOWN),
           "source": out.get("source", "") if is_known(out) else ""}
    if path and (out["age"] == UNKNOWN or out["gender"] == UNKNOWN):
        for s in (_demo_from_sidecar(path), _demo_from_filename(path)):
            if out["age"] == UNKNOWN and s.get("age", UNKNOWN) != UNKNOWN:
                out["age"] = s["age"]; out["source"] = out["source"] or s.get("source", "")
            if out["gender"] == UNKNOWN and s.get("gender", UNKNOWN) != UNKNOWN:
                out["gender"] = s["gender"]; out["source"] = out["source"] or s.get("source", "")
            if out["age"] != UNKNOWN and out["gender"] != UNKNOWN:
                break
    return out


def demographic_from_file(path: str) -> dict:
    """Dosya yolundan demografi oku (çerezi açar). Pool init'te kullanılır."""
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return demographic_from_data(data, path)


def write_sidecar(path: str, demo: dict) -> bool:
    """Taranan demografiyi sidecar'a yaz (kalıcı; çereze dokunmaz)."""
    try:
        with open(sidecar_path(path), "w", encoding="utf-8") as f:
            json.dump({"demographic": {"age": demo.get("age", UNKNOWN),
                                       "gender": demo.get("gender", UNKNOWN),
                                       "source": demo.get("source", "adcenter")}},
                      f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ============================== HEDEF & EŞLEŞME ==============================
def parse_target_ages(text) -> list:
    """'25-34, 35-44' / liste → kanonik kova listesi. Boş → [] (yaş hedeflemesi kapalı)."""
    if not text:
        return []
    items = text if isinstance(text, (list, tuple)) else re.split(r"[,\s;]+", str(text))
    out = []
    for it in items:
        b = normalize_age(it)
        if b != UNKNOWN and b not in out:
            out.append(b)
    return out


def normalize_target_gender(text) -> str:
    """Hedef cinsiyet → 'female'|'male'|'' (boş = kapalı)."""
    if not text:
        return ""
    s = str(text).strip().lower()
    if s in ("", "any", "hepsi", "tümü", "tumu", "kapalı", "kapali", "farketmez", "hepsi (kapalı)"):
        return ""
    g = normalize_gender(s)
    return g if g in ("female", "male") else ""


def matches(demo: dict, target_ages, target_gender, require_known=True) -> bool:
    """Hesap demografisi hedefe uyuyor mu? Hedeflenen boyutta 'unknown' → ELENİR (unknown olmasın)."""
    ta = list(target_ages or [])
    tg = normalize_target_gender(target_gender)
    if not ta and not tg:
        return True                                  # demografi hedeflemesi yok → herkes uygun
    age = (demo or {}).get("age", UNKNOWN)
    gen = (demo or {}).get("gender", UNKNOWN)
    if ta:
        if age == UNKNOWN:
            if require_known:      # varsayılan: hedeflenen boyutta unknown → ELENİR
                return False
        elif age not in ta:
            return False
    if tg:
        if gen == UNKNOWN:
            if require_known:
                return False
        elif gen != tg:
            return False
    return True


def summarize(demos) -> dict:
    """Sayım: toplam / bilinen / unknown / cinsiyet & yaş dağılımı (loglamak için)."""
    total = len(demos)
    known = sum(1 for d in demos if is_known(d))
    by_g = {"female": 0, "male": 0, "unknown": 0}
    by_a = {}
    for d in demos:
        by_g[d.get("gender", UNKNOWN)] = by_g.get(d.get("gender", UNKNOWN), 0) + 1
        a = d.get("age", UNKNOWN)
        by_a[a] = by_a.get(a, 0) + 1
    return {"total": total, "known": known, "unknown": total - known, "by_gender": by_g, "by_age": by_a}


# ============================== AD-CENTER OKUYUCU (best-effort, async) ==============================
_AGE_NEAR = re.compile(r"(?:ya[şs]|age)[^0-9]{0,20}(\d{2})\s*[-–—]\s*(\d{2})", re.I)
_AGE_PLUS = re.compile(r"(?:ya[şs]|age)[^0-9]{0,20}(65)\s*\+", re.I)
_GEN_TR = re.compile(r"cinsiyet[^A-Za-zçğıöşü]{0,20}(kad[ıi]n|erkek)", re.I)
_GEN_EN = re.compile(r"gender[^A-Za-z]{0,20}(female|male|woman|man)", re.I)


async def read_demographic_via_adcenter(page, log=None) -> dict:
    """Google Ad Center / Ad Settings'ten yaş+cinsiyeti BEST-EFFORT okur. Başarısız → unknown.
    Sağlam yol değil (Google SPA'sı değişir) — asıl yol operatör-etiketi; bu bir kolaylık."""
    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass
    urls = [
        "https://myadcenter.google.com/controls?hl=tr",
        "https://adssettings.google.com/authenticated?hl=tr",
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            continue
        # consent/interstitial
        for sel in ("#L2AGLb", "button:has-text('Kabul et')", "button:has-text('Accept all')"):
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click(timeout=2500)
                    await page.wait_for_timeout(800)
            except Exception:
                pass
        try:
            await page.wait_for_timeout(2500)
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            text = ""
        if not text:
            continue
        age = UNKNOWN
        gender = UNKNOWN
        m = _AGE_NEAR.search(text) or None
        if m:
            age = normalize_age(f"{m.group(1)}-{m.group(2)}")
        elif _AGE_PLUS.search(text):
            age = "65+"
        gm = _GEN_TR.search(text) or _GEN_EN.search(text)
        if gm:
            gender = normalize_gender(gm.group(1))
        demo = normalize_demo(age if age != UNKNOWN else None,
                              gender if gender != UNKNOWN else None, "adcenter")
        if is_known(demo):
            _log(f"   demografi okundu: {demo_label(demo)} ({url.split('//')[1].split('/')[0]})")
            return demo
    _log("   demografi okunamadı → unknown")
    return normalize_demo(source="adcenter")
