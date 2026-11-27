# ======================================================================================
# WSGI CONFIGURATION FILE UNTUK PYTHONANYWHERE
# ======================================================================================
# Cara Penggunaan di PythonAnywhere:
# 1. Masuk ke dashboard PythonAnywhere (https://www.pythonanywhere.com/).
# 2. Masuk ke tab "Web".
# 3. Klik link "WSGI configuration file" (contoh: /var/www/username_pythonanywhere_com_wsgi.py).
# 4. Hapus seluruh isi defaultnya, lalu salin isi file ini ke dalamnya.
# 5. Ganti 'NAMA_USERNAME_ANDA' di bawah dengan username akun PythonAnywhere Anda.
# 6. Klik "Save", lalu kembali ke tab "Web" dan klik tombol hijau "Reload".
# ======================================================================================

import os
import sys

# 1. Tentukan username dan folder proyek Anda di PythonAnywhere
USERNAME = "NAMA_USERNAME_ANDA"  # <-- GANTI DENGAN USERNAME PYTHONANYWHERE ANDA
PROJECT_NAME = "Simandiri-CNN"   # <-- GANTI JIKA NAMA FOLDER REPO ANDA BERBEDA

PROJECT_HOME = f"/home/{USERNAME}/{PROJECT_NAME}"

# 2. Masukkan folder proyek ke dalam Python Path
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

# 3. Set direktori kerja (working directory) ke folder proyek
os.chdir(PROJECT_HOME)

# 4. Import instance Flask utama sebagai 'application' (standar WSGI)
from app import app as application

# 5. Pre-warm model TFLite agar respon Kiosk instan pada permintaan pertama
try:
    from kiosk_inference import warmup_models
    warmup_models()
except Exception as exc:
    print(f"[WSGI] Info warmup: {exc}")
