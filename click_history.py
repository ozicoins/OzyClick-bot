"""
click_history.py — KALICI tık defteri (SIVT agregat-desen savunması).

Google IVT'nin offline (SIVT) katmanı ~60 günü geriye tarayıp KÜMELER: aynı hesap/IP'den
yüksek velocity, tekrar eden aynı yolculuk, ani CTR sıçraması → geç iade/kredi. Tek bir tık
temiz olsa bile AGREGAT desen bot'u ele verir. Bu defter runlar ARASI kalıcıdır ve:
  • hesap-başı günlük tık tavanı,
  • IP(proxy)-başı günlük tık tavanı,
  • hesap↔hedef son-tıklama zamanı (aynı hesabın aynı rakibi tekrar tıklamasını yavaşlatmak)
tutar. ~60 günden eski kayıtlar budanır (Google'ın inceleme penceresi).

Not: tek asyncio döngüsünde çalışır (worker'lar tek event-loop) → dict için kilit gerekmez;
disk yazımı atomiktir (tmp+replace).
"""

import os
import json
import time
import logging

_DAY = 86400.0


class ClickLedger:
    def __init__(self, path, retain_days: int = 60):
        self.path = path
        self.retain = retain_days * _DAY
        self.data = {"accounts": {}, "proxies": {}}
        self._load()

    def _load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    self.data = {
                        "accounts": d.get("accounts") or {},
                        "proxies": d.get("proxies") or {},
                    }
        except Exception:
            self.data = {"accounts": {}, "proxies": {}}

    def save(self):
        """Atomik + dayanıklı yazım. Başarısızlıkta True/False döner (çağıran duraklatabilir #8)."""
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())     # disk'e gerçekten yaz (crash sonrası bayat state → cap ihlali)
            os.replace(tmp, self.path)
            return True
        except Exception as e:
            logging.getLogger("click_history").warning("ledger save başarısız: %s", e)
            return False

    @staticmethod
    def _count_since(lst, now, window):
        c = now - window
        return sum(1 for t in lst if t >= c)

    def account_clicks_today(self, acct, now=None):
        now = now or time.time()
        a = self.data["accounts"].get(acct)
        return self._count_since(a.get("clicks", []), now, _DAY) if a else 0

    def proxy_clicks_today(self, key, now=None):
        now = now or time.time()
        p = self.data["proxies"].get(key)
        return self._count_since(p.get("clicks", []), now, _DAY) if p else 0

    def target_recent(self, acct, domain, now=None, cooldown_days: float = 0):
        """Bu hesap bu hedefi cooldown_days içinde tıkladı mı? (tekrar-yolculuk yavaşlatma)"""
        if not domain or cooldown_days <= 0:
            return False
        now = now or time.time()
        a = self.data["accounts"].get(acct)
        if not a:
            return False
        last = (a.get("targets") or {}).get(domain, 0)
        return (now - last) < (cooldown_days * _DAY)

    def account_remaining(self, acct, cap, now=None):
        return max(0, int(cap) - self.account_clicks_today(acct, now))

    def proxy_remaining(self, key, cap, now=None):
        return max(0, int(cap) - self.proxy_clicks_today(key, now))

    def record(self, acct, proxy_key, domain, now=None):
        """BAŞARILI tık kaydı (yalnız success çağırmalı). save() sonucunu döndürür (#11: disk
        yazımı başarısızsa çağıran tık'ı durdurabilsin → bayat-state'ten cap ihlali olmasın)."""
        now = now or time.time()
        if acct:
            a = self.data["accounts"].setdefault(acct, {"clicks": [], "targets": {}})
            a.setdefault("clicks", []).append(now)
            if domain:
                a.setdefault("targets", {})[domain] = now
        if proxy_key:
            p = self.data["proxies"].setdefault(proxy_key, {"clicks": []})
            p.setdefault("clicks", []).append(now)
        self._prune(now)
        return self.save()

    def _prune(self, now):
        cutoff = now - self.retain
        for a in self.data["accounts"].values():
            a["clicks"] = [t for t in a.get("clicks", []) if t >= cutoff]
            tg = a.get("targets") or {}
            a["targets"] = {k: v for k, v in tg.items() if v >= cutoff}
        for p in self.data["proxies"].values():
            p["clicks"] = [t for t in p.get("clicks", []) if t >= cutoff]

    def capacity(self, accounts, acct_proxy_key, acct_cap, ip_cap, now=None,
                 target_dom="", cooldown_days=0):
        """Bugünkü toplam GÜVENLİ kapasite (effective_target) — SABİT hesap→proxy eşlemesine SAYGILI.
        Her hesap kendi sabit proxy'sine (acct_proxy_key(a) → görüntü-server; '' de bir grup) gider.
        Proxy'ye göre GRUPLA, grup başına min(grup-hesap-kalanı, proxy-IP-kalanı). target_dom+cooldown
        verilirse (tek-hedef), cooldown içinde o hedefi tıklamış hesap 0 sayılır (#4 over-count). Böylece
        effective_target ERİŞİLEBİLİR başarıyı AŞAMAZ. acct_cap/ip_cap sınırsızsa 10**9 geç."""
        now = now or time.time()
        # basename DEDUP: runtime ledger'ı basename ile anahtarlıyor → aynı basename'i çift sayma (Tur3 #7)
        uniq = {}
        for a in accounts:
            uniq.setdefault(os.path.basename(a), a)
        groups = {}   # proxy_key -> [account basename,...]
        for a in uniq.values():
            try:
                pk = acct_proxy_key(a) or ""
            except Exception:
                pk = ""
            groups.setdefault(pk, []).append(os.path.basename(a))

        def _acc_rem(bn):
            if target_dom and cooldown_days > 0 and self.target_recent(bn, target_dom, now, cooldown_days):
                return 0   # tek-hedef cooldown'da → bu hesap bugün erişilemez
            return self.account_remaining(bn, acct_cap, now)

        total = 0
        for pk, accs in groups.items():
            if not pk:
                continue   # PROXYSİZ (ne panel ne birth) → runtime FAIL-CLOSED → 0 kapasite (Tur3 #4/#9)
            acc_rem = sum(_acc_rem(bn) for bn in accs)
            if ip_cap < 10**9:
                total += min(acc_rem, self.proxy_remaining(pk, ip_cap, now))
            else:
                total += acc_rem   # IP-cap yok → sadece hesap sınırı
        return total
