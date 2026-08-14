#!/usr/bin/env python3
"""click — masaüstü GUI (adswhite tarzı pencere + menü).
Headful + vanilla playwright → VPS'te engellenen her şey burada çalışır:
gerçek render, per-profil de-korelasyon, WebGL/deviceMemory spoof, davranış, leasing.

Çift tıkla: start.command (Mac) / start.bat (Windows) — venv + tarayıcıyı kurar, GUI'yi açar.
"""
import os
import csv
import json
import shutil
import sys
import time
import asyncio

# Motor + headful'u ZORLA (clicker_core import'undan ÖNCE)
os.environ.setdefault("CLICKER_ENGINE", "vanilla")
os.environ.setdefault("CLICKER_HEADFUL", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "gui_settings.json")   # tüm alanlar burada kalır (durmadan yazma yok)

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QFileDialog, QFrame, QMessageBox,
)

from clicker_core import (
    JobConfig, discover_cookie_files, run_click_job, scan_demographics_job, Stats, TURKISH_CITIES,
    _parse_proxy,
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
* { outline:none; }
QWidget { background:#0a0e15; color:#e6edf5; font-family:'Segoe UI','SF Pro Text',Arial; font-size:13px; }
QMainWindow, QDialog { background:#0a0e15; }
QLabel#h1 { color:#e6b450; font-size:19px; font-weight:800; letter-spacing:0.5px; }
QLabel.lbl { color:#7d8b9c; font-size:11px; font-weight:600; letter-spacing:0.3px; }

QLineEdit, QTextEdit, QComboBox, QSpinBox {
    background:#070b11; border:1px solid #1e2a38; border-radius:8px; padding:7px 9px; color:#e6edf5;
    selection-background-color:#37c9b0; selection-color:#04120f;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #37c9b0; background:#080d14; }
QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled { color:#4a5666; background:#0b1119; border:1px solid #16202b; }

/* Açılır menü (combo) — arkası SİYAH (beyaz değil) */
QComboBox::drop-down { border:none; width:22px; }
QComboBox::down-arrow { image:none; border-left:5px solid transparent; border-right:5px solid transparent; border-top:6px solid #7d8b9c; margin-right:8px; }
QComboBox QAbstractItemView {
    background:#0a0e15; color:#e6edf5; border:1px solid #1e2a38; border-radius:8px;
    selection-background-color:#15303a; selection-color:#37c9b0; outline:none; padding:4px;
}
QSpinBox::up-button, QSpinBox::down-button { width:18px; background:#111a25; border:none; border-radius:3px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background:#1a2735; }

QFrame#card { background:#0e151f; border:1px solid #1e2a38; border-radius:14px; }

QPushButton { background:#131c28; border:1px solid #24303e; border-radius:10px; padding:9px 16px; font-weight:700; color:#cdd8e4; }
QPushButton:hover { border:1px solid #37c9b0; color:#e6edf5; }
QPushButton:pressed { background:#0e1621; }
QPushButton#start { background:#22c55e; color:#04120f; border:none; }
QPushButton#start:hover { background:#2ee66b; }
QPushButton#stop { background:#2a1518; color:#ff7b7b; border:1px solid #5c2b2f; }
QPushButton#stop:hover { background:#3a1d20; }

QCheckBox { color:#cdd8e4; spacing:8px; }
QCheckBox::indicator { width:18px; height:18px; border:1px solid #24303e; border-radius:5px; background:#070b11; }
QCheckBox::indicator:checked { background:#37c9b0; border:1px solid #37c9b0; }

QTextEdit#log { background:#05080c; border:1px solid #14202c; font-family:'SF Mono','Consolas','Courier New',monospace; font-size:12px; color:#cbd6e2; }

QToolTip { background:#0e151f; color:#e6edf5; border:1px solid #37c9b0; border-radius:6px; padding:6px 8px; font-size:12px; }

QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
QScrollBar::handle:vertical { background:#24303e; border-radius:5px; min-height:24px; }
QScrollBar::handle:vertical:hover { background:#37c9b0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:transparent; height:10px; margin:2px; }
QScrollBar::handle:horizontal { background:#24303e; border-radius:5px; min-width:24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
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
        add("HEDEF URL", self.target)

        self.single = QCheckBox("Tek hedef modu (sadece bu URL'nin reklamına tıkla)")
        self.single.toggled.connect(self._on_single_toggled)
        lg.addWidget(self.single, r, 0, 1, 2); r += 1
        self._on_single_toggled(self.single.isChecked())   # başlangıç durumu (URL alanını ayarla)

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
        self.total.setToolTip("TOPLAM kaç tık yapılacak (iş bitene kadar). Ör. 20 = 20 ziyaret/tık.")
        self.conc = QSpinBox(); self.conc.setRange(1, 12); self.conc.setValue(6)   # GPU'lu PC (RTX 2060) → 6-8 rahat
        self.conc.setToolTip("AYNI ANDA kaç tarayıcı çalışsın (paralel).\n"
                             "GPU'lu PC (RTX 2060): 6-8 rahat çalışır (16GB RAM ile).\n"
                             "Kasarsa / RAM yetmezse düşür. GPU'suz laptop'ta 2-3 tut.")
        self.think = QSpinBox(); self.think.setRange(3, 600); self.think.setValue(20)
        self.think.setToolTip("İki tık arasında beklenecek saniye (insan gibi; düşük-yavaş = güvenli).")
        for lab, w in [("Toplam tık", self.total), ("Aynı anda (paralel)", self.conc), ("Tık arası (sn)", self.think)]:
            col = QVBoxLayout()
            l = QLabel(lab); l.setProperty("class", "lbl"); col.addWidget(l); col.addWidget(w)
            row.addLayout(col)
        lg.addLayout(row, r, 0, 1, 2); r += 1

        # Günlük güvenlik limiti — Google 'çok tık' (geçersiz-tık/SIVT) yakalamasın; düşük-ve-yavaş = tutulan tık.
        row2 = QHBoxLayout()
        self.cap_acct = QSpinBox(); self.cap_acct.setRange(0, 1000); self.cap_acct.setValue(5)
        self.cap_acct.setToolTip("Bir HESAP günde en fazla kaç kez tıklasın.\nDüşük tut (5-10) → Google 'bu hesap çok tıklıyor' demez.\n0 = sınırsız (riskli).")
        self.cap_ip = QSpinBox(); self.cap_ip.setRange(0, 10000); self.cap_ip.setValue(15)
        self.cap_ip.setToolTip("Bir PROXY/IP günde en fazla kaç kez tıklasın.\nDüşük tut (10-20) → Google 'bu IP çok tıklıyor' demez.\n0 = sınırsız (riskli).")
        for lab, w in [("Bir hesap · günde max tık", self.cap_acct), ("Bir proxy · günde max tık", self.cap_ip)]:
            col = QVBoxLayout()
            l = QLabel(lab); l.setProperty("class", "lbl"); col.addWidget(l); col.addWidget(w)
            row2.addLayout(col)
        lab = QLabel("GÜNLÜK GÜVENLİK LİMİTİ  —  Google 'çok tık' yakalamasın (az = güvenli)")
        lab.setProperty("class", "lbl")
        lab.setToolTip("Aynı hesabı/IP'yi günde çok kez tıklatmak Google'ın geçersiz-tık filtresini (SIVT) tetikler ve\n"
                       "tıklar sonradan İADE olur. Bu iki limit günlük tık sayısını düşük tutar → 'düşük ve yavaş' = tutulan tık.")
        lg.addWidget(lab, r, 0, 1, 2); r += 1
        lg.addLayout(row2, r, 0, 1, 2); r += 1

        # çerezler: KLASÖR seç VEYA tek tek DOSYA ekle
        ck = QHBoxLayout()
        self.cookie_lbl = QLabel("—")
        self.cookie_lbl.setProperty("class", "lbl")
        btn_ck = QPushButton("📁 Klasör")
        btn_ck.setToolTip("Çerez .json dosyalarının olduğu KLASÖRÜ seç")
        btn_ck.clicked.connect(self.pick_cookies)
        btn_cf = QPushButton("➕ Dosya Ekle")
        btn_cf.setToolTip("Tek tek çerez .json dosyası seç → çerez klasörüne kopyalanır")
        btn_cf.clicked.connect(self.add_cookie_files)
        ck.addWidget(btn_ck); ck.addWidget(btn_cf); ck.addWidget(self.cookie_lbl, 1)
        lab = QLabel("ÇEREZLER  (SADQ panelinden indir → klasör seç ya da dosya ekle)"); lab.setProperty("class", "lbl")
        lg.addWidget(lab, r, 0, 1, 2); r += 1
        lg.addLayout(ck, r, 0, 1, 2); r += 1

        self.proxies = QTextEdit()
        self.proxies.setPlaceholderText(
            "Her satıra 1 proxy:\n"
            "  ip:port                    →  1.2.3.4:8080\n"
            "  kullanıcı:parola@ip:port   →  user:pass@1.2.3.4:8080\n"
            "  [IPv6]:port                →  [2a01:4f8::1]:8080\n"
            "Boş bırak → her çerez KENDİ doğum proxy'siyle çıkar (önerilen)."
        )
        self.proxies.setFixedHeight(78)
        add("PROXY  (satır satır · ip:port  ya da  kullanıcı:parola@ip:port · opsiyonel)", self.proxies)

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

        self._load_settings()          # kayıtlı ayarları geri yükle (durmadan yazma yok)
        self.refresh_cookies()
        self._log("Hazır. Ayarların hatırlandı. Çerez ekle, kelime gir, Başlat.")

    # ---- yardımcılar ----
    def pick_cookies(self):
        d = QFileDialog.getExistingDirectory(self, "Çerez Klasörü Seç", self.cookies_dir)
        if d:
            self.cookies_dir = d
            self.refresh_cookies()

    def add_cookie_files(self):
        # Tek tek çerez .json dosyası seç → çerez klasörüne kopyala (klasör seçmeye gerek kalmadan).
        files, _ = QFileDialog.getOpenFileNames(self, "Çerez Dosyaları Seç", self.cookies_dir, "Çerez dosyası (*.json)")
        if not files:
            return
        try:
            os.makedirs(self.cookies_dir, exist_ok=True)
        except Exception:
            pass
        added = 0
        for f in files:
            try:
                dst = os.path.join(self.cookies_dir, os.path.basename(f))
                if os.path.abspath(f) != os.path.abspath(dst):
                    shutil.copy2(f, dst)
                added += 1
            except Exception as e:
                self._log(f"⚠️ kopyalanamadı: {os.path.basename(f)} ({str(e)[:40]})")
        self._log(f"➕ {added} çerez dosyası eklendi → {self.cookies_dir}")
        self.refresh_cookies()

    def _on_single_toggled(self, on):
        # Tek-hedef AÇIK → HEDEF URL alanı aktif + odak (bu URL'nin reklamına tıklanır).
        # KAPALI (kelime-only) → URL alanı pasif/soluk (kullanılmaz; whitelist DIŞI rakip reklama tıklanır).
        self.target.setEnabled(on)
        if on:
            self.target.setPlaceholderText("bu sitenin reklamına tıkla  →  site.com")
            self.target.setFocus()
        else:
            self.target.setPlaceholderText("kelime-only modunda gerekmez (rakip reklama tıklanır)")

    def refresh_cookies(self):
        n = len(discover_cookie_files([self.cookies_dir]))
        self.cookie_lbl.setText(f"{n} çerez · {self.cookies_dir}")

    # ---- ayar kalıcılığı (durmadan yazma yok) ----
    def _collect_settings(self):
        return {
            "keyword": self.keyword.text(), "target": self.target.text(),
            "single": self.single.isChecked(), "white": self.white.toPlainText(),
            "capsolver": self.capsolver.text(), "location": self.location.currentText(),
            "gender": self.gender.currentText(), "age": self.age.text(),
            "total": self.total.value(), "conc": self.conc.value(), "think": self.think.value(),
            "cap_acct": self.cap_acct.value(), "cap_ip": self.cap_ip.value(),
            "cookies_dir": self.cookies_dir, "proxies": self.proxies.toPlainText(),
        }

    def _apply_settings(self, d):
        try:
            self.keyword.setText(d.get("keyword", ""))
            self.target.setText(d.get("target", ""))
            self.single.setChecked(bool(d.get("single", False)))   # → _on_single_toggled tetiklenir
            self.white.setPlainText(d.get("white", ""))
            self.capsolver.setText(d.get("capsolver", ""))
            if d.get("location"):
                self.location.setCurrentText(d["location"])
            if d.get("gender"):
                self.gender.setCurrentText(d["gender"])
            self.age.setText(d.get("age", ""))
            for key, w in (("total", self.total), ("conc", self.conc), ("think", self.think),
                           ("cap_acct", self.cap_acct), ("cap_ip", self.cap_ip)):
                v = d.get(key)
                if isinstance(v, int):
                    w.setValue(v)
            cd = d.get("cookies_dir")
            if cd and os.path.isdir(cd):
                self.cookies_dir = cd
            self.proxies.setPlainText(d.get("proxies", ""))
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._collect_settings(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._apply_settings(json.load(f))
        except Exception:
            pass

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
        # Proxy biçim ön-kontrolü: çözülemeyen satırları uyar (biçim: ip:port / kullanıcı:parola@ip:port / [IPv6]:port).
        bad = [p for p in proxies if _parse_proxy(p) is None]
        if bad:
            if QMessageBox.warning(
                self, "Proxy biçimi",
                f"{len(bad)} proxy satırı çözülemedi.\nDoğru biçim: ip:port  ya da  kullanıcı:parola@ip:port\n"
                f"Hatalı örnek: {bad[0][:48]}\n\nBu satırlar ATLANIR (o ziyaretler güvenle atlanır, gerçek-IP sızmaz). Yine de başlansın mı?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
        loc = self.location.currentText()
        if loc.startswith("Yok"):
            loc = ""       # GPS kapalı → boş geç (aşağıda 'loc or Rastgele' ile EZİLMEMELİ)
        tgender = demo_mod.normalize_target_gender(self.gender.currentText())
        tages = demo_mod.parse_target_ages(self.age.text().strip())
        self._save_settings()          # başlatınca ayarları kaydet (bir dahaki açılışta hazır gelir)
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
        self._save_settings()          # kapanışta ayarları kaydet (bir dahaki açılışta hatırlanır)
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
