# click — masaüstü GUI (adswhite tarzı pencere + menü)

VPS'te **engellenen** her şey burada **çalışır**: gerçek pencere (**headful**), gerçek GPU,
**vanilla playwright** (patchright ezmiyor) → per-profil **de-korelasyon** (her hesap farklı
canvas/WebGL/audio hash → toplu-ban zinciri kırılır) + WebGL/deviceMemory spoof + CDP Client
Hints + dokunmatik davranış + hesap-proxy leasing.

## Çalıştırma — ÇİFT TIKLA

- **Windows:** `start.bat`'e çift tıkla
- **Mac:** `start.command`'a çift tıkla

İlk seferde otomatik kurar (venv + Chromium indirir — birkaç dakika), sonra **pencere açılır**.
Sonraki açılışlar hızlıdır.

> Mac'te ilk çift tıklamada "izin" uyarısı çıkarsa: sağ tık → **Aç** (bir kez).
> Windows'ta Python kurulu değilse önce python.org'dan Python 3'ü kur (kurulumda "Add to PATH" işaretle).

## Pencerede (menü)

| Alan | Ne |
|---|---|
| **Anahtar Kelime** | Aratılacak kelime (zorunlu) |
| **Hedef URL** + *Tek hedef modu* | Kapalı = kelime-only (rakibe tıkla) · Açık = sadece hedef domaine tıkla |
| **Kendi/Beyaz Linkler** | Kendi siten(ler)in — ASLA tıklanmaz. Domain yeter (`benimsite.com` → tüm alt-alan+path) |
| **CapSolver Key** | Google captcha çıkarsa |
| **Lokasyon** | Rastgele / şehir / Yok |
| **Ziyaret · Pencere · Bekleme** | Toplam ziyaret · aynı anda pencere (headful → 2-3 tut) · ziyaretler arası sn |
| **Çerez Klasörü** | Butona bas, SADQ çerezlerinin olduğu klasörü seç (varsayılan `cookies/`) |
| **Proxy** | Boş → her çerez kendi doğum proxy'siyle. Doldurursan hesaba sabit eşlenir |

**Başlat** → gerçek Chromium pencereleri açılır, canlı log + istatistik akar.
**Durdur** → düzgün durur. Sonuçlar `sonuclar.csv`'ye de yazılır.

## Çerezler

SADQ panelinden indirdiğin çerez `.json` dosyalarını **`cookies/`** klasörüne koy (veya "Çerez
Klasörü" ile başka klasör seç). Her hesap tek seferde bir kez kullanılır (leasing) + cooldown.

## Neden yerel daha iyi
VPS'te GPU yok → headful çöküyordu + patchright override'larımızı eziyordu. Mac/Windows'ta gerçek
ekran+GPU var, vanilla playwright ile override'lar **gerçekten** uygulanıyor → asıl undetect burada.

---
İleri: pencere yerine terminalden komutla da çalıştırılabilir (`python run.py` + `config.json`).
Web panel (clicker.ozicoin.dev) aynen duruyor — bu ona ek, bağımsız bir yerel araç.
