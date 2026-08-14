"""
Clicker çekirdeği — adswhite.py'nin (bug'ları düzeltilmiş) tık mantığını sunucu-tarafı
HEADLESS çalıştırır. GUI (PySide6/matplotlib) YOK. Tek fark/seam: tarayıcı context'i
SADQ'nun undetect fingerprint_service'i ile, çerezin DOĞDUĞU fingerprint'ten kurulur
(birth=use) → Google fingerprint-mismatch görmez, oturum pasife düşmez.

PORT VERBATIM (dokunulmadı): _parse_proxy, is_white_url, google_search_behavior,
handle_captcha, solve_recaptcha_with_capsolver, human_type, random_mouse_movements,
random_scroll, safe_goto.
ADAPT: visit_site (context seam), worker pool (asyncio, classic-headless).
"""
import os
import time
import json
import glob
import math
import random
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse, quote_plus

from fingerprint_service import FingerprintService, BrowserFingerprint
import demographics as demo_mod
from click_history import ClickLedger

logger = logging.getLogger("clicker_core")
_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "click_history.json")

# Sunucu paylaşımlı (SADQ ile aynı makine) → sert eşzamanlılık tavanı (OOM koruması).
MAX_CONCURRENCY = int(os.environ.get("CLICKER_MAX_CONCURRENCY", "12"))

# Yedek UA havuzu — SADECE çerez dosyasında fingerprint/UA YOKSA kullanılır (Android/Chromium).
# ⚠️ Yalnız UA'sız çerez için FALLBACK. BAYAT UA = tell → güncel tut. Son güncelleme 2026-08-14 (stabil=152).
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 15; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; 2211133G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 15; CPH2449) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36",
]

TURKISH_CITIES = [
    ("Adana", 37.0000, 35.3213), ("Adıyaman", 37.7648, 38.2786), ("Afyonkarahisar", 38.7507, 30.5567),
    ("Ağrı", 39.7191, 43.0503), ("Amasya", 40.6499, 35.8353), ("Ankara", 39.9208, 32.8541),
    ("Antalya", 36.8969, 30.7133), ("Artvin", 41.1828, 41.5149), ("Aydın", 37.8560, 27.8416),
    ("Balıkesir", 39.6484, 27.8826), ("Bilecik", 40.1426, 29.9793), ("Bingöl", 38.8847, 40.4986),
    ("Bitlis", 38.4011, 42.1078), ("Bolu", 40.7392, 31.6094), ("Burdur", 37.7203, 30.2908),
    ("Bursa", 40.1950, 29.0600), ("Çanakkale", 40.1553, 26.4142), ("Çankırı", 40.6013, 33.6134),
    ("Çorum", 40.5499, 34.9533), ("Denizli", 37.7765, 29.0864), ("Diyarbakır", 37.9144, 40.2306),
    ("Edirne", 41.6764, 26.5559), ("Elazığ", 38.6810, 39.2264), ("Erzincan", 39.7464, 39.4914),
    ("Erzurum", 39.9043, 41.2679), ("Eskişehir", 39.7767, 30.5206), ("Gaziantep", 37.0662, 37.3833),
    ("Giresun", 40.9128, 38.3895), ("Gümüşhane", 40.4386, 39.5086), ("Hakkari", 37.5744, 43.7408),
    ("Hatay", 36.4018, 36.3498), ("Isparta", 37.7648, 30.5566), ("Mersin", 36.8121, 34.6415),
    ("İstanbul", 41.0082, 28.9784), ("İzmir", 38.4237, 27.1428), ("Kars", 40.6013, 43.0975),
    ("Kastamonu", 41.3887, 33.7827), ("Kayseri", 38.7312, 35.4787), ("Kırklareli", 41.7333, 27.2167),
    ("Kırşehir", 39.1425, 34.1709), ("Kocaeli", 40.8533, 29.8815), ("Konya", 37.8746, 32.4932),
    ("Kütahya", 39.4242, 29.9833), ("Malatya", 38.3552, 38.3095), ("Manisa", 38.6191, 27.4289),
    ("Kahramanmaraş", 37.5858, 36.6372), ("Mardin", 37.3212, 40.7245), ("Muğla", 37.2141, 28.3636),
    ("Muş", 38.7432, 41.5065), ("Nevşehir", 38.6939, 34.6857), ("Niğde", 37.9667, 34.6833),
    ("Ordu", 40.9839, 37.8777), ("Rize", 41.0201, 40.5234), ("Sakarya", 40.7569, 30.3781),
    ("Samsun", 41.2867, 36.3300), ("Siirt", 37.9333, 41.9500), ("Sinop", 42.0231, 35.1531),
    ("Sivas", 39.7477, 37.0179), ("Tekirdağ", 40.9833, 27.5167), ("Tokat", 40.3167, 36.5500),
    ("Trabzon", 41.0015, 39.7178), ("Tunceli", 39.1079, 39.5401), ("Şanlıurfa", 37.1674, 38.7955),
    ("Uşak", 38.6823, 29.4082), ("Van", 38.4942, 43.3800), ("Yozgat", 39.8181, 34.8147),
    ("Zonguldak", 41.4564, 31.7987), ("Aksaray", 38.3687, 34.0370), ("Bayburt", 40.2552, 40.2249),
    ("Karaman", 37.1759, 33.2287), ("Kırıkkale", 39.8468, 33.5153), ("Batman", 37.8812, 41.1351),
    ("Şırnak", 37.5189, 42.4537), ("Bartın", 41.6358, 32.3375), ("Ardahan", 41.1105, 42.7022),
    ("Iğdır", 39.9237, 44.0450), ("Yalova", 40.6500, 29.2667), ("Karabük", 41.2061, 32.6204),
    ("Kilis", 36.7184, 37.1212), ("Osmaniye", 37.0742, 36.2478), ("Düzce", 40.8438, 31.1565),
]


# ============================== VERİ MODELLERİ ==============================
@dataclass
class JobConfig:
    keyword: str
    target_url: str = ""
    single_target: bool = False
    white_urls: list = field(default_factory=list)
    capsolver_api: str = ""
    location: str = "Rastgele (Tüm Türkiye)"
    total_visits: int = 50
    concurrency: int = 3
    cookie_source: str = "auto"   # 'auto' (SADQ klasörü) | 'upload'
    think_time: int = 20          # ziyaretler arası ortalama saniye (log-normal; temporal burst'ü yayar)
    # DEMOGRAFİ hedefleme: rakip kampanyanın hedef segmenti. Boş → filtre yok (herkes uygun).
    # Doluysa: hedef yaş kovaları içinde OLMAYAN veya cinsiyeti tutmayan hesap ELENİR; hedeflenen
    # boyutta 'unknown' olan hesap da ELENİR (mobil SERP'te demografik reklam görünmez → tık boşa).
    target_age: list = field(default_factory=list)   # ör. ["25-34","35-44"]; boş = kapalı
    target_gender: str = ""                            # 'female' | 'male' | '' (kapalı)
    # SIVT AGREGAT tavanları (runlar arası KALICI defter — click_history.json). Google offline
    # katmanı ~60 günü tarar; yüksek hesap/IP velocity + tekrar-yolculuk geç iade tetikler.
    # Düşük-ve-yavaş > hacim: kotalar volume'ü sınırlar AMA tutulan (iadesiz) tık oranını yükseltir.
    max_clicks_per_account_day: int = 5   # 0 = sınırsız (önerilmez)
    max_clicks_per_ip_day: int = 15       # tek proxy → tüm hesaplar bu IP'yi paylaşır; düşük tut
    target_cooldown_days: int = 2         # aynı hesap aynı rakibi bu kadar gün tekrar tıklamasın


class Stats:
    def __init__(self):
        self.success = 0
        self.fail = 0
        self.total_visits_done = 0

    def snapshot(self) -> dict:
        return {"success": self.success, "fail": self.fail, "total": self.total_visits_done}


# ============================== HELPERS (PORT VERBATIM) ==============================
def _parse_proxy(proxy_line):
    """Esnek proxy ayrıştırıcı. host:port | host:port:user:pass | user:pass@host:port |
    scheme://... | IPv6 (bracket + bare). Parse edilemezse None (fail-closed sinyali)."""
    s = (proxy_line or "").strip()
    if not s:
        return None
    try:
        if "://" in s or "@" in s:
            if "://" not in s:
                s = "http://" + s
            u = urlparse(s)
            if not u.hostname or not u.port:
                return None
            scheme = u.scheme if u.scheme in ("http", "https", "socks5", "socks5h") else "http"
            host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
            d = {"server": f"{scheme}://{host}:{u.port}"}
            if u.username:
                d["username"] = u.username
            if u.password:
                d["password"] = u.password
            return d
        if s.startswith("["):
            host_part, _, rest = s[1:].partition("]")
            bits = rest.lstrip(":").split(":")
            if bits and bits[0]:
                d = {"server": f"http://[{host_part}]:{bits[0]}"}
                if len(bits) >= 3:
                    d["username"], d["password"] = bits[1], bits[2]
                return d
            return None
        parts = s.split(":")
        if len(parts) == 2:
            return {"server": f"http://{parts[0]}:{parts[1]}"}
        if len(parts) == 4:
            host, port, user, pw = parts
            return {"server": f"http://{host}:{port}", "username": user, "password": pw}
        if len(parts) > 4 and parts[-1].isdigit():
            return {"server": f"http://[{':'.join(parts[:-1])}]:{parts[-1]}"}
        return None
    except Exception:
        return None


def is_white_url(url, white_urls):
    """URL beyaz listede mi (kendi-link koruması). Sınır-kontrollü domain eşleşmesi."""
    if not white_urls:
        return False
    try:
        # Çıplak host ('example.com') gelirse netloc boş kalır → şema ekleyip normalize et.
        u = url if '://' in url else 'https://' + url
        parsed = urlparse(u)
        url_domain = parsed.netloc.replace('www.', '').lower()
        url_path = parsed.path.lower()
    except Exception:
        return False
    for white_url in white_urls:
        w = white_url.strip().lower()
        if not w:
            continue
        # Wildcard toleransı: "*.domain.com" ve "domain.com/*" (ve "https://domain.com/*")
        # → domain + TÜM alt-alan + TÜM path. Çıplak "domain.com" da aynı sonucu verir.
        if w.startswith('*.'):
            w = w[2:]
        try:
            white_parsed = urlparse(w if w.startswith('http') else f'https://{w}')
            white_domain = white_parsed.netloc.replace('www.', '').lower()
            white_path = white_parsed.path.lower().rstrip('*')   # "/*" → "/", "/x*" → "/x"
            if white_path == '/':
                white_path = ''
            if url_domain == white_domain or url_domain.endswith('.' + white_domain):
                if not white_path or url_path.startswith(white_path):
                    return True
        except Exception:
            if w in url.lower():
                return True
    return False


def generate_geolocation_js(lat, lon):
    return f"""
    (() => {{
        const lat = {lat};
        const lon = {lon};
        if (navigator.geolocation) {{
            navigator.geolocation.getCurrentPosition = function(success, error, options) {{
                success({{ coords: {{ latitude: lat, longitude: lon, accuracy: 100,
                    altitude: null, altitudeAccuracy: null, heading: null, speed: null }},
                    timestamp: Date.now() }});
            }};
            navigator.geolocation.watchPosition = navigator.geolocation.getCurrentPosition;
        }}
    }})();
    """


async def human_type(page, selector, text):
    for char in text:
        await page.type(selector, char, delay=random.uniform(30, 80))


async def random_mouse_movements(page):
    try:
        viewport = page.viewport_size
        if viewport:
            for _ in range(random.randint(2, 4)):
                x = random.randint(0, max(1, viewport["width"] - 100))
                y = random.randint(0, max(1, viewport["height"] - 100))
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.05, 0.2))
    except Exception:
        pass


async def random_scroll(page):
    try:
        for _ in range(random.randint(1, 3)):
            await page.evaluate(f"window.scrollBy(0, {random.choice([200, 300, 400]) * random.choice([-1, 1])})")
            await asyncio.sleep(random.uniform(0.2, 0.8))
    except Exception:
        pass


# ============================== DAVRANIŞ GERÇEKÇİLİĞİ (Faz 4) ==============================
def _lognorm(median: float, sigma: float = 0.5, lo: float = 0.0, hi: float = 1e9) -> float:
    """İnsan-benzeri log-normal gecikme (uniform yerine → düz-histogram tell'ini kapatır)."""
    v = median * math.exp(random.gauss(0, sigma))
    return max(lo, min(hi, v))


async def human_touch_scroll(page, downs=None):
    """Kaydırma — çoğu aşağı, değişken mesafe/hız, kademeli (mobil okuma davranışı)."""
    try:
        n = downs if downs is not None else random.randint(1, 3)
        for _ in range(n):
            dist = random.randint(180, 420) * (1 if random.random() < 0.85 else -1)
            steps = random.randint(6, 12)
            await page.evaluate(
                """([dy,steps]) => new Promise(res => {
                    let i=0;
                    const step=()=>{ window.scrollBy(0, dy/steps); if(++i<steps){ setTimeout(step, 12+Math.random()*20);} else res(); };
                    step();
                })""",
                [dist, steps],
            )
            await asyncio.sleep(_lognorm(0.5, 0.5, 0.2, 2.0))
    except Exception:
        pass


def _diurnal_mult():
    """İnsan sirkadiyen ritmi → tık hızı çarpanı. Gece yavaş, yoğun saatler normal. Uniform 24/7
    metronom (SIVT'nin en zor gizlenen temporal tell'i) kırılır. (IVT araştırması: 'never a metronome')"""
    h = time.localtime().tm_hour
    if 1 <= h < 7:
        return 2.8          # gece derin uyku → çok az tık
    if h == 0 or h == 23:
        return 1.9          # gece geç
    if 7 <= h < 9:
        return 1.5          # sabah yavaş
    if (12 <= h < 14) or (19 <= h < 22):
        return 0.9          # yoğun saatler (biraz daha sık normal)
    return 1.0


_LANDING_SKIP = ("facebook.", "instagram.", "twitter.", "x.com", "youtube.", "wa.me", "whatsapp",
                 "t.me", "telegram", "linkedin.", "pinterest.", "tiktok.", "logout", "signout",
                 "sign-out", "cikis", "çıkış", "/login", "/signin")


async def _landing_engage(landing, log, task_id):
    """Landing'de GERÇEKÇİ, AĞIR-KUYRUKLU engagement — bounce DEĞİL, sabit-dwell DEĞİL. MOBİL TOUCH
    (masaüstü mouse DEĞİL → cihaz uyumsuzluğu olurdu). Bazen input focus (pasif sinyal), bazen AYNI
    host'ta 2. iç sayfa (session derinliği). Post-click en güçlü IVT/iade sinyalini kapatır."""
    try:
        host = ""
        try:
            host = (landing.url or "").split("//")[-1].split("/")[0].replace("www.", "").lower()
        except Exception:
            host = ""
        # 1) ilk okuma — ağır kuyruk (çoğu 8-30s, nadiren çok kısa/çok uzun; asla 0s bounce)
        await asyncio.sleep(_lognorm(9, 0.75, 2.5, 55))
        await human_touch_scroll(landing, downs=random.randint(2, 6))
        await asyncio.sleep(_lognorm(6, 0.7, 1.5, 40))
        # 2) bazen bir input'a dokunup odaklan (scroll/focus/pasif etkileşim skorlanır)
        if random.random() < 0.30:
            try:
                el = await landing.query_selector("input:not([type=hidden]):not([type=submit]), textarea, [contenteditable=true]")
                if el and await el.is_visible():
                    await el.scroll_into_view_if_needed()
                    b = await el.bounding_box()
                    if b and b.get("width"):
                        await landing.touchscreen.tap(b["x"] + b["width"] * 0.5, b["y"] + b["height"] * 0.5)
                        await asyncio.sleep(_lognorm(1.6, 0.5, 0.5, 6))
            except Exception:
                pass
        # 3) bazen AYNI reklamveren host'unda 2. sayfaya geç (harici/sosyal/logout DEĞİL) → derinlik
        if host and random.random() < 0.5:
            try:
                links = await landing.query_selector_all("a[href]")
                cand = []
                for a in links[:80]:
                    try:
                        href = (await a.get_attribute("href") or "").strip()
                    except Exception:
                        continue
                    if not href or href[0] == "#" or href.startswith(("mailto:", "tel:", "javascript:")):
                        continue
                    hl = href.lower()
                    if any(s in hl for s in _LANDING_SKIP):
                        continue
                    # AYNI host: göreli VEYA hostname eşleşmesi (substring DEĞİL → 'host.evil.com' kaçağı yok: #11)
                    # '//host' protokol-göreli MUTLAK'tır → göreli sayma, hostname kontrolüne düşür (#6).
                    same = href.startswith("/") and not href.startswith("//")
                    if not same and host:
                        hn = (urlparse(href).hostname or "").replace("www.", "").lower()
                        same = bool(hn) and (hn == host or hn.endswith("." + host))
                    if same:
                        try:
                            if await a.is_visible():
                                cand.append(a)
                        except Exception:
                            pass
                    if len(cand) >= 12:
                        break
                if cand:
                    a = random.choice(cand)
                    try:
                        await a.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    b = await a.bounding_box()
                    if b and b.get("width"):
                        lctx = landing.context
                        pg_before = set(lctx.pages)
                        before2 = landing.url or ""
                        await landing.touchscreen.tap(b["x"] + b["width"] * random.uniform(0.4, 0.6),
                                                      b["y"] + b["height"] * random.uniform(0.4, 0.6))
                        # Yeni sekme (target=_blank) mı, same-tab nav mı? ~3s poll (#10 sekme sızıntısı).
                        second = None
                        for _ in range(15):
                            await asyncio.sleep(0.2)
                            np = next((p for p in lctx.pages if p not in pg_before), None)
                            if np is not None:
                                second = np
                                break
                            if (landing.url or "") != before2:
                                second = landing
                                break
                        target = second or landing
                        try:
                            await target.wait_for_load_state("domcontentloaded", timeout=12000)
                        except Exception:
                            pass
                        cur2 = (urlparse(target.url or "").hostname or "").replace("www.", "").lower()
                        if host and (cur2 == host or cur2.endswith("." + host)):   # hâlâ reklamverende
                            log(f"   ↪ (Bot {task_id}) 2. sayfa gezildi → session derinliği")
                            await asyncio.sleep(_lognorm(7, 0.7, 2, 45))
                            await human_touch_scroll(target, downs=random.randint(1, 4))
                            await asyncio.sleep(_lognorm(4, 0.6, 1, 25))
                        # pg_before'DAN BERİ açılan TÜM yeni sekmeleri kapat (yavaş >3s açılan da: #13).
                        for p in list(lctx.pages):
                            if p not in pg_before and p is not landing:
                                try:
                                    await p.close()
                                except Exception:
                                    pass
            except Exception:
                pass
    except Exception:
        pass


async def _tap(page, element):
    """Elemanı DOKUNARAK tıkla → mobil PointerEvent(touch). OCCLUSION kontrolü: o noktada gerçekten
    reklam anchor'ı mı (overlay/consent tap'i yutmasın: #19). Fallback: element.click()."""
    try:
        box = await element.bounding_box()
        if box and box.get("width") and box.get("height"):
            cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
            cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)
            try:
                hit = await page.evaluate(
                    """([x,y]) => { const el = document.elementFromPoint(x,y);
                        return !!(el && el.closest && el.closest('a[data-pcu]')); }""",
                    [cx, cy],
                )
            except Exception:
                hit = True
            if not hit:
                return False   # nokta reklam DEĞİL (overlay) → çağıran diğer rakibe geçsin
            await page.touchscreen.tap(cx, cy)
            return True
    except Exception:
        pass
    try:
        await element.click()
        return True
    except Exception:
        return False


async def serp_dwell(page):
    """SERP'te gerçekçi okuma: değişken dwell + kaydırma (anında-tıklama tell'ini kapatır)."""
    await asyncio.sleep(_lognorm(1.6, 0.5, 0.6, 6.0))
    await human_touch_scroll(page, downs=random.randint(1, 3))
    await asyncio.sleep(_lognorm(1.2, 0.6, 0.4, 5.0))
    if random.random() < 0.35:
        try:
            await page.evaluate("window.scrollBy(0, -%d)" % random.randint(120, 300))
        except Exception:
            pass
        await asyncio.sleep(_lognorm(0.8, 0.5, 0.3, 3.0))


async def _dismiss_consent(page):
    """Google consent/çerez ekranını kabul et — giriş yapılmışsa nadir; yine de garanti (#22)."""
    try:
        for sel in ('#L2AGLb', 'button[aria-label*="Kabul"]', 'button[aria-label*="Accept"]',
                    'form[action*="consent"] button', 'button:has-text("Tümünü kabul")',
                    'button:has-text("Accept all")', 'button:has-text("Kabul et")'):
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def safe_goto(page, url, max_retries=3, timeout=30000):
    for attempt in range(max_retries):
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)   # hafif — boşa 15s bekleme (#28)
            except Exception:
                pass
            return True
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(random.uniform(1, 3))
            continue
    return False


# ============================== CAPTCHA (PORT VERBATIM) ==============================
async def solve_recaptcha_with_capsolver(api_key, website_url, website_key, log_callback, task_id, proxy=None):
    import aiohttp  # lazy: yalnız captcha çözümünde gerekli (import-zamanı sert bağımlılık yok)
    if not api_key:
        log_callback(f"❌ (Bot {task_id}) CapSolver API Key girilmedi! Captcha aşılamıyor.")
        return False
    log_callback(f"🤖 (Bot {task_id}) CapSolver'a reCAPTCHA görevi gönderiliyor...")
    create_task_url = "https://api.capsolver.com/createTask"
    get_result_url = "https://api.capsolver.com/getTaskResult"
    # PROXY-BOUND task (#21): token OTURUM proxy'sinden çözülsün (IP uyuşmazlığı Google'da reddedilir).
    task = {"type": "ReCaptchaV2TaskProxyLess", "websiteURL": website_url, "websiteKey": website_key}
    if proxy and isinstance(proxy, dict) and proxy.get("server"):
        try:
            srv = proxy["server"]
            scheme = srv.split("://")[0] if "://" in srv else "http"
            rest = srv.split("://")[-1]
            if rest.startswith("["):
                host = rest[1:].split("]")[0]
                port = rest.split("]:")[-1]
            else:
                host, port = rest.rsplit(":", 1)
            task = {"type": "ReCaptchaV2Task", "websiteURL": website_url, "websiteKey": website_key,
                    "proxyType": "socks5" if "socks5" in scheme else "http",
                    "proxyAddress": host, "proxyPort": int(port)}
            if proxy.get("username"):
                task["proxyLogin"] = proxy["username"]
            if proxy.get("password"):
                task["proxyPassword"] = proxy["password"]
        except Exception:
            task = {"type": "ReCaptchaV2TaskProxyLess", "websiteURL": website_url, "websiteKey": website_key}
    payload = {"clientKey": api_key, "task": task}
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(create_task_url, json=payload) as resp:
                result = await resp.json()
            if result.get("errorId"):
                log_callback(f"❌ (Bot {task_id}) CapSolver Hatası: {result.get('errorDescription')}")
                return False
            task_id_cs = result.get("taskId")
            log_callback(f"⏳ (Bot {task_id}) CapSolver görevi oluşturuldu, çözülmesi bekleniyor...")
            for _ in range(60):
                await asyncio.sleep(3)
                async with session.post(get_result_url, json={"clientKey": api_key, "taskId": task_id_cs}) as res:
                    res_result = await res.json()
                if res_result.get("errorId"):
                    log_callback(f"❌ (Bot {task_id}) CapSolver Sonuç Hatası: {res_result.get('errorDescription')}")
                    return False
                if res_result.get("status") == "ready":
                    token = res_result.get("solution", {}).get("gRecaptchaResponse")
                    log_callback(f"✅ (Bot {task_id}) Captcha çözüldü! Token alındı.")
                    return token
            log_callback(f"⌛ (Bot {task_id}) CapSolver zaman aşımına uğradı.")
            return False
    except Exception as e:
        log_callback(f"❌ (Bot {task_id}) CapSolver Bağlantı Hatası: {str(e)[:60]}")
        return False


async def handle_captcha(page, api_key, log_callback, task_id, proxy=None):
    if "sorry/index" in page.url or "google.com/sorry" in page.url:
        log_callback(f"🛑 (Bot {task_id}) Google Captcha (sorry) ekranı tespit edildi!")
        sitekey = await page.evaluate("""() => {
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');
            const scripts = document.querySelectorAll('script[src*="recaptcha"]');
            for (const s of scripts) { const m = s.src.match(/[?&]render=([^&]+)/); if (m) return m[1]; }
            return null;
        }""")
        if not sitekey:
            log_callback(f"⚠️ (Bot {task_id}) reCAPTCHA sitekey bulunamadı!")
            return False
        token = await solve_recaptcha_with_capsolver(api_key, page.url, sitekey, log_callback, task_id, proxy=proxy)
        if not token:
            return False
        try:
            await page.evaluate("""(token) => {
                let t = document.getElementById('g-recaptcha-response')
                    || document.querySelector('textarea[name="g-recaptcha-response"]');
                if (t) { t.style.display = 'block'; t.value = token; t.innerHTML = token; }
            }""", token)
            try:
                await page.click('input[type="submit"]', timeout=2000)
            except Exception:
                await page.evaluate("() => { const f = document.getElementById('captcha-form'); if (f) f.submit(); }")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(2)
            if "sorry/index" not in page.url:
                log_callback(f"✅ (Bot {task_id}) Captcha başarıyla aşıldı!")
                return True
            log_callback(f"❌ (Bot {task_id}) Captcha geçilemedi.")
            return False
        except Exception as e:
            log_callback(f"❌ (Bot {task_id}) Token enjekte hatası: {str(e)[:50]}")
            return False
    return True


# ============================== TIK MANTIĞI (PORT VERBATIM) ==============================
async def google_search_behavior(page, task_id, log_callback, target_domain, white_urls, single_target=False):
    """KELİME-ONLY (varsayılan): whitelist DIŞI ilk RAKİP reklama tıklar; kendi/whitelist linke DOKUNMAZ.
    TEK HEDEF (single_target=True): sadece target_domain reklamına tıklar."""
    try:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(1.5, 2.5))
        except Exception:
            pass

        async def _ad_domain(al):
            # data-pcu BİRDEN FAZLA (boşlukla ayrık) URL içerebilir → İLK'ini al.
            for attr in ('data-pcu', 'href'):
                try:
                    raw = await al.get_attribute(attr)
                except Exception:
                    continue
                if not raw or not raw.strip():
                    continue
                first = raw.split()[0]
                u = first if '://' in first else 'https://' + first
                dom = urlparse(u).netloc.replace('www.', '').lower()
                if dom:
                    return dom, first
            return "", ""

        async def _click(al, why):
            try:
                if not await al.is_visible():
                    return False
                await al.scroll_into_view_if_needed()
                # Headful: sekmeyi öne getir — arka-plan/gizli sekme tap'i IVT ile geçersiz (#5)
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                await asyncio.sleep(_lognorm(0.7, 0.5, 0.3, 2.5))   # reklama bakma
                before_url = page.url
                ctx = page.context
                pages_before = set(ctx.pages)
                if not await _tap(page, al):     # tap ıskalarsa çağıran diğer rakibe geçer
                    return False
                # Navigasyon (same-tab) VEYA popup (yeni sekme) — ikisini de yakala (#3 + #27).
                # YAVAŞ açılan popup/nav ~5s'ye kadar POLL edilir (sabit 0.8s'de gerçek tık discard olurdu: #5).
                landing = page
                for _ in range(25):     # 25 × 0.2s ≈ 5s
                    await asyncio.sleep(0.2)
                    newp = next((p for p in ctx.pages if p not in pages_before), None)
                    if newp is not None:
                        landing = newp
                        break
                    if (page.url or "") != before_url:   # same-tab navigasyon başladı
                        break
                # Yeni sekme about:blank iken açıldıysa gerçek URL'e geçmesini bekle (aksi halde
                # 'about:' landed=False → gerçek tık discard: #7).
                if landing is not page:
                    for _ in range(20):    # ~4s
                        u = landing.url or ""
                        if u and not u.startswith("about:"):
                            break
                        await asyncio.sleep(0.2)
                try:
                    await landing.wait_for_load_state("domcontentloaded", timeout=12000)
                except Exception:
                    pass
                await asyncio.sleep(1.0)
                cur = landing.url or ""
                host = cur.split("//")[-1].split("/")[0] if "//" in cur else ""
                # BAŞARI DOĞRULAMASI: url SERP/about:blank/hata/sorry/google DIŞINA çıktı = GERÇEK tık.
                # ('/search' KALDIRILDI: Google SERP zaten 'google.' host ile eleniyor; bare '/search'
                #  reklamverenin arama-sayfasını (etsy.com/search) yanlışça GEÇERSİZ sayıyordu — Tur4.)
                landed = (bool(cur) and not cur.startswith("about:")
                          and "chrome-error" not in cur and "sorry" not in cur
                          and (landing is not page or cur != before_url)
                          and "google." not in host)
                if not landed:
                    log_callback(f"⚠️ (Bot {task_id}) navigasyon YOK/SERP'te kaldı — GEÇERSİZ tık ({why})")
                    if landing is not page:
                        try:
                            await landing.close()
                        except Exception:
                            pass
                    elif (page.url or "") != before_url:
                        # same-tab başka yere gitti (ör. ara-sayfa) → SERP'i GERİ YÜKLE ki retry bayat
                        # handle kullanmasın (#12). goto(before_url) → çok-hop redirect'te go_back'ten
                        # daha güvenilir (#14: tek go_back SERP'e dönmeyebilir).
                        try:
                            await page.goto(before_url, wait_until="domcontentloaded", timeout=8000)
                        except Exception:
                            pass
                    return False
                log_callback(f"🎯 GERÇEK TIK ({why}) → {cur[:55]} (Bot {task_id})")
                try:
                    await landing.bring_to_front()
                except Exception:
                    pass
                # Landing'de DERİN, ağır-kuyruklu engagement (post-click iade sinyalini kapatır:
                # dwell dağılımı + touch scroll + input focus + bazen 2. iç sayfa) — IVT sertleştirme
                await _landing_engage(landing, log_callback, task_id)
                if landing is not page:   # popup ise kapat → SERP page'e dön
                    try:
                        await landing.close()
                    except Exception:
                        pass
                return True
            except Exception as e:
                log_callback(f"❌ Reklam tıklama hatası (Bot {task_id}): {str(e)[:50]}")
                return False

        ad_links = await page.query_selector_all('a[data-pcu]')
        if not ad_links:
            log_callback(f"❌ Sponsor reklam bulunamadı (proxy lokasyonu uygun olmayabilir) (Bot {task_id})")
            return False

        # SERP'te gerçekçi okuma davranışı (anında-tıklama IVT imzasını kapatır)
        await serp_dwell(page)

        if single_target and target_domain:
            td = target_domain.lower()
            for al in ad_links:
                dom, url = await _ad_domain(al)
                if dom and (dom == td or dom.endswith('.' + td)):
                    if is_white_url(dom, white_urls) or (url and is_white_url(url, white_urls)):
                        log_callback(f"🚫 (Bot {task_id}) Hedef whitelist'te — TIKLAMA İPTAL")
                        return "__wl_skip__"    # #16: fail DEĞİL (karantina/devre-kesici sürüklemesin)
                    if await _click(al, f"tek-hedef: {dom}"):
                        return dom
            log_callback(f"❌ Hedef domain reklamı bulunamadı (Bot {task_id})")
            return ""

        # KELİME-ONLY: whitelist DIŞI rakipleri topla, İLK'i HER ZAMAN değil — üste ağırlıklı
        # rastgele seç (hep-birinci-reklam IVT desenini kırar).
        competitors = []
        for al in ad_links:
            dom, url = await _ad_domain(al)
            if not dom:
                continue
            if is_white_url(dom, white_urls) or (url and is_white_url(url, white_urls)):
                log_callback(f"🛡️ (Bot {task_id}) KENDİ/beyaz link — ATLANDI (muaf): {dom}")
                continue
            competitors.append((al, dom))
        if not competitors:
            log_callback(f"❌ Tıklanacak (whitelist dışı) sponsorlu reklam yok (Bot {task_id})")
            return ""
        # Üst-ağırlıklı primary seç; İLK ıskalarsa DİĞER rakiplere geç (geçerli tık kaybı: #20)
        primary = min(len(competitors) - 1, int(abs(random.gauss(0, 1.2))))
        order = [primary] + [i for i in range(len(competitors)) if i != primary]
        comp_domains = [d for _, d in competitors]

        async def _fresh_handle(dom):
            """SERP navigasyonundan sonra handle BAYAT olabilir → domaine göre YENİDEN sorgula (#12)."""
            try:
                for al2 in await page.query_selector_all('a[data-pcu]'):
                    d2, u2 = await _ad_domain(al2)
                    if d2 == dom and not (is_white_url(d2, white_urls) or (u2 and is_white_url(u2, white_urls))):
                        return al2
            except Exception:
                pass
            return None

        for i in order:
            dom = comp_domains[i]
            fresh = await _fresh_handle(dom)
            if fresh is None:
                continue
            if await _click(fresh, f"rakip #{i + 1}: {dom}"):
                return dom
        log_callback(f"❌ Hiçbir rakip reklam GEÇERLİ tıklanamadı (Bot {task_id})")
        return ""
    except Exception as e:
        log_callback(f"⚠️ Reklam arama hatası (Bot {task_id}): {str(e)[:50]}")
        return ""


# ============================== ÇEREZ / FINGERPRINT (SADQ'dan) ==============================
def _sanitize_cookies(cookies):
    """add_cookies patlamasın: sameSite=None → secure=True; geçersiz sameSite düşürülür;
    name/domain zorunlu (tek bozuk çerez TÜM batch'i reddeder)."""
    out = []
    for c in cookies or []:
        ss = c.get("sameSite")
        if ss not in ("Strict", "Lax", "None"):
            ss = None
        ck = {k: c[k] for k in ("name", "value", "domain", "path") if c.get(k) is not None}
        exp = c.get("expires", c.get("expirationDate"))
        if isinstance(exp, (int, float)) and exp > 0:
            ck["expires"] = float(exp)
        ck["httpOnly"] = bool(c.get("httpOnly", False))
        ck["secure"] = bool(c.get("secure", False))
        if ss:
            if ss == "None":
                ck["secure"] = True
            ck["sameSite"] = ss
        if ck.get("name") and ck.get("domain"):
            out.append(ck)
    return out


def _fp_from_stored(fp):
    """Saklı fingerprint dict'inden BrowserFingerprint kur → stealth + Client Hints birebir
    uygulanır. YENİDEN üretme YOK (birth match bozulur, oturum ölür)."""
    import re
    ua = (fp or {}).get("user_agent", "") or ""
    cver = (re.search(r"Chrome/(\d+)", ua) or [None, "152"])[1] if "Chrome/" in ua else "152"
    mm = re.search(r"Android \d+; ([^)]+)\)", ua)
    av = re.search(r"Android (\d+)", ua)
    fp = fp or {}
    return BrowserFingerprint(
        user_agent=ua or random.choice(USER_AGENTS),
        viewport=fp.get("viewport") or {"width": 390, "height": 844},
        hardware_concurrency=fp.get("hardware_concurrency", 8),
        device_memory=min(8, fp.get("device_memory", 8) or 8),   # deviceMemory tavanı 8
        device_scale_factor=fp.get("device_scale_factor", 3.0),
        is_mobile=bool(fp.get("is_mobile", True)),
        has_touch=bool(fp.get("has_touch", True)),
        platform=fp.get("platform", "Linux armv8l"),
        gpu_vendor=fp.get("webgl_vendor", "Qualcomm"),
        gpu_renderer=fp.get("webgl_renderer", "Adreno (TM) 740"),
        device_name=fp.get("device", ""),
        locale=fp.get("locale", "tr-TR"),
        timezone_id=fp.get("timezone_id", "Europe/Istanbul"),
        model=fp.get("model") or (mm.group(1).strip() if mm else "SM-S911B"),
        os_version=fp.get("os_version") or (av.group(1) if av else "14"),
        browser_version=str(cver),
        canvas_noise=int(fp.get("canvas_noise", 1) or 1),
        noise_seed=int(fp.get("noise_seed", 0) or 0),   # per-profil de-korelasyon (crack #1)
    )


def _demo_label_of(path):
    """Bir çerezin demografi etiketi (K·25-34) — worker timeout/exception satırlarında kullanılır."""
    try:
        return demo_mod.demo_label((load_profile(path) or {}).get("demographic"))
    except Exception:
        return ""


def load_profile(path):
    """Çerez dosyasını yükle. İKİ formatı da anlar:
      - adswhite export: {user_agent, fingerprint, proxy, cookies:[...]}
      - ham SADQ profili: {fingerprint, storage_state:{cookies:[...]}, proxy_ip}
    Döner: {"fingerprint": dict, "cookies": [...], "birth_proxy": str|None} veya None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        # düz çerez listesi (nadir) → fingerprint yok
        if isinstance(data, list):
            return {"fingerprint": {}, "cookies": data, "birth_proxy": None,
                    "demographic": demo_mod.demographic_from_data({}, path)}
        return None
    fp = data.get("fingerprint") or {}
    cookies = data.get("cookies")
    if not isinstance(cookies, list):
        cookies = (data.get("storage_state") or {}).get("cookies") or []
    # doğum proxy'si: adswhite 'proxy' (str) → yoksa fingerprint.proxy.server / proxy_ip
    birth_proxy = data.get("proxy")
    if not isinstance(birth_proxy, str) or not birth_proxy.strip():
        birth_proxy = None
    if not birth_proxy:
        pd = fp.get("proxy") or {}
        birth_proxy = (pd.get("server") if isinstance(pd, dict) else None) or fp.get("proxy_ip") or data.get("proxy_ip")
        if not isinstance(birth_proxy, str) or not birth_proxy.strip():
            birth_proxy = None
    # Demografi: gömülü 'demographic' > sidecar (.meta.json) > dosya-adı kuralı (hedefli seçim için)
    dem = demo_mod.demographic_from_data(data, path)
    return {"fingerprint": fp, "cookies": cookies or [], "birth_proxy": birth_proxy, "demographic": dem}


def _resolve_geo(location):
    """location adına göre Türk şehri geolocation'ı + override JS döndürür. Yoksa (None, '')."""
    if not location:
        return None, ""
    city = None
    if location.lower().startswith("rastgele"):
        city = random.choice(TURKISH_CITIES)
    else:
        for c in TURKISH_CITIES:
            if c[0] == location:
                city = c
                break
    if not city:
        return None, ""
    return {"latitude": city[1], "longitude": city[2]}, generate_geolocation_js(city[1], city[2])


def _mask_proxy(pd):
    """Kimlik bilgisiz proxy sunucu string'i (panelde göstermek için — user:pass gösterilmez)."""
    if not pd:
        return ""
    if isinstance(pd, dict):
        return pd.get("server", "")
    return str(pd)


# ============================== ZİYARET (ADAPT — undetect seam) ==============================
async def visit_site(task_id, cfg: JobConfig, proxy_line, stop_event, log, browser, cookie_file, stats, fsvc, record):
    account = os.path.basename(cookie_file)
    used_proxy = ""
    used_demo = [""]                          # hesabın demografi etiketi (yükleme sonrası dolar)

    def _rec(status, clicked="", reason=""):
        try:
            record({
                "task_id": task_id,
                "account": account,
                "clicked": clicked,           # tıklanan rakip/hedef domain (başarıda)
                "status": status,             # success | fail | skipped
                "reason": reason,
                "proxy": used_proxy,
                "keyword": cfg.keyword,
                "mode": "tek-hedef" if cfg.single_target else "kelime-only",
                "demografi": used_demo[0],    # K·25-34 gibi (hangi demografik hesap tıkladı)
            })
        except Exception:
            pass

    profile = load_profile(cookie_file)
    if profile:
        try:
            used_demo[0] = demo_mod.demo_label(profile.get("demographic"))
        except Exception:
            used_demo[0] = ""
    if not profile or not profile.get("cookies"):
        log(f"⚠️ (Bot {task_id}) profil/çerez okunamadı: {account}")
        stats.fail += 1
        _rec("fail", reason="profil/çerez okunamadı")
        return

    fp_obj = _fp_from_stored(profile["fingerprint"])
    cookies = _sanitize_cookies(profile["cookies"])
    if not cookies:
        log(f"⚠️ (Bot {task_id}) geçerli çerez yok: {account}")
        stats.fail += 1
        _rec("fail", reason="geçerli çerez yok")
        return

    stealth = fsvc.get_stealth_script(fp_obj)
    geo_location, geo_js = _resolve_geo(cfg.location)

    target_domain = ""
    if cfg.target_url:
        try:
            tu = cfg.target_url if "://" in cfg.target_url else "https://" + cfg.target_url
            target_domain = urlparse(tu).netloc.replace("www.", "")
        except Exception:
            target_domain = ""

    reason = "deneme tükendi"
    max_retries = 3
    for attempt in range(max_retries):
        if stop_event.is_set():
            return

        # Proxy: panel listesi öncelikli, yoksa DOĞUM proxy'si. Parse edilemezse fail-closed.
        proxy_dict = None
        pl = proxy_line or profile.get("birth_proxy")
        if pl:
            proxy_dict = _parse_proxy(pl)
            if proxy_dict is None:
                # Ham proxy satırını LOGLAMA (user:pass sızabilir) — sadece redakte gösterge.
                log(f"⛔ (Bot {task_id}) proxy ayrıştırılamadı, gerçek-IP koruması → ziyaret atlandı")
                stats.fail += 1
                _rec("fail", reason="proxy ayrıştırılamadı (fail-closed)")   # Tur3 #10: fail sayılıyor → etiketi de 'fail'
                return
        else:
            # FAIL-CLOSED (#1): hiç proxy yok (ne panel ne doğum) → GERÇEK ev-IP'nden ÇIKMA.
            # (Aksi halde tüm tıklar tek ev-IP'sinden → hesaplar + IP yanar + deşifre.)
            log(f"⛔ (Bot {task_id}) proxy YOK → gerçek-IP koruması → ziyaret ATLANDI (hesabı korur)")
            stats.fail += 1
            _rec("fail", reason="proxy yok (fail-closed)")   # Tur3 #10: fail sayılıyor → etiketi de 'fail'
            return
        used_proxy = _mask_proxy(proxy_dict)

        context = None
        try:
            # >>> SEAM: SADQ undetect context — çerezin DOĞDUĞU fingerprint'ten kurulur <<<
            # ignore_https_errors YOK: bozuk sertifika üreten proxy hem eleme sinyali hem MITM riski.
            ctx_opts = fsvc.get_context_options(fp_obj)
            if proxy_dict:
                ctx_opts["proxy"] = proxy_dict
            if geo_location:
                ctx_opts["geolocation"] = geo_location
                ctx_opts["permissions"] = ["geolocation"]
            context = await browser.new_context(**ctx_opts)

            white_urls = cfg.white_urls

            async def _route_handler(route, request):
                u = request.url
                if "stun:" in u or "turn:" in u:
                    await route.abort()
                    return
                if white_urls and is_white_url(u, white_urls):
                    log(f"🚫 (Bot {task_id}) Beyaz URL isteği ENGELLENDİ: {u[:60]}")
                    await route.abort()
                    return
                await route.continue_()

            await context.route("**/*", _route_handler)

            # Stealth init script çerezlerden ÖNCE (document-start'ta çalışmalı).
            await context.add_init_script(stealth)
            if geo_js:
                await context.add_init_script(geo_js)

            # Çerez yükle: önce toplu, patlarsa TEK TEK (tek bozuk çerez hepsini düşürmesin).
            loaded = 0
            try:
                await context.add_cookies(cookies)
                loaded = len(cookies)
            except Exception:
                for ck in cookies:
                    try:
                        await context.add_cookies([ck])
                        loaded += 1
                    except Exception:
                        pass
            if loaded == 0:
                log(f"⚠️ (Bot {task_id}) HİÇ çerez yüklenemedi — oturum ANONİM, atlandı")
                stats.fail += 1
                _rec("fail", reason="çerez yüklenemedi (anonim)")
                return
            if attempt == 0:
                log(f"🍪 (Bot {task_id}) {loaded}/{len(cookies)} çerez · {fp_obj.model} · Chrome {fp_obj.browser_version}")

            page = await context.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(45000)

            # CDP: userAgentMetadata → yüksek-entropili Client Hints Android'e sabit (ağ
            # desktop-Linux sızıntısını kapatır #3). Navigasyondan ÖNCE, sayfa başına.
            try:
                cdp = await context.new_cdp_session(page)
                await cdp.send("Network.setUserAgentOverride", fsvc.ua_cdp_override(fp_obj))
                # Mobil dokunmatik: pointer/hover media query'lerini mobil değerlere sabitle (#17)
                try:
                    await cdp.send("Emulation.setEmulatedMedia", {"features": [
                        {"name": "pointer", "value": "coarse"},
                        {"name": "any-pointer", "value": "coarse"},
                        {"name": "hover", "value": "none"},
                        {"name": "any-hover", "value": "none"},
                    ]})
                except Exception:
                    pass
            except Exception as e:
                log(f"⚠️ (Bot {task_id}) CDP UA override atlandı: {str(e)[:40]}")

            # Popup/yeni-sekme reklamlarına da CDP UA override uygula (#15)
            def _on_popup(pg):
                async def _ap():
                    try:
                        c = await context.new_cdp_session(pg)
                        await c.send("Network.setUserAgentOverride", fsvc.ua_cdp_override(fp_obj))
                    except Exception:
                        pass
                try:
                    asyncio.get_running_loop().create_task(_ap())
                except Exception:
                    pass
            try:
                context.on("page", _on_popup)
            except Exception:
                pass

            if not await safe_goto(page, "https://www.google.com", max_retries=3, timeout=30000):
                log(f"❌ (Bot {task_id}) Google yüklenemedi")
                reason = "google yüklenemedi"
                continue
            if not await handle_captcha(page, cfg.capsolver_api, log, task_id, proxy=proxy_dict):
                reason = "captcha geçilemedi"
                continue
            await _dismiss_consent(page)
            await page.wait_for_timeout(random.randint(800, 1500))

            # Arama: kutuya İNSAN gibi yaz; kutu yoksa DOĞRUDAN /search'e git (SERP garanti: #22)
            search_selector = None
            for sel in ('textarea[name="q"]', 'input[name="q"]'):
                if await page.query_selector(sel):
                    search_selector = sel
                    break
            searched = False
            if search_selector:
                try:
                    await page.click(search_selector)
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    await human_type(page, search_selector, cfg.keyword)
                    await page.keyboard.press("Enter")
                    searched = True
                except Exception:
                    searched = False
            if not searched:
                await safe_goto(page, f"https://www.google.com/search?q={quote_plus(cfg.keyword)}&hl=tr&gl=tr",
                                max_retries=2, timeout=30000)

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            await _dismiss_consent(page)
            if not await handle_captcha(page, cfg.capsolver_api, log, task_id, proxy=proxy_dict):
                reason = "captcha geçilemedi (arama)"
                continue
            # SERP DOĞRULA — reklamlar ancak arama sonuç sayfasında olur
            if "/search" not in (page.url or ""):
                await safe_goto(page, f"https://www.google.com/search?q={quote_plus(cfg.keyword)}&hl=tr&gl=tr",
                                max_retries=2, timeout=30000)
                await _dismiss_consent(page)
                if "/search" not in (page.url or ""):
                    reason = "SERP'e ulaşılamadı"
                    continue

            clicked = await google_search_behavior(
                page, task_id, log, target_domain, cfg.white_urls, cfg.single_target
            )
            if clicked == "__wl_skip__":       # #16: whitelist iptali → nötr (fail değil)
                _rec("skipped", reason="hedef whitelist'te — iptal")
                return "skipped"
            if clicked:
                log(f"✅ (Bot {task_id}) REKLAM ZİYARETİ TAMAMLANDI → {clicked}")
                stats.success += 1
                _rec("success", clicked=clicked,
                     reason=("hedef tıklandı" if cfg.single_target else "rakip tıklandı"))
                return "success"
            else:
                stats.fail += 1
                _rec("fail", reason="geçerli tık çıkmadı")
                return "fail"

        except Exception as e:
            log(f"❌ (Bot {task_id}) hata: {str(e)[:60]}")
            reason = f"hata: {str(e)[:40]}"
        finally:
            if context:
                try:
                    await asyncio.wait_for(context.close(), timeout=15)   # #13: sınırsız close → VISIT_BUDGET etkisiz
                except (Exception, asyncio.TimeoutError):
                    pass

    # Tüm retry'lar tükendi (continue/exception) → durdurulmadıysa TEK fail say + kaydet.
    if not stop_event.is_set():
        stats.fail += 1
        _rec("fail", reason=reason)


# ============================== WORKER POOL (ADAPT) ==============================
def discover_cookie_files(dirs):
    """Verilen klasörlerde *.json/*.txt çerez dosyalarını bulur (düz + tek seviye alt-klasör)."""
    files = []
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        files += glob.glob(os.path.join(d, "*.json"))
        files += glob.glob(os.path.join(d, "*.txt"))
        files += glob.glob(os.path.join(d, "*", "*.json"))
    # tekrarları at + demografi SIDECAR'larını (.meta.json) ELE — çerez değil, hayalet-hesap olurdu
    # (hep-fail → circuit-breaker/stall'ı false-abort'a iter: Tur3 #1).
    # + BASENAME-DEDUP: kimlik her yerde basename (ledger/proxy/capacity). Aynı basename'in farklı
    # klasörlerdeki ikizleri → eşzamanlı tek-IP (impossible-travel) + cap karışması olurdu (Tur4 #2/#3).
    seen = set()
    out = []
    for f in sorted(x for x in set(files) if not x.endswith(".meta.json")):
        b = os.path.basename(f)
        if b not in seen:
            seen.add(b)
            out.append(f)
    return out


class AccountPool:
    """Hesap leasing: aynı hesap AYNI ANDA en fazla bir kez; kullanımdan sonra cooldown;
    K ardışık fail → karantina. Impossible-travel + hesap-yorma + banlı-hesap tekrarını önler.

    DEMOGRAFİ: target_ages/target_gender verilirse, YALNIZ hedefe uyan hesaplar 'eligible' olur
    (hedeflenen boyutta 'unknown' olan elenir → demografik reklam görünmeyen hesaba tık boşa gitmez)."""
    def __init__(self, files, cooldown=120, quar_fails=3, quar_secs=1800,
                 target_ages=None, target_gender=""):
        self.files = list(files)
        self.cooldown = cooldown
        self.quar_fails = quar_fails
        self.quar_secs = quar_secs
        self.state = {}
        self.target_ages = list(target_ages or [])
        self.target_gender = demo_mod.normalize_target_gender(target_gender)
        # Demografi hedeflemesi AÇIKSA her hesabın demografisini bir kez oku → süz. Kapalıysa
        # tüm çerezleri açmaya gerek yok (gereksiz I/O): eligible = hepsi.
        if self.target_ages or self.target_gender:
            self.demo = {f: demo_mod.demographic_from_file(f) for f in self.files}
            self.eligible = [f for f in self.files
                             if demo_mod.matches(self.demo[f], self.target_ages, self.target_gender)]
        else:
            self.demo = {}
            self.eligible = list(self.files)

    def demo_of(self, f):
        return self.demo.get(f) or {}

    def eligible_count(self):
        return len(self.eligible)

    def _s(self, f):
        return self.state.setdefault(f, {"inflight": False, "last": 0.0, "fails": 0, "quar_until": 0.0})

    def lease(self):
        now = time.monotonic()
        cand = []
        for f in self.eligible:                          # sadece demografiye uyan havuz
            s = self.state.get(f)
            if not s:
                cand.append(f)
                continue
            if s["inflight"] or s["quar_until"] > now or (now - s["last"]) < self.cooldown:
                continue
            cand.append(f)
        if not cand:
            return None
        # ROUND-ROBIN (LRU): en UZUN SÜREDİR kullanılmayan çerezi seç (last en küçük; hiç kullanılmamış=0
        # en önce). Böylece TÜM farklı çerezler birer kez kullanılmadan hiçbiri tekrar kullanılmaz →
        # üst üste aynı çerezle tık (Google iade/geçersiz sayar) ENGELLENIR. Bir tur biter, baştan döner.
        f = min(cand, key=lambda x: self.state.get(x, {}).get("last", 0.0))
        self._s(f)["inflight"] = True
        return f

    def release(self, f, success):
        s = self._s(f)
        s["inflight"] = False
        s["last"] = time.monotonic()
        if success:
            s["fails"] = 0
        else:
            s["fails"] += 1
            if s["fails"] >= self.quar_fails:
                s["quar_until"] = time.monotonic() + self.quar_secs
                s["fails"] = 0

    def quarantined(self):
        now = time.monotonic()
        return sum(1 for s in self.state.values() if s["quar_until"] > now)


def _proxy_for(account, proxy_list):
    """Hesabı proxy'ye KALICI eşle (hep aynı çıkış IP → impossible-travel yok). Panel proxy'si
    varsa hash ile stabil seç; yoksa None (visit_site DOĞUM proxy'sine düşer, o da hesaba sabit)."""
    if not proxy_list:
        return None
    # STABİL digest: builtin hash() PYTHONHASHSEED ile process-başına TUZLANIR → her restart'ta
    # hesap→proxy DEĞİŞİR = aynı hesap farklı çıkış-IP = impossible-travel = HESAP YANAR (#8).
    idx = int.from_bytes(hashlib.sha1(os.path.basename(account).encode("utf-8")).digest()[:4], "big") % len(proxy_list)
    return proxy_list[idx]


# Datacenter/hosting ASN/ISP anahtar kelimeleri — exit-IP bunlardan biriyse Google GIVT ile ANINDA eler.
_DC_HINTS = ("ovh", "amazon", "aws", "google", "gcp", "digitalocean", "hetzner", "linode", "vultr",
             "contabo", "choopa", "leaseweb", "m247", "datacamp", "hosting", "cloud", "server",
             "datacenter", "data center", "colo", "microsoft", "azure", "oracle", "scaleway",
             "hostwinds", " colocation", "dedicated", "vps", "netcup", "clouvider")


async def _preflight_proxy_geo(browser, proxy_list, log, stop_event=None):
    """Panel proxy'lerinin exit-IP'sini bir kez kontrol et: DATACENTER mı (=iade garantisi) veya
    TR-DIŞI mı (=IP-geo↔timezone uyuşmazlığı, SIVT). En yüksek-kaldıraçlı IVT sinyali OPERASYONELDİR
    (residential/mobil TR proxy) — kod sadece yanlış proxy'yi ERKEN yakalar. Best-effort + iptal-edilebilir (#14)."""
    seen = set()
    for pl in (proxy_list or []):
        if stop_event is not None and stop_event.is_set():   # #14: Durdur'a basıldıysa erken çık
            return
        pd = _parse_proxy(pl)
        if not pd:
            continue
        key = pd.get("server", "")
        if not key or key in seen:
            continue
        seen.add(key)
        ctx = None
        try:
            ctx = await browser.new_context(proxy=pd)
            pg = await ctx.new_page()
            await pg.goto("http://ip-api.com/json/?fields=status,country,countryCode,timezone,isp,org,as,query",
                          wait_until="domcontentloaded", timeout=15000)
            txt = await pg.evaluate("() => document.body ? document.body.innerText : ''")
            data = json.loads(txt)
            cc = data.get("countryCode", "") or ""
            blob = (str(data.get("isp", "")) + " " + str(data.get("org", "")) + " " + str(data.get("as", ""))).lower()
            ipq = data.get("query", "")
            if any(k in blob for k in _DC_HINTS):
                log(f"⛔ PROXY RİSKİ: {key} → {ipq} DATACENTER/hosting görünüyor ({data.get('isp','')[:30]}). "
                    f"Google GIVT bunu FATURALAMADAN eler = tık boşa. RESIDENTIAL/MOBİL proxy şart!")
            elif cc and cc != "TR":
                log(f"⚠️ PROXY RİSKİ: {key} → ülke={cc} ama fingerprint+hesap TR. IP-geo↔timezone "
                    f"uyuşmazlığı SIVT tetikler (geç iade). TR çıkışlı proxy kullan.")
            else:
                log(f"✅ Proxy {key} → {ipq} · {cc} · {data.get('isp','')[:28]} (residential görünüyor)")
        except Exception as e:
            log(f"ℹ️ Proxy geo-kontrol atlandı ({key}): {str(e)[:40]}")
        finally:
            if ctx:
                try:
                    await ctx.close()
                except Exception:
                    pass


async def run_click_job(cfg: JobConfig, cookie_files, proxy_list, log, stats, stop_event, record):
    """Tek tarayıcı + N asyncio worker ile tık işini yürütür. record: per-visit sonuç callback'i."""
    if not cookie_files:
        log("❌ Çerez dosyası bulunamadı — iş başlatılamadı.")
        return

    fsvc = FingerprintService()
    # Masaüstü: CLICKER_ENGINE=vanilla → düz playwright (patchright override'larımızı EZİYOR;
    # vanilla + headful'da de-korelasyon + WebGL/deviceMemory spoof GERÇEKTEN çalışır).
    _pref = os.environ.get("CLICKER_ENGINE", "").lower()
    if _pref == "vanilla":
        from playwright.async_api import async_playwright
        engine = "playwright-vanilla"
    else:
        try:
            from patchright.async_api import async_playwright
            engine = "patchright"
        except ImportError:
            from playwright.async_api import async_playwright
            engine = "playwright"

    base_args = [
        "--disable-dev-shm-usage", "--disable-background-networking",
        "--disable-default-apps", "--disable-sync", "--no-first-run",
        "--disable-blink-features=AutomationControlled",
        # WebRTC GERÇEK public/local IP sızıntısını KES — geçerli flag'ler (--disable-webrtc geçersizdi: #7)
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-features=WebRtcHideLocalIpsWithMdns",
    ]
    n = max(1, min(int(cfg.concurrency or 1), MAX_CONCURRENCY))
    pool = AccountPool(cookie_files, cooldown=max(60, cfg.think_time * 2),
                       target_ages=cfg.target_age, target_gender=cfg.target_gender)
    # Demografi hedeflemesi açıksa uygunluk özetini bildir (0 ise operatör 'Demografi Tara' çalıştırmalı).
    if pool.target_ages or pool.target_gender:
        _tg = {"female": "Kadın", "male": "Erkek"}.get(pool.target_gender, "farketmez")
        _ta = ",".join(pool.target_ages) if pool.target_ages else "farketmez"
        elig = pool.eligible_count()
        log(f"🎯 Demografi hedefi: cinsiyet={_tg} · yaş={_ta} → {elig}/{len(cookie_files)} hesap uygun")
        if elig == 0:
            log("⛔ Hedef demografiye UYAN hesap yok. Çerezleri etiketle veya 'Demografi Tara' çalıştır.")
            log("🏁 İş iptal (0 uygun hesap) — tarayıcı açılmadı.")
            return   # KRİTİK: aksi halde workerlar lease()==None'da sonsuza kadar döner, iş asılır

    # SIVT AGREGAT tavanı: kalıcı defterden bugünkü GÜVENLİ kapasiteyi hesapla → effective_target.
    ledger = ClickLedger(_HISTORY_PATH)

    _save_fails = {"n": 0}

    def _record_led(r):
        """record callback sarmalayıcı: BAŞARILI tıkı kalıcı deftere işle. Disk yazımı KALICI
        (3 ardışık) başarısızsa işi durdur (bayat-state → cap ihlali) — tek transient hiccup'ta DEĞİL (Tur3 #5)."""
        try:
            if r.get("status") == "success":
                if ledger.record(r.get("account", ""), r.get("proxy", ""), r.get("clicked", "")) is False:
                    _save_fails["n"] += 1
                    log(f"⚠️ Tık geçmişi diske yazılamadı ({_save_fails['n']}/3)")
                    if _save_fails["n"] >= 3:
                        log("⛔ Disk 3 kez üst üste yazılamadı — cap ihlali riski, iş durduruluyor.")
                        stop_event.set()
                else:
                    _save_fails["n"] = 0
        except Exception:
            pass
        record(r)

    now0 = time.time()
    acct_cap = int(cfg.max_clicks_per_account_day or 0)
    ip_cap = int(cfg.max_clicks_per_ip_day or 0)
    effective_target = int(cfg.total_visits)

    _pkey_cache = {}

    def _acct_proxy_key(a):
        """Hesabın GERÇEK çıkış-IP anahtarı: panel proxy varsa o; yoksa DOĞUM proxy'si (çerezden
        okunur, cache'li). Birth-proxy hesapları da ip_cap/velocity'ye tabi olur (#5/#9). Görüntü-server."""
        if a in _pkey_cache:
            return _pkey_cache[a]
        pl = _proxy_for(a, proxy_list)
        if not pl:
            try:
                pl = (load_profile(a) or {}).get("birth_proxy")
            except Exception:
                pl = None
        key = _mask_proxy(_parse_proxy(pl)) if pl else ""
        _pkey_cache[a] = key
        return key

    # #7: tek-hedef modunda hedef domain (aynı hesabın aynı hedefi cooldown içinde tekrar tıklamasını engelle)
    _target_dom = ""
    _cool = int(cfg.target_cooldown_days or 0)
    if cfg.single_target and cfg.target_url:
        try:
            _tu = cfg.target_url if "://" in cfg.target_url else "https://" + cfg.target_url
            _target_dom = urlparse(_tu).netloc.replace("www.", "").lower()
        except Exception:
            _target_dom = ""

    # #2: acct_cap VEYA ip_cap açıksa kapasiteyi kıs (yalnız acct_cap>0 değil → acct_cap=0+ip_cap
    # senaryosunda effective_target IP ile de bağlansın, aksi halde iş asılıyordu).
    if acct_cap > 0 or ip_cap > 0:
        capacity = ledger.capacity(pool.eligible, _acct_proxy_key,
                                   acct_cap if acct_cap > 0 else 10**9,
                                   ip_cap if ip_cap > 0 else 10**9, now=now0,
                                   target_dom=_target_dom, cooldown_days=_cool)
        effective_target = max(0, min(effective_target, capacity))
        log(f"📊 SIVT tavanı: hesap≤{acct_cap or '∞'}/gün · IP≤{ip_cap or '∞'}/gün → bugün güvenli "
            f"kapasite {capacity} tık (hedef {cfg.total_visits} → etkin {effective_target})")
        if effective_target == 0:
            log("⛔ Bugünkü güvenli kota DOLU (hesaplar/IP günlük tavana ulaştı). Yarın devam et veya "
                "daha çok hesap/proxy ekle. İş iptal — tarayıcı açılmadı.")
            return

    VISIT_BUDGET = 300   # ziyaret başına SERT üst sınır (dwell+retry+captcha dahil) → hung worker kesilir
    # Masaüstü: CLICKER_HEADFUL=1 → zorla HEADFUL (gerçek ekran+GPU var, headless tell'i yok).
    force_headful = os.environ.get("CLICKER_HEADFUL", "").lower() in ("1", "true", "yes")
    display = os.environ.get("DISPLAY")
    launch_headless = False if force_headful else not bool(display)
    render_label = "headful" if not launch_headless else "classic-headless"
    log(f"🚀 Tarayıcı başlatılıyor ({engine}, {render_label})…")

    async with async_playwright() as p:
        _headful_dead = [False]

        async def _launch():
            # HEADFUL: mobil pencere boyutuyla (--start-maximized masaüstü pencereyi ele veriyordu #10/#25).
            if not launch_headless and not _headful_dead[0]:
                errs = None
                for extra in (["--window-size=400,860"], ["--window-size=400,860", "--no-sandbox"]):
                    try:
                        br = await p.chromium.launch(headless=False, args=base_args + extra)
                        log("✅ HEADFUL açıldı — gerçek render")
                        return br
                    except Exception as e:
                        errs = e
                if force_headful:
                    # SESSİZCE headless'e DÜŞME (#6): headless tespit edilir, kullanıcı 'headful' sanır.
                    raise RuntimeError(f"HEADFUL AÇILAMADI (headless'e düşülmedi): {str(errs)[:80]}")
                _headful_dead[0] = True
                log("⚠️ Headful açılamadı → classic-headless")
            last = None
            for extra in ([], ["--no-sandbox"]):
                try:
                    return await p.chromium.launch(headless=True, args=base_args + extra)
                except Exception as e:
                    last = e
            raise last or RuntimeError("Tarayıcı açılamadı")

        browser = await _launch()
        log(f"✅ Tarayıcı hazır · {len(cookie_files)} hesap · {n} worker · hedef {effective_target} · proxy {len(proxy_list)}")

        # IVT ön-kontrol: panel proxy'leri DATACENTER/TR-dışı mı? (en yüksek IVT sinyali burada erken yakalanır)
        if proxy_list and not stop_event.is_set():
            try:
                await _preflight_proxy_geo(browser, proxy_list, log, stop_event)
            except Exception:
                pass

        early = {"total": 0, "fail": 0}   # devre kesici: ilk ziyaretler çoğu fail'se işi yak(ma)

        async def _sleep_stoppable(secs):
            waited = 0.0
            while waited < secs and not stop_event.is_set():
                await asyncio.sleep(min(1.0, secs - waited))
                waited += 1.0

        relaunch_lock = asyncio.Lock()
        # PER-IP VELOCITY: aynı çıkış-IP'sinden tık hızını sınırla (tek proxy → tüm tık tek IP =
        # SIVT velocity kümesi). Proxy başına min-gap + diurnal çarpanı. (IVT: 'low-and-slow beats volume')
        proxy_gate = asyncio.Lock()
        proxy_last = {}
        _ip_pending = {}   # #4 TOCTOU: bu IP'de UÇUŞTA olan (henüz kaydedilmemiş) tık sayısı
        stall = {"n": 0}   # #1 anti-hang: ardışık ilerlemesiz iterasyon (bütçe-dolu skip / fail)
        # UYGUN havuza göre boyutla (tüm-liste değil): demografi-filtreli küçük havuzda 10x geç-abort'u önler (Tur3 #3)
        stall_limit = max(30, pool.eligible_count() * 3)
        busy = {"n": 0}    # UÇUŞTAKİ gerçek ziyaret sayısı (bütçe-skip'in yavaş-başarıyı false-abort'unu önler: Tur3 #2)
        relaunch_fails = {"n": 0}   # ardışık tarayıcı-relaunch başarısızlığı (OOM/DISPLAY) → sınırlı (Tur5)

        async def _proxy_pace(key):
            """Bu çıkış-IP anahtarı (panel VEYA birth) için min-gap dolana kadar bekle (velocity tavanı)."""
            if not key:
                return
            gap = max(12.0, float(cfg.think_time)) * _diurnal_mult()
            while not stop_event.is_set():
                async with proxy_gate:
                    now = time.monotonic()
                    last = proxy_last.get(key, 0.0)
                    if now - last >= gap:
                        proxy_last[key] = now
                        return
                    wait = gap - (now - last)
                await _sleep_stoppable(min(wait, 5.0))

        def _bump_stall():
            """İlerlemesiz iterasyon (lease None / bütçe-dolu). Eşik aşılırsa işi KESİN sonlandır (#1)."""
            stall["n"] += 1
            if stall["n"] >= stall_limit:
                log("⛔ Tüm hesaplar/IP bugünlük kotada veya erişilemiyor (ilerleme yok) — iş sonlandırıldı.")
                stop_event.set()

        async def worker(wid):
            nonlocal browser
            await _sleep_stoppable(_lognorm(wid * 2.0, 0.6, 0.3, 45))   # stagger
            while not stop_event.is_set():
                if stats.success >= effective_target:      # #3: BAŞARI-bazlı sonlandırma (deneme değil)
                    return
                # Tarayıcı iş-ortasında öldüyse yeniden başlat — TEK worker (kilit) yapsın (#14).
                if not browser.is_connected():
                    async with relaunch_lock:
                        if not browser.is_connected():
                            log("⚠️ Tarayıcı bağlantısı düştü — yeniden başlatılıyor…")
                            try:
                                try:
                                    await browser.close()
                                except Exception:
                                    pass
                                browser = await _launch()
                                relaunch_fails["n"] = 0
                                log("✅ Tarayıcı yeniden başlatıldı")
                            except Exception as e:
                                log(f"❌ Relaunch başarısız: {str(e)[:50]}")
                                # Tur5: ısrarlı relaunch başarısızlığı (OOM/DISPLAY kaybı) SONSUZ dönüyordu.
                                # 6 ardışık başarısızlık (~30s) → iş kesilir (terminasyon garantisi).
                                relaunch_fails["n"] += 1
                                if relaunch_fails["n"] >= 6:
                                    log("⛔ Tarayıcı 6 kez yeniden başlatılamadı (OOM/DISPLAY?) — iş sonlandırıldı.")
                                    stop_event.set()
                                await _sleep_stoppable(5)
                    if not browser.is_connected():
                        continue
                # Hesap lease et (aynı hesap aynı anda tek; cooldown/karantina).
                acct = pool.lease()
                if acct is None:
                    # None-lease GEÇİCİ (cooldown/karantina dolar) → stall SAYMA (aksi halde büyük
                    # think_time'da meşru cooldown beklemesinde yanlış-abort olurdu). Yalnız KALICI
                    # durum (günlük-cap budget-skip) stall'a sayılır.
                    await _sleep_stoppable(_lognorm(6, 0.4, 2, 20))
                    continue
                proxy_line = _proxy_for(acct, proxy_list)   # hesaba SABIT proxy (impossible-travel yok)
                _pkey = _acct_proxy_key(acct)   # GERÇEK çıkış-IP (panel VEYA birth) → ip_cap birth'te de işler (#5/#9)
                _bn = os.path.basename(acct)
                # SIVT günlük tavan: hesap VEYA IP kotası dolduysa ATLA. IP kontrolüne UÇUŞTAKİ (henüz
                # kaydedilmemiş) tıklar dahil → TOCTOU aşımı yok (#4).
                _ip_now = ledger.proxy_clicks_today(_pkey) + _ip_pending.get(_pkey, 0) if _pkey else 0
                # #7: tek-hedef cooldown — bu hesap bu hedefi son N günde tıkladıysa ATLA (tekrar-yolculuk)
                _cool_hit = (_target_dom and _cool > 0 and
                             ledger.target_recent(_bn, _target_dom, cooldown_days=_cool))
                if _cool_hit or \
                   (acct_cap > 0 and ledger.account_clicks_today(_bn) >= acct_cap) or \
                   (ip_cap > 0 and _pkey and _ip_now >= ip_cap):
                    pool.release(acct, True)      # fail değil — sadece bugünlük dolu / cooldown
                    # Budget-skip'i YALNIZ hiç gerçek ziyaret uçuşta değilken stall'a say (Tur3 #2):
                    # aksi halde yavaş-başarı yaparken kapalı hesapların skip'leri stall'ı doldurup
                    # kapasitesi olan işi false-abort ediyordu. 'Hepsi kapalı' terminal abort korunur.
                    if busy["n"] == 0:
                        _bump_stall()
                    await _sleep_stoppable(_lognorm(3, 0.4, 1, 10))
                    continue
                # Buradan itibaren GERÇEK ziyaret → uçuşta-IP + busy sayaçlarını artır, finally'de azalt (#4/Tur3#2).
                if _pkey:
                    _ip_pending[_pkey] = _ip_pending.get(_pkey, 0) + 1
                busy["n"] += 1
                try:
                    # PER-IP VELOCITY gate: bu çıkış-IP'si için min-gap dolana kadar bekle (low-and-slow).
                    await _proxy_pace(_pkey)
                    if stop_event.is_set() or stats.success >= effective_target:
                        pool.release(acct, True)
                        return
                    stats.total_visits_done += 1
                    task_id = stats.total_visits_done
                    outcome = None
                    ok = False
                    skipped = False
                    try:
                        outcome = await asyncio.wait_for(
                            visit_site(task_id, cfg, proxy_line, stop_event, log, browser, acct, stats, fsvc, _record_led),
                            timeout=VISIT_BUDGET,
                        )
                    except asyncio.TimeoutError:
                        log(f"⏱️ (Bot {task_id}) ziyaret bütçesi ({VISIT_BUDGET}s) aşıldı — kesildi")
                        stats.fail += 1
                        outcome = "fail"
                        try:
                            record({"task_id": task_id, "account": os.path.basename(acct), "clicked": "",
                                    "status": "fail", "reason": "ziyaret bütçesi aşıldı",
                                    "proxy": _pkey, "keyword": cfg.keyword,
                                    "mode": "tek-hedef" if cfg.single_target else "kelime-only",
                                    "demografi": _demo_label_of(acct)})
                        except Exception:
                            pass
                    except Exception as e:
                        log(f"❌ Worker {wid} hatası (Bot {task_id}): {str(e)[:60]}")
                        stats.fail += 1
                        outcome = "fail"
                        try:
                            record({"task_id": task_id, "account": os.path.basename(acct), "clicked": "",
                                    "status": "fail", "reason": f"worker hata: {str(e)[:40]}",
                                    "proxy": _pkey, "keyword": cfg.keyword,
                                    "mode": "tek-hedef" if cfg.single_target else "kelime-only",
                                    "demografi": _demo_label_of(acct)})
                        except Exception:
                            pass
                    ok = (outcome == "success")
                    skipped = (outcome == "skipped")       # #16: whitelist iptali → fail DEĞİL, nötr
                    pool.release(acct, ok or skipped)      # skipped karantinaya SÜRÜKLEMESİN (fail değil)
                    # #1/#2/#3: stall'ı BAŞARI'ya göre izle (deneme değil). Başarı→sıfırla; aksi (fail
                    # VEYA skipped=ilerleme yok)→bump → hep-fail VEYA hep-whitelist-skip akışı stall_limit'te
                    # İPTAL (skipped'ı stall'DIŞI bırakmak all-skip HANG'i açıyordu — kendi bulgum).
                    if ok:
                        stall["n"] = 0
                    else:
                        _bump_stall()
                finally:
                    if _pkey:                              # #4: uçuştaki sayacı GERİ al
                        _ip_pending[_pkey] = max(0, _ip_pending.get(_pkey, 0) - 1)
                    busy["n"] = max(0, busy["n"] - 1)      # Tur3 #2: uçuştaki gerçek-ziyaret sayacı
                # Devre kesici: ilk ~12 ziyaretin %85+'i fail ise (ölü proxy/ağ) işi İPTAL et.
                # skipped (whitelist iptali) SAYILMAZ (#16); oran fraction ile (#12: int() %75'e düşürüyordu).
                if not skipped and early["total"] < 12:
                    early["total"] += 1
                    early["fail"] += 0 if ok else 1
                    if early["total"] >= 8 and (early["fail"] / early["total"]) >= 0.85:
                        log("⛔ İlk ziyaretlerin ~%85+'i başarısız (ölü proxy/ağ?) — iş İPTAL (bütçe yakılmadı).")
                        stop_event.set()
                        return
                # Ziyaretler arası think-time (log-normal) × diurnal (gece yavaş → sirkadiyen entropi).
                if not stop_event.is_set() and stats.success < effective_target:
                    base = max(3, cfg.think_time) * _diurnal_mult()
                    await _sleep_stoppable(_lognorm(base, 0.7, 3, base * 6))

        try:
            await asyncio.gather(*[asyncio.create_task(worker(i + 1)) for i in range(n)])
        finally:
            try:
                await asyncio.wait_for(browser.close(), timeout=15)
            except Exception:
                pass   # kapanış hang'i → async_playwright __aexit__ zorla temizler

    done = stats.total_visits_done
    log(f"🏁 İş bitti · {stats.success} başarılı / {stats.fail} başarısız / {done} ziyaret · karantina {pool.quarantined()} hesap")


# ============================== DEMOGRAFİ TARAMA (ad-center okuyucu) ==============================
async def scan_demographics_job(cookie_files, proxy_list, log, stop_event, record=None, only_unknown=True):
    """Her çerezle Google Ad Center'a girip yaş+cinsiyeti BEST-EFFORT okur, sonucu <cerez>.meta.json
    sidecar'ına yazar (çereze dokunmaz). Böylece hedefli koşuda hesaplar demografiyle seçilebilir.
    only_unknown=True → zaten etiketli hesapları atla. Proxy FAIL-CLOSED (proxysiz okuma yok)."""
    if not cookie_files:
        log("❌ Taranacak çerez yok.")
        return
    _pref = os.environ.get("CLICKER_ENGINE", "").lower()
    if _pref == "vanilla":
        from playwright.async_api import async_playwright
    else:
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            from playwright.async_api import async_playwright

    base_args = [
        "--disable-dev-shm-usage", "--disable-background-networking",
        "--disable-default-apps", "--disable-sync", "--no-first-run",
        "--disable-blink-features=AutomationControlled",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-features=WebRtcHideLocalIpsWithMdns",
    ]
    force_headful = os.environ.get("CLICKER_HEADFUL", "").lower() in ("1", "true", "yes")
    display = os.environ.get("DISPLAY")
    launch_headless = False if force_headful else not bool(display)
    fsvc = FingerprintService()
    scanned = 0
    known = 0
    log(f"🔎 Demografi taraması başlıyor · {len(cookie_files)} hesap")

    async with async_playwright() as p:
        async def _launch():
            if not launch_headless:
                for extra in (["--window-size=400,860"], ["--window-size=400,860", "--no-sandbox"]):
                    try:
                        return await p.chromium.launch(headless=False, args=base_args + extra)
                    except Exception:
                        pass
                if force_headful:
                    raise RuntimeError("HEADFUL açılamadı (tarama)")
            for extra in ([], ["--no-sandbox"]):
                try:
                    return await p.chromium.launch(headless=True, args=base_args + extra)
                except Exception as e:
                    last = e
            raise last or RuntimeError("Tarayıcı açılamadı")

        browser = await _launch()
        try:
            for cf in cookie_files:
                if stop_event.is_set():
                    break
                account = os.path.basename(cf)
                profile = load_profile(cf)
                if not profile or not profile.get("cookies"):
                    log(f"⚠️ {account}: çerez okunamadı, atlandı")
                    continue
                if only_unknown and demo_mod.is_known(profile.get("demographic")):
                    continue
                pl = _proxy_for(cf, proxy_list) or profile.get("birth_proxy")
                proxy_dict = _parse_proxy(pl) if pl else None
                if proxy_dict is None:
                    log(f"⛔ {account}: proxy yok/parse hatası → gerçek-IP koruması, atlandı")
                    continue
                fp_obj = _fp_from_stored(profile["fingerprint"])
                cookies = _sanitize_cookies(profile["cookies"])
                context = None
                try:
                    ctx_opts = fsvc.get_context_options(fp_obj)
                    ctx_opts["proxy"] = proxy_dict
                    context = await browser.new_context(**ctx_opts)
                    await context.add_init_script(fsvc.get_stealth_script(fp_obj))
                    try:
                        await context.add_cookies(cookies)
                    except Exception:
                        for ck in cookies:
                            try:
                                await context.add_cookies([ck])
                            except Exception:
                                pass
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                    demo = await asyncio.wait_for(
                        demo_mod.read_demographic_via_adcenter(page, log=log), timeout=90)
                    demo_mod.write_sidecar(cf, demo)
                    scanned += 1
                    if demo_mod.is_known(demo):
                        known += 1
                    log(f"   ✓ {account} → {demo_mod.demo_label(demo)}")
                    if record:
                        try:
                            record({"account": account, "demografi": demo_mod.demo_label(demo),
                                    "status": "scan", "reason": demo.get("source", "")})
                        except Exception:
                            pass
                except Exception as e:
                    log(f"   ✗ {account}: {str(e)[:60]}")
                finally:
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass
        finally:
            try:
                await asyncio.wait_for(browser.close(), timeout=15)
            except Exception:
                pass
    log(f"🔎 Tarama bitti · {scanned} tarandı / {known} demografi bulundu")
