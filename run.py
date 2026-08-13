#!/usr/bin/env python3
"""click — YEREL (masaüstü) tık motoru.

VPS'te ENGELLENEN her şey BURADA çalışır:
  • HEADFUL (gerçek pencere, gerçek GPU) — Google/Cloudflare 'headless' tell'i YOK
  • VANILLA playwright — patchright override'ları ezmiyor → per-profil DE-KORELASYON
    (her hesap farklı canvas/WebGL/audio hash → toplu-ban zinciri kırılır), WebGL/deviceMemory
    spoof, CDP high-entropy Client Hints, seed'li gürültü — hepsi GERÇEKTEN uygulanır.

Kullanım:
  1) config.example.json'u 'config.json' yap ve doldur
  2) SADQ panelinden indirdiğin çerez JSON'larını cookies/ klasörüne koy
  3) python run.py
"""
import os
import sys
import csv
import json
import time
import signal
import asyncio

# Motoru ve headful'u ZORLA (clicker_core import'undan ÖNCE okunur)
os.environ.setdefault("CLICKER_ENGINE", "vanilla")
os.environ.setdefault("CLICKER_HEADFUL", "1")

from clicker_core import JobConfig, discover_cookie_files, run_click_job, scan_demographics_job, Stats  # noqa: E402
import demographics as demo_mod  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _read_lines(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


async def main():
    cfg_path = os.path.join(HERE, "config.json")
    if not os.path.exists(cfg_path):
        print("❌ config.json yok. 'config.example.json'u 'config.json' olarak kopyalayıp doldur.")
        return
    c = json.load(open(cfg_path, encoding="utf-8"))
    if not (c.get("keyword") or "").strip():
        print("❌ config.json → 'keyword' zorunlu.")
        return

    cookies_dir = os.path.join(HERE, c.get("cookies_dir", "cookies"))
    cookies = discover_cookie_files([cookies_dir])
    if not cookies:
        print(f"❌ '{cookies_dir}' içinde çerez yok. SADQ panelinden indirip .json olarak koy.")
        return
    proxies = _read_lines(os.path.join(HERE, "proxies.txt"))

    wl = c.get("white_urls", [])
    if isinstance(wl, str):
        wl = [x.strip() for x in wl.replace(",", "\n").splitlines() if x.strip()]

    cfg = JobConfig(
        keyword=c["keyword"].strip(),
        target_url=(c.get("target_url") or "").strip(),
        single_target=bool(c.get("single_target", False)),
        white_urls=wl,
        capsolver_api=(c.get("capsolver_api") or "").strip(),
        location=(c.get("location") or "Rastgele (Tüm Türkiye)"),
        total_visits=int(c.get("total_visits", 20)),
        concurrency=int(c.get("concurrency", 2)),
        cookie_source="upload",
        think_time=int(c.get("think_time", 20)),
        target_age=demo_mod.parse_target_ages(c.get("target_age", "")),
        target_gender=demo_mod.normalize_target_gender(c.get("target_gender", "")),
        max_clicks_per_account_day=int(c.get("max_clicks_per_account_day", 5)),
        max_clicks_per_ip_day=int(c.get("max_clicks_per_ip_day", 15)),
        target_cooldown_days=int(c.get("target_cooldown_days", 2)),
    )

    stats = Stats()
    stop = asyncio.Event()

    # 'python run.py --scan-demografi' → tık yerine demografi taraması yap (etiketsiz hesapları oku)
    if "--scan-demografi" in sys.argv or bool(c.get("scan_demografi", False)):
        results_path = os.path.join(HERE, "demografi_sonuc.csv")
        csv_f = open(results_path, "w", newline="", encoding="utf-8")
        writer = csv.writer(csv_f)
        writer.writerow(["saat", "hesap", "demografi", "kaynak"])

        def slog(m):
            print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

        def srecord(r):
            writer.writerow([time.strftime("%H:%M:%S"), r.get("account", ""),
                             r.get("demografi", ""), r.get("reason", "")])
            csv_f.flush()
        try:
            await scan_demographics_job(cookies, proxies, slog, stop, srecord)
        finally:
            csv_f.close()
        print(f"\nDemografi etiketleri .meta.json sidecar'larına yazıldı. Sonuç: {results_path}")
        return

    results_path = os.path.join(HERE, "sonuclar.csv")
    csv_f = open(results_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(csv_f)
    writer.writerow(["saat", "bot", "hesap", "demografi", "tiklanan_site", "durum", "sebep", "proxy"])

    def log(m):
        print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

    def record(r):
        writer.writerow([time.strftime("%H:%M:%S"), r.get("task_id", ""), r.get("account", ""),
                         r.get("demografi", ""), r.get("clicked", ""), r.get("status", ""),
                         r.get("reason", ""), r.get("proxy", "")])
        csv_f.flush()

    # Ctrl+C → graceful durdurma (workerlar çalışan ziyaretleri bitirir)
    def _sigint():
        log("⏹️ Durdurma istendi (Ctrl+C) — çalışan ziyaretler bitince duracak…")
        stop.set()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, _sigint)
    except (NotImplementedError, RuntimeError):
        pass

    mode = "tek-hedef" if cfg.single_target else "kelime-only(rakip)"
    log(f"▶️ click · kelime='{cfg.keyword}' · mod={mode} · {len(cookies)} çerez · "
        f"{len(proxies)} proxy · hedef {cfg.total_visits} · HEADFUL+VANILLA")
    try:
        await run_click_job(cfg, cookies, proxies, log, stats, stop, record)
    finally:
        csv_f.close()

    print(f"\n=== ÖZET: {stats.success} başarılı / {stats.fail} başarısız / "
          f"{stats.total_visits_done} ziyaret ===")
    print(f"Detaylı sonuçlar: {results_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDurduruldu.")
