# PANDUAN LENGKAP DEPLOYMENT KE PYTHONANYWHERE
## Sistem Simandiri CNN — POLMAN Smart Attendance & APD Inspection

Panduan langkah demi langkah ini dibuat agar seluruh fitur web (Dashboard Admin, Live Monitoring Kiosk, Biometrik Wajah, 4 Deteksi APD, Evaluasi Mahasiswa, dan Kamera Webcam) dapat berjalan lancar di PythonAnywhere persis seperti saat dijalankan di komputer lokal.

---

### Langkah 1: Buat Web App di PythonAnywhere
1. Buka dan login ke akun Anda di [PythonAnywhere](https://www.pythonanywhere.com/).
2. Klik tab **Web** di bagian atas menu.
3. Klik tombol **"Add a new web app"**.
4. Pada wizard:
   - Domain: Gunakan domain gratis bawaan (contoh: `username.pythonanywhere.com`).
   - Pilih Web Framework: Pilih **Manual configuration** *(PENTING: Jangan pilih Flask otomatis, pilih Manual configuration agar kita leluasa mengarahkan direktori repo)*.
   - Pilih Versi Python: Pilih **Python 3.10** (atau Python 3.11).
   - Klik **Next** sampai selesai.

---

### Langkah 2: Kloning / Upload Kode ke PythonAnywhere
1. Buka tab **Consoles**, lalu klik **Bash** untuk membuka terminal cloud Linux.
2. Di dalam console Bash, kloning repositori GitHub Anda:
   ```bash
   git clone https://github.com/USERNAME_GITHUB/NAMA_REPO.git Simandiri-CNN
   ```
   *(Atau jika menggunakan file ZIP, Anda bisa mengunggahnya lewat tab **Files** lalu mengekstraknya di folder `/home/username/Simandiri-CNN`)*.
3. Masuk ke direktori proyek:
   ```bash
   cd Simandiri-CNN
   ```

---

### Langkah 3: Instalasi Dependensi Ringan (Bebas Quota Limit)
Di terminal Bash PythonAnywhere, jalankan perintah instalasi berikut:
```bash
pip install --user -r requirements-pythonanywhere.txt
```

> **Mengapa menggunakan `requirements-pythonanywhere.txt`?**
> 1. Akun gratis PythonAnywhere memiliki batas memori disk 512 MB. Full TensorFlow berukuran >500 MB sehingga sering gagal instalasi. `tflite-runtime` hanya berukuran **~5 MB** dan sudah cukup untuk mengeksekusi ke-5 model TFLite kita.
> 2. Menggunakan `opencv-python-headless` agar tidak terjadi error `libGL.so.1 missing` pada server Linux tanpa GUI.
> 3. Jika paket `dlib` tidak sempat terkompilasi, sistem Simandiri CNN sudah dilengkapi **fallback otomatis** ke mode siluet panduan Kiosk, sehingga web server dijamin 100% stabil dan tidak akan crash.

---

### Langkah 4: Konfigurasi WSGI File
1. Buka kembali tab **Web** di dashboard PythonAnywhere.
2. Scroll ke bagian **Code**, lalu klik link biru pada **WSGI configuration file** (contoh: `/var/www/username_pythonanywhere_com_wsgi.py`).
3. Hapus seluruh baris teks yang ada di editor tersebut, lalu salin isi file [pythonanywhere_wsgi.py](pythonanywhere_wsgi.py) berikut:

```python
import os
import sys

# 1. Ganti USERNAME_ANDA dengan username PythonAnywhere Anda
USERNAME = "USERNAME_ANDA"
PROJECT_NAME = "Simandiri-CNN"

PROJECT_HOME = f"/home/{USERNAME}/{PROJECT_NAME}"

# 2. Masukkan folder proyek ke sys.path
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

# 3. Pindahkan working directory
os.chdir(PROJECT_HOME)

# 4. Import Flask application
from app import app as application

# 5. Pre-warm model AI TFLite ke memori
try:
    from kiosk_inference import warmup_models
    warmup_models()
except Exception as exc:
    print(f"[WSGI] Info warmup: {exc}")
```
4. Ganti teks `"USERNAME_ANDA"` dengan username akun PythonAnywhere Anda.
5. Klik tombol **Save** di pojok kanan atas.

---

### Langkah 5: Set Directory di Tab Web
Di tab **Web**, pastikan pengaturan direktori berikut terisi:
- **Source code**: `/home/USERNAME_ANDA/Simandiri-CNN`
- **Working directory**: `/home/USERNAME_ANDA/Simandiri-CNN`

---

### Langkah 6: Pemetaan Static Files (Agar Load Gambar Cepat)
Scroll ke bagian **Static files** di tab **Web**, lalu tambahkan 2 baris pemetaan berikut:

| URL | Directory |
| :--- | :--- |
| `/assets/` | `/home/USERNAME_ANDA/Simandiri-CNN/web/assets` |
| `/uploads/` | `/home/USERNAME_ANDA/Simandiri-CNN/web/uploads` |

*(Langkah ini membuat server Nginx PythonAnywhere menyajikan file CSS, JS, font, dan foto snapshot secara instan tanpa membebani thread Python)*.

---

### Langkah 7: Wajib Aktifkan "Force HTTPS" (Kunci Akses Webcam)
> **PENTING UNTUK KAMERA KIOSK:**  
> Browser modern (Google Chrome, Microsoft Edge, Mozilla Firefox) secara ketat **MEMBLOKIR** akses kamera webcam `getUserMedia()` jika website dibuka melalui protokol HTTP biasa yang tidak terenkripsi (hanya diizinkan di `localhost`).  
> 
> **Cara Mengaktifkannya:**
> 1. Di tab **Web**, scroll ke bagian **Security**.
> 2. Cari pengaturan **Force HTTPS**.
> 3. Ubah tombol toggle menjadi **Enabled**.
> 4. Sekarang website Anda memiliki sertifikat SSL gembok hijau resmi (`https://username.pythonanywhere.com`) dan webcam Kiosk akan langsung terbuka mulus tanpa dicekal browser!

---

### Langkah 8: Reload Web App
1. Di bagian paling atas tab **Web**, klik tombol hijau besar **"Reload username.pythonanywhere.com"**.
2. Buka link web Anda: `https://username.pythonanywhere.com`.
3. Selesai! Aplikasi Simandiri CNN Anda kini sudah live di internet.

---

### Kredensial Login Bawaan Sistem
- **Akun Administrator / Dosen / PLP**:
  - Username: `dosen01`
  - Password: `password123`
- **Akun Terminal Kiosk Presensi**:
  - Username: `kiosk01`
  - Password: `kiosk123`
- **Akun Mahasiswa**:
  - NIM: `224443009` *(Lukita)*, `224443003` *(Chakim)*, `224443012` *(Basit)*
  - Password: `password123`
