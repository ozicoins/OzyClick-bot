#!/usr/bin/env python3
"""click — masaüstü GUI (adswhite tarzı pencere + menü).
Headful + vanilla playwright → VPS'te engellenen her şey burada çalışır:
gerçek render, per-profil de-korelasyon, WebGL/deviceMemory spoof, davranış, leasing.

Çift tıkla: start.command (Mac) / start.bat (Windows) — venv + tarayıcıyı kurar, GUI'yi açar.
"""
import os
import csv
import sys
import time
import asyncio

# Motor + headful'u ZORLA (clicker_core import'undan ÖNCE)
os.environ.setdefault("CLICKER_ENGINE", "vanilla")
os.environ.setdefault("CLICKER_HEADFUL", "1")

HERE = os.path.dirname(os.path.abspath(__file__))

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QFileDialog, QFrame, QMessageBox,
)

from clicker_core import (
    JobConfig, discover_cookie_files, run_click_job, scan_demographics_job, Stats, TURKISH_CITIES,
)
import demographics as demo_mod


# ============================== BOT THREAD (asyncio + Qt) ==============================
class BotThread(QThread):
    log_signal = Signal(str)
    stat_signal = Signal(int, int, int)   # success, fail, total
    result_signal = Signal(dict)
    finished_signal = Signal()

    def __init__(self, cfg, cookies, proxies):
        super().__init__()
        self.cfg = cfg
        self.cookies = cookies
        self.proxies = proxies
        self._loop = None
        self._stop = None
        self._pending_stop = False
        self.stats = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.stats = Stats()
        self._stop = asyncio.Event()
        if self._pending_stop:          # loop kurulmadan Durdur'a basıldıysa (#29)
            self._stop.set()

        def log(m):
            self.log_signal.emit(str(m))

        def record(r):
            self.result_signal.emit(r)

        async def _stat_pump():
            while not self._stop.is_set():
                self.stat_signal.emit(self.stats.success, self.stats.fail, self.stats.total_visits_done)
                await asyncio.sleep(1)

        async def _main():
            if self._pending_stop:      # #16: kurulum sırasında Durdur'a basıldıysa (loop başlamadan) yakala
                self._stop.set()
            pump = asyncio.ensure_future(_stat_pump())
            try:
                await run_click_job(self.cfg, self.cookies, self.proxies, log, self.stats, self._stop, record)
            finally:
                self._stop.set()
                try:
                    await pump
                except Exception:
                    pass

        try:
            self._loop.run_until_complete(_main())
        except Exception as e:
            self.log_signal.emit(f"❌ Loop hatası: {e}")
        finally:
            self.stat_signal.emit(self.stats.success, self.stats.fail, self.stats.total_visits_done)
            try:
                self._loop.close()
            except Exception:
                pass
            self.finished_signal.emit()

    def stop(self):
        # Loop hazırsa thread-safe set; değilse pending bayrağı (run() kurunca uygular) — #29
        try:
            if self._loop and self._stop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._stop.set)
            else:
                self._pending_stop = True
        except Exception:
            self._pending_stop = True


class ScanThread(QThread):
    """Demografi taraması (ad-center okuyucu) — BotThread ile aynı asyncio/Qt deseni."""
    log_signal = Signal(str)
    result_signal = Signal(dict)
    finished_signal = Signal()

    def __init__(self, cookies, proxies):
        super().__init__()
        self.cookies = cookies
        self.proxies = proxies
        self._loop = None
        self._stop = None
        self._pending_stop = False

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop = asyncio.Event()
        if self._pending_stop:
            self._stop.set()

        def log(m):
            self.log_signal.emit(str(m))

        def record(r):
            self.result_signal.emit(r)

        async def _main():
            if self._pending_stop:      # #16: kurulum sırasında Durdur'a basıldıysa yakala
                self._stop.set()
            await scan_demographics_job(self.cookies, self.proxies, log, self._stop, record)

        try:
            self._loop.run_until_complete(_main())
        except Exception as e:
            self.log_signal.emit(f"❌ Tarama hatası: {e}")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self.finished_signal.emit()

    def stop(self):
        try:
            if self._loop and self._stop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._stop.set)
            else:
                self._pending_stop = True
        except Exception:
            self._pending_stop = True


# ============================== ANA PENCERE ==============================
DARK = """
QWidget { background:#0f141a; color:#e3ebf3; font-family:'Segoe UI','SF Pro Text',Arial; font-size:13px; }
QLabel#h1 { color:#2ee66b; font-size:18px; font-weight:800; }
QLabel.lbl { color:#8a97a6; font-size:11px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background:#0a0f14; border:1px solid #27333f; border-radius:7px; padding:6px 8px; color:#e3ebf3;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #37c9b0; }
QFrame#card { background:#141b24; border:1px solid #27333f; border-radius:12px; }
QPushButton { background:#1b2531; border:1px solid #27333f; border-radius:9px; padding:9px 16px; font-weight:700; }
QPushButton:hover { border:1px solid #37c9b0; }
QPushButton#start { background:#22c55e; color:#04120f; border:none; }
QPushButton#start:hover { background:#2ee66b; }
QPushButton#stop { background:#3a1f22; color:#ff6b6b; border:1px solid #6b2b2b; }
QCheckBox { color:#e3ebf3; }
QTextEdit#log { background:#05080b; font-family:'SF Mono','Consolas',monospace; font-size:12px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OzyClick — headful + de-korelasyon")
        self.resize(900, 760)
        self.bot = None
        self.scan = None
        self.cookies_dir = os.path.join(HERE, "cookies")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        title = QLabel("OzyClick")
        title.setObjectName("h1")
        root.addWidget(title)
        sub = QLabel("Yerel · HEADFUL (gerçek pencere) · vanilla (de-korelasyon çalışır)")
        sub.setProperty("class", "lbl")
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        # --- SOL: AYARLAR ---
        left = QFrame()
        left.setObjectName("card")
        lg = QGridLayout(left)
        lg.setContentsMargins(14, 14, 14, 14)
        lg.setVerticalSpacing(6)
        r = 0

        def add(label, w):
            nonlocal r
            lab = QLabel(label)
            lab.setProperty("class", "lbl")
            lg.addWidget(lab, r, 0, 1, 2)
            r += 1
            lg.addWidget(w, r, 0, 1, 2)
            r += 1

        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText("ör. uçak bileti")
        add("ANAHTAR KELİME *", self.keyword)

        self.target = QLineEdit()
        self.target.setPlaceholderText("kelime-only'de boş · tek-hedefte zorunlu (site.com)")
        add("HEDEF URL", self.target)

        self.single = QCheckBox("Tek hedef modu (sadece hedef domaine tıkla)")
        lg.addWidget(self.single, r, 0, 1, 2); r += 1

        self.white = QTextEdit()
        self.white.setPlaceholderText("benimsite.com\n# domain yeter → tüm alt-alan+path korunur")
        self.white.setFixedHeight(56)
        add("KENDİ/BEYAZ LİNKLER (ASLA tıklanmaz)", self.white)

        self.capsolver = QLineEdit()
        self.capsolver.setPlaceholderText("CAP-... (captcha için)")
        add("CAPSOLVER KEY", self.capsolver)

        self.location = QComboBox()
        self.location.addItem("Rastgele (Tüm Türkiye)")
        for city in ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana"]:
            self.location.addItem(city)
        self.location.addItem("Yok (kapalı)")
        add("LOKASYON (GPS)", self.location)

        # DEMOGRAFİ hedefleme — rakip kampanyanın hedef segmenti (hesap eşleşmezse reklam görünmez).
        drow = QHBoxLayout()
        self.gender = QComboBox()
        self.gender.addItem("Farketmez")
        self.gender.addItem("Kadın")
        self.gender.addItem("Erkek")
        self.age = QLineEdit()
        self.age.setPlaceholderText("boş=hepsi · ör. 25-34,35-44")
        for lab, w in [("Cinsiyet", self.gender), ("Hedef yaş", self.age)]:
            col = QVBoxLayout()
            l = QLabel(lab); l.setProperty("class", "lbl"); col.addWidget(l); col.addWidget(w)
            drow.addLayout(col)
        lab = QLabel("DEMOGRAFİ HEDEFİ (unknown olan elenir)"); lab.setProperty("class", "lbl")
        lg.addWidget(lab, r, 0, 1, 2); r += 1
        lg.addLayout(drow, r, 0, 1, 2); r += 1

        row = QHBoxLayout()
        self.total = QSpinBox(); self.total.setRange(1, 100000); self.total.setValue(20)
        self.conc = QSpinBox(); self.conc.setRange(1, 4); self.conc.setValue(2)   # headful → düşük tut (#25)
        self.think = QSpinBox(); self.think.setRange(3, 600); self.think.setValue(20)
        for lab, w in [("Ziyaret", self.total), ("Pencere", self.conc), ("Bekleme(sn)", self.think)]:
            col = QVBoxLayout()
            l = QLabel(lab); l.setProperty("class", "lbl"); col.addWidget(l); col.addWidget(w)
            row.addLayout(col)
        lg.addLayout(row, r, 0, 1, 2); r += 1

        # SIVT günlük tavanlar (kalıcı defter → iade-önleyici; düşük-ve-yavaş)
        row2 = QHBoxLayout()
        self.cap_acct = QSpinBox(); self.cap_acct.setRange(0, 1000); self.cap_acct.setValue(5)
        self.cap_ip = QSpinBox(); self.cap_ip.setRange(0, 10000); self.cap_ip.setValue(15)
        for lab, w in [("Hesap/gün (0=∞)", self.cap_acct), ("IP/gün (0=∞)", self.cap_ip)]:
            col = QVBoxLayout()
            l = QLabel(lab); l.setProperty("class", "lbl"); col.addWidget(l); col.addWidget(w)
            row2.addLayout(col)
        lab = QLabel("SIVT GÜNLÜK TAVAN (iade-önleyici)"); lab.setProperty("class", "lbl")
        lg.addWidget(lab, r, 0, 1, 2); r += 1
        lg.addLayout(row2, r, 0, 1, 2); r += 1

        # çerez klasörü
        ck = QHBoxLayout()
        self.cookie_lbl = QLabel("—")
        self.cookie_lbl.setProperty("class", "lbl")
        btn_ck = QPushButton("Çerez Klasörü")
        btn_ck.clicked.connect(self.pick_cookies)
        ck.addWidget(btn_ck); ck.addWidget(self.cookie_lbl, 1)
        lab = QLabel("ÇEREZLER"); lab.setProperty("class", "lbl")
        lg.addWidget(lab, r, 0, 1, 2); r += 1
        lg.addLayout(ck, r, 0, 1, 2); r += 1

        self.proxies = QTextEdit()
        self.proxies.setPlaceholderText("boş → her çerez kendi doğum proxy'siyle\nkullanici:parola@host:port")
        self.proxies.setFixedHeight(48)
        add("PROXY (satır satır, opsiyonel)", self.proxies)

        lg.setRowStretch(r, 1)
        body.addWidget(left, 0)

        # --- SAĞ: KONTROL + LOG ---
        right = QVBoxLayout()
        right.setSpacing(10)

        stat_card = QFrame(); stat_card.setObjectName("card")
        sc = QHBoxLayout(stat_card)
        self.s_ok = QLabel("0"); self.s_fail = QLabel("0"); self.s_tot = QLabel("0")
        for val, lab, color in [(self.s_ok, "Başarılı", "#34d399"), (self.s_fail, "Başarısız", "#ff6b6b"), (self.s_tot, "Ziyaret", "#37c9b0")]:
            col = QVBoxLayout()
            val.setStyleSheet(f"color:{color}; font-size:26px; font-weight:800;")
            val.setAlignment(Qt.AlignCenter)
            l = QLabel(lab); l.setProperty("class", "lbl"); l.setAlignment(Qt.AlignCenter)
            col.addWidget(val); col.addWidget(l)
            sc.addLayout(col)
        right.addWidget(stat_card)

        btns = QHBoxLayout()
        self.btn_start = QPushButton("▶  Başlat"); self.btn_start.setObjectName("start")
        self.btn_stop = QPushButton("■  Durdur"); self.btn_stop.setObjectName("stop"); self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        btns.addWidget(self.btn_start, 1); btns.addWidget(self.btn_stop, 1)
        right.addLayout(btns)

        # Demografi tara: hesapların yaş+cinsiyetini Google Ad Center'dan okuyup .meta.json'a yazar
        self.btn_scan = QPushButton("🔎  Demografi Tara (etiketsiz hesapları oku)")
        self.btn_scan.clicked.connect(self.scan_demografi)
        right.addWidget(self.btn_scan)

        self.log = QTextEdit(); self.log.setObjectName("log"); self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(3000)   # log sınırsız büyümesin (#26)
        right.addWidget(self.log, 1)

        body.addLayout(right, 1)

        self.refresh_cookies()
        self._log("Hazır. Çerez klasörünü seç, kelime gir, Başlat.")

    # ---- yardımcılar ----
    def pick_cookies(self):
        d = QFileDialog.getExistingDirectory(self, "Çerez Klasörü Seç", self.cookies_dir)
        if d:
            self.cookies_dir = d
            self.refresh_cookies()

    def refresh_cookies(self):
        n = len(discover_cookie_files([self.cookies_dir]))
        self.cookie_lbl.setText(f"{n} çerez · {self.cookies_dir}")

    def _log(self, m):
        from time import strftime
        self.log.append(f"<span style='color:#5d6b7a'>[{strftime('%H:%M:%S')}]</span> {m}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _stats(self, ok, fail, tot):
        self.s_ok.setText(str(ok)); self.s_fail.setText(str(fail)); self.s_tot.setText(str(tot))

    def _result(self, r):
        st = r.get("status", "")
        icon = {"success": "✅", "skipped": "⏭️", "scan": "🔎"}.get(st, "❌")
        clicked = r.get("clicked") or "—"
        dem = r.get("demografi", "")
        dtag = f" · <span style='color:#37c9b0'>{dem}</span>" if dem else ""
        self._log(f"{icon} <b>{r.get('account','')}</b>{dtag} → {clicked} · {r.get('reason','')}")
        w = getattr(self, "_csv_w", None)
        if w:
            try:
                w.writerow([time.strftime("%H:%M:%S"), r.get("task_id", ""), r.get("account", ""),
                            r.get("demografi", ""), r.get("clicked", ""), r.get("status", ""),
                            r.get("reason", ""), r.get("proxy", "")])
                self._csv_f.flush()
            except Exception:
                pass

    # ---- kontrol ----
    def start(self):
        if self.bot and self.bot.isRunning():
            return
        keyword = self.keyword.text().strip()
        if not keyword:
            QMessageBox.critical(self, "Eksik", "Anahtar kelime zorunlu.")
            return
        single = self.single.isChecked()
        target = self.target.text().strip()
        if single and not target:
            QMessageBox.critical(self, "Eksik", "Tek hedef modunda 'Hedef URL' zorunlu.")
            return
        cookies = discover_cookie_files([self.cookies_dir])
        if not cookies:
            QMessageBox.critical(self, "Çerez yok", f"'{self.cookies_dir}' içinde çerez yok.\nSADQ panelinden indirip koy.")
            return
        wl = [x.strip() for x in self.white.toPlainText().replace(",", "\n").splitlines() if x.strip() and not x.startswith("#")]
        proxies = [x.strip() for x in self.proxies.toPlainText().splitlines() if x.strip() and not x.startswith("#")]
        loc = self.location.currentText()
        if loc.startswith("Yok"):
            loc = ""       # GPS kapalı → boş geç (aşağıda 'loc or Rastgele' ile EZİLMEMELİ)
        tgender = demo_mod.normalize_target_gender(self.gender.currentText())
        tages = demo_mod.parse_target_ages(self.age.text().strip())
        cfg = JobConfig(
            keyword=keyword, target_url=target, single_target=single, white_urls=wl,
            capsolver_api=self.capsolver.text().strip(), location=loc,   # "Yok"→"" (kapalı) korunur
            total_visits=self.total.value(), concurrency=self.conc.value(),
            cookie_source="upload", think_time=self.think.value(),
            target_age=tages, target_gender=tgender,
            max_clicks_per_account_day=self.cap_acct.value(),
            max_clicks_per_ip_day=self.cap_ip.value(),
        )

        self.log.clear()
        # sonuclar.csv — GUI'de de yaz (#24)
        try:
            self._csv_f = open(os.path.join(HERE, "sonuclar.csv"), "w", newline="", encoding="utf-8")
            self._csv_w = csv.writer(self._csv_f)
            self._csv_w.writerow(["saat", "bot", "hesap", "demografi", "tiklanan_site", "durum", "sebep", "proxy"])
        except Exception:
            self._csv_f = None
            self._csv_w = None
        if not proxies:
            self._log("⚠️ Proxy girilmedi → doğum-proxy'si OLMAYAN çerezler ATLANIR (gerçek-IP koruması).")
        self._log(f"▶️ Başlıyor · {len(cookies)} çerez · {len(proxies)} proxy · headful+vanilla · "
                  f"{'tek-hedef' if single else 'kelime-only(rakip)'}")
        self.bot = BotThread(cfg, cookies, proxies)
        self.bot.log_signal.connect(self._log)
        self.bot.stat_signal.connect(self._stats)
        self.bot.result_signal.connect(self._result)
        self.bot.finished_signal.connect(self.on_finished)
        self.bot.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop(self):
        if self.bot and self.bot.isRunning():
            self._log("⏹️ Durduruluyor — çalışan ziyaretler bitince duracak…")
            self.bot.stop()
            self.btn_stop.setEnabled(False)
        if self.scan and self.scan.isRunning():
            self._log("⏹️ Tarama durduruluyor…")
            self.scan.stop()

    def scan_demografi(self):
        if (self.bot and self.bot.isRunning()) or (self.scan and self.scan.isRunning()):
            QMessageBox.warning(self, "Meşgul", "Zaten bir iş çalışıyor.")
            return
        cookies = discover_cookie_files([self.cookies_dir])
        if not cookies:
            QMessageBox.critical(self, "Çerez yok", f"'{self.cookies_dir}' içinde çerez yok.")
            return
        proxies = [x.strip() for x in self.proxies.toPlainText().splitlines() if x.strip() and not x.startswith("#")]
        if not proxies:
            r = QMessageBox.question(self, "Proxy yok",
                                     "Proxy girilmedi. Doğum-proxy'si olmayan hesaplar taranamaz "
                                     "(gerçek-IP koruması). Yine de devam?",
                                     QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        self.log.clear()
        self._log(f"🔎 Demografi taraması · {len(cookies)} hesap · yalnız etiketsizler okunur…")
        self.scan = ScanThread(cookies, proxies)
        self.scan.log_signal.connect(self._log)
        self.scan.result_signal.connect(self._result)
        self.scan.finished_signal.connect(self.on_scan_finished)
        self.scan.start()
        self.btn_scan.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def on_scan_finished(self):
        self._log("🔎 Tarama bitti. Artık hedef demografi girip Başlat'a basabilirsin.")
        self.btn_scan.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.refresh_cookies()

    def on_finished(self):
        self._log("🏁 İş bitti.")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        try:
            if getattr(self, "_csv_f", None):
                self._csv_f.close()
        except Exception:
            pass
        self._csv_w = None      # #17: bayat writer'a sonraki tarama yazmasın (kapalı dosyaya writerow)
        self._csv_f = None

    def closeEvent(self, event):
        # Non-blocking-ish: durdur, 4s bekle, bitmezse zorla sonlandır (GUI donmasın #12).
        for th in (self.bot, self.scan):
            if th and th.isRunning():
                th.stop()
                if not th.wait(4000):
                    try:
                        th.terminate()
                        th.wait(1000)
                    except Exception:
                        pass
        try:
            if getattr(self, "_csv_f", None):
                self._csv_f.close()
        except Exception:
            pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
