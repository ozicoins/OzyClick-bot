#!/bin/bash
# macOS: çift tıkla → ilk seferde kurar (tamamlanma bayrağıyla), sonra GUI'yi açar.
cd "$(dirname "$0")"
if [ ! -f venv/.setup_ok ]; then
  echo "İlk kurulum (venv + Chromium) — birkaç dakika sürebilir…"
  python3 -m venv venv           || { echo "HATA: venv oluşturulamadı (Python 3 kurulu mu?)"; read -p "Enter ile kapat…"; exit 1; }
  # pip'i python -m pip ile yükselt + OPSIYONEL (başarısız olsa da devam — pip.exe/kilit sorunları kurulumu bloke etmesin)
  ./venv/bin/python -m pip install --upgrade pip  || echo "(pip güncellenemedi — önemsiz, devam)"
  ./venv/bin/python -m pip install -r requirements.txt  || { echo "HATA: bağımlılıklar kurulamadı"; read -p "Enter…"; exit 1; }
  ./venv/bin/python -m playwright install chromium || { echo "HATA: Chromium indirilemedi"; read -p "Enter…"; exit 1; }
  touch venv/.setup_ok
fi
exec ./venv/bin/python click_gui.py
