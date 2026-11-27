"""
========================================================================================
SIMANDIRI CNN - POLMAN SMART ATTENDANCE & APD INSPECTION
TAHAP 1 & TAHAP 2: PENGUMPULAN DATA & PERSIAPAN DATASET (DATA PREPARATION & SMART CROPPING)
========================================================================================

Dokumentasi & Alur Algoritma:
----------------------------------------------------------------------------------------
1. LATAR BELAKANG MASALAH:
   - Jika citra dipotong menggunakan koordinat statis/tetap (misal x: 200-400, y: 100-300):
     * Saat mahasiswa berdiri maju/mundur, kotak potong akan meleset memotong tembok/plafon kosong.
     * Saat mahasiswa posisi duduk/setengah badan, koordinat bawah akan memotong meja/paha
       dan salah dikenali sebagai celana jeans atau sepatu.
     * Tembok putih polos laboratorium bisa ikut tersimpan dan mengacaukan proses training CNN.

2. SOLUSI - ADAPTIVE FACE-ANCHORED CROPPING:
   - Deteksi kepala/wajah mahasiswa secara dinamis menggunakan dlib HOG sebagai JANGKAR ANATOMIS.
   - Koordinat bounding box Helm, Baju Praktik, Celana Jeans, dan Sepatu Safety dihitung
     secara proporsional terhadap ukuran wajah (lebar wajah fw, tinggi wajah fh, dan pusat horizontal cx).
   - Pengenalan otomatis pose duduk / setengah badan (is_half_body): jika dagu berada di bawah
     38% tinggi frame (fy1 > 0.38*h), jeans dan sepatu otomatis DIABAIKAN (tidak memotong meja).
   - Filter Kualitas Variansi Citra (std >= 14.0): membuang potongan tembok putih polos atau ruang gelap.
   - Deteksi Kontur Warna Oranye HSV: mengunci helm K3 POLMAN secara presisi pada ruang warna HSV.
   - Hard Negative Mining: menyuntikkan sampel latar belakang lab (lantai, meja) dan foto silang
     antar-bagian tubuh ke kelas 'tidak' agar model tahan terhadap salah deteksi.

3. STRUKTUR OUTPUT DATASET:
   - dataset_area/
       ├── helm/   {pakai/, tidak/}   (citra RGB 96x96)
       ├── baju/   {pakai/, tidak/}   (citra RGB 128x128)
       ├── jeans/  {pakai/, tidak/}   (citra RGB 128x128)
       ├── sepatu/ {pakai/, tidak/}   (citra RGB 128x128)
       ├── preview/                   (visualisasi kotak potong warna-warni)
       └── labels.csv                 (riwayat metadata pemotongan)
   - dataset_wajah/
       ├── Basit/  (citra RGB 128x128 crop ketat dahi & dagu)
       ├── Chakim/ (citra RGB 128x128 crop ketat dahi & dagu)
       └── Luki/   (citra RGB 128x128 crop ketat dahi & dagu)

4. CARA PENGGUNAAN (CLI):
   - python siapkan_dataset.py --clean          # Bersihkan folder lama & proses ulang dari awal
   - python siapkan_dataset.py --skip-wajah     # Hanya memproses 4 area APD tanpa mengulang wajah
========================================================================================
"""
import argparse
import csv
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

# Inisialisasi Detektor Wajah dlib HOG
try:
    import dlib
    DETEKTOR_WAJAH = dlib.get_frontal_face_detector()
except ImportError:
    DETEKTOR_WAJAH = None

# ======================================================================================
# PEMETAAN LABEL FOLDER MENTAH (GROUND TRUTH MAPPING)
# Format Tuple: (helm, baju, jeans, sepatu)
# Nilai:
#   1    = Memakai APD standar POLMAN (Positif)
#   0    = Tidak memakai / memakai atribut salah (Negatif)
#   None = Bagian tubuh tidak tampak di frame (Duduk / Setengah Badan) -> JANGAN DIPOTONG!
# ======================================================================================
LABEL_FOLDER = {
    # 1. Full Seragam Lengkap (Semua APD Pakai)
    "Full seragam":            (1, 1, 1, 1),

    # 2. Kombinasi APD Pakai Sebagian (Diambil saat posisi duduk / setengah badan)
    "Hanya Helm":              (1, 0, None, None),
    "Hanya Helm dan Kemeja":   (1, 1, None, None),
    "Hanya Kemeja dan Jeans":  (0, 1, 1, 0),
    "Hanya Jeans dan Sepatu":  (0, 0, 1, 1),

    # 3. Kombinasi Pelanggaran / Atribut Non-Standar
    "Salah Helm":              (0, 1, 1, 1),
    "Salah Kemeja":            (1, 0, 1, 1),
    "Salah Celana dan Sepatu": (None, None, 0, 0),
    "Salah Celana":            (None, None, 0, 0),
    "Salah Helm & kemeja":     (0, 0, 1, 1),
    "Salah Sepatu":            (1, 1, 1, 0),
    "Salah Sepatu & Helm":     (0, 1, 1, 0),
    "Salah Sepatu & Kemeja":   (1, 0, 1, 0),
    "Hanya Jeans":             (0, 0, 1, 0),

    # 4. Folder legacy / nama alternatif:
    "Tanpa Helm":              (0, 1, 1, 1),
    "Tanpa Kemeja":            (1, 0, 1, 1),
    "Tanpa sepatu":            (1, 1, 1, 0),
    "Tanpa Sepatu & Helm":     (0, 1, 1, 0),
    "Tanpa Sepatu & Kemeja":   (1, 0, 1, 0),
    "Tanpa Helm & kemeja":     (0, 0, 1, 1),
}

ITEM = ["helm", "baju", "jeans", "sepatu"]
ITEM_DILATIH = ["helm", "baju", "jeans", "sepatu"]

# Ukuran target input model CNN dalam format RGB (lebar, tinggi)
UKURAN = {
    "helm":   (96, 96),     # Helm cukup 96x96 agar komputasi ringan
    "baju":   (128, 128),   # Butuh 128x128 untuk menangkap detail kerah & kancing
    "jeans":  (128, 128),   # Butuh 128x128 untuk tekstur denim
    "sepatu": (128, 128),   # Butuh 128x128 untuk moncong keras & sol sepatu safety
    "wajah":  (128, 128),   # Resolusi optimal klasifikasi biometrik MobileNetV2
}

# Standar deviasi minimal intensitas piksel grayscale (std >= 14.0)
# Digunakan untuk mengeliminasi potongan tembok polos, plafon, atau bayangan hitam pekat
STD_MIN_VALID = 14.0

EKSTENSI = {".jpg", ".jpeg", ".png", ".bmp"}


def cari_label(nama_folder):
    for nama, label in LABEL_FOLDER.items():
        if nama.lower() == nama_folder.lower():
            return label
    return None


def adalah_waist_down(folder_name, file_path):
    fn = folder_name.lower()
    if "salah celana" in fn:
        return True
    if fn == "salah sepatu" and "20261117" in file_path.name:
        return True
    return False


def deteksi_wajah(img):
    """
    Deteksi wajah cepat menggunakan HOG (Histogram of Oriented Gradients) dari dlib.
    Menggunakan penskalaan adaptif agar komputasi ringan dan cepat.
    
    Output: Koordinat bounding box wajah skala asli (fx0, fy0, fx1, fy1)
    """
    if DETEKTOR_WAJAH is None:
        return None
    h, w = img.shape[:2]
    # Jika resolusi gambar besar (>960px), resize sementara agar detektor HOG dlib cepat
    scale = 960.0 / w if w > 960 else 1.0
    sw, sh = int(w * scale), int(h * scale)
    small = cv2.resize(img, (sw, sh))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

    # Deteksi wajah (tahap 0 kecepatan tinggi, jika belum ketemu upsample tahap 1)
    rects = DETEKTOR_WAJAH(rgb, 0)
    if not rects:
        rects = DETEKTOR_WAJAH(rgb, 1)
    if not rects:
        return None

    # Pilih wajah terbesar (orang utama di depan kamera, abaikan orang lewat di belakang)
    r = max(rects, key=lambda b: b.width() * b.height())
    
    # Kembalikan koordinat bounding box ke resolusi citra asli
    return (
        int(r.left() / scale),
        int(r.top() / scale),
        int(r.right() / scale),
        int(r.bottom() / scale)
    )


def potong_area_adaptif(img, folder_name, file_path, label):
    """
    Jantung Algoritma Tahap 2: Adaptive Face-Anchored Cropping.
    
    Prinsip Kerja:
    1. Mencari wajah sebagai jangkar tubuh. Jika wajah ditemukan:
       - Lebar wajah (fw) dan tinggi wajah (fh) menjadi satuan acuan proporsi anatomi tubuh.
       - Titik tengah horizontal wajah (cx) menjadi sumbu simetri tubuh (garis tengah).
    2. Deteksi Pose Setengah Badan / Duduk (is_half_body):
       - Jika dagu fy1 > 0.38*h, berarti mahasiswa sedang duduk / setengah badan.
       - Celana jeans dan sepatu safety OTOMATIS DIABAIKAN agar meja/paha tidak terpotong!
    3. Deteksi Helm Cerdas (Smart HSV Contour):
       - Khusus kelas pakai (h_lbl == 1), kontur warna oranye helm K3 dicari terlebih dahulu.
    4. Filter Kualitas Citra:
       - Setiap potongan wajib memiliki variansi std >= 14.0 dan mean < 195 agar tembok
         putih polos atau lampu plafon lab tidak masuk ke dataset.
    """
    h, w = img.shape[:2]
    face = deteksi_wajah(img)
    hasil = {}
    kotak = {}

    h_lbl, b_lbl, j_lbl, s_lbl = label

    if face is not None:
        fx0, fy0, fx1, fy1 = face
        fw, fh = fx1 - fx0, fy1 - fy0
        cx = (fx0 + fx1) // 2
        # Deteksi apakah mahasiswa sedang duduk / setengah badan di depan webcam
        is_half_body = (fy1 > 0.38 * h)

        # ----------------------------------------------------------------------
        # 1. PEMOTONGAN AREA HELM K3
        # ----------------------------------------------------------------------
        if h_lbl is not None:
            helm_found = False
            # Jika kelas pakai (1), prioritaskan deteksi kontur warna oranye helm K3
            if h_lbl == 1:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                # Rentang warna oranye helm keselamatan di ruang HSV
                orange_mask = cv2.inRange(hsv, (7, 80, 80), (25, 255, 255))
                cnts, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                head_cnts = []
                for c in cnts:
                    if cv2.contourArea(c) < 350:
                        continue
                    bx, by, bw, bh = cv2.boundingRect(c)
                    # Pastikan kontur oranye berada di atas dahi dan sejajar sumbu tengah wajah cx
                    if abs((bx + bw // 2) - cx) < fw * 0.9 and by < fy1 and (by + bh) > (fy0 - int(fh * 1.1)):
                        head_cnts.append(c)
                if head_cnts:
                    best_c = max(head_cnts, key=cv2.contourArea)
                    bx, by, bw, bh = cv2.boundingRect(best_c)
                    # Beri margin 12% agar lengkungan helm terpotong utuh
                    pad_w = int(bw * 0.12)
                    pad_h = int(bh * 0.12)
                    hx0 = max(0, bx - pad_w)
                    hy0 = max(0, by - pad_h)
                    hx1 = min(w, bx + bw + pad_w)
                    hy1 = min(h, by + bh + pad_h)
                    crop = img[hy0:hy1, hx0:hx1]
                    if crop.size > 0 and np.mean(crop) < 195:
                        hasil["helm"] = crop
                        kotak["helm"] = (hx0, hy0, hx1, hy1)
                        helm_found = True

            # Jika bukan helm oranye atau kelas 'tidak pakai helm', potong area tepat di atas dahi
            if not helm_found:
                hy0 = max(0, fy0 - int(fh * 0.85))
                hy1 = min(h, fy0 + int(fh * 0.25))
                hx0 = max(0, cx - int(fw * 0.75))
                hx1 = min(w, cx + int(fw * 0.75))
                if hy1 > hy0 + 20 and hx1 > hx0 + 20:
                    crop = img[hy0:hy1, hx0:hx1]
                    # Filter variansi & kecerahan agar tidak menyimpan plafon lab putih kosong
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID and np.mean(crop) < 195:
                        hasil["helm"] = crop
                        kotak["helm"] = (hx0, hy0, hx1, hy1)

        # ----------------------------------------------------------------------
        # 2. PEMOTONGAN AREA BAJU PRAKTIK
        # ----------------------------------------------------------------------
        if b_lbl is not None:
            # Dari tepat di bawah dagu (fy1 - 0.15*fh) hingga ke batas dada/perut
            by0 = max(0, fy1 - int(fh * 0.15))
            by1 = min(h, fy1 + int(fh * (2.2 if is_half_body else 2.8)))
            bx0 = max(0, cx - int(fw * 1.5))
            bx1 = min(w, cx + int(fw * 1.5))
            if by1 > by0 + 20 and bx1 > bx0 + 20:
                crop = img[by0:by1, bx0:bx1]
                # Filter kualitas variansi piksel (harus bertekstur kain baju, bukan tembok)
                if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                    hasil["baju"] = crop
                    kotak["baju"] = (bx0, by0, bx1, by1)

        # ----------------------------------------------------------------------
        # 3 & 4. PEMOTONGAN AREA JEANS & SEPATU SAFETY (Hanya Jika Berdiri Penuh)
        # ----------------------------------------------------------------------
        if not is_half_body:
            # CELANA JEANS: Dari batas pinggang hingga di bawah lutut
            if j_lbl is not None:
                jy0 = min(h, fy1 + int(fh * 2.8))
                jy1 = min(h, fy1 + int(fh * 6.2))
                jx0 = max(0, cx - int(fw * 1.3))
                jx1 = min(w, cx + int(fw * 1.3))
                if jy1 > jy0 + 20 and jx1 > jx0 + 20:
                    crop = img[jy0:jy1, jx0:jx1]
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                        hasil["jeans"] = crop
                        kotak["jeans"] = (jx0, jy0, jx1, jy1)

            # SEPATU SAFETY: Dari pergelangan kaki hingga menyentuh lantai
            if s_lbl is not None:
                sy0 = min(h, fy1 + int(fh * 5.8))
                sy1 = h
                sx0 = max(0, cx - int(fw * 1.3))
                sx1 = min(w, cx + int(fw * 1.3))
                if sy1 > sy0 + 20 and sx1 > sx0 + 20:
                    crop = img[sy0:sy1, sx0:sx1]
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                        hasil["sepatu"] = crop
                        kotak["sepatu"] = (sx0, sy0, sx1, sy1)

    else:
        # Fallback jika wajah tidak terdeteksi (misal foto khusus kaki ke bawah / waist-down)
        if adalah_waist_down(folder_name, file_path):
            lebar = int(w * 0.34)
            x0 = (w - lebar) // 2
            x1 = x0 + lebar
            if j_lbl is not None:
                jy0, jy1 = int(h * 0.10), int(h * 0.70)
                crop = img[jy0:jy1, x0:x1]
                if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                    hasil["jeans"] = crop
                    kotak["jeans"] = (x0, jy0, x1, jy1)
            if s_lbl is not None:
                sy0, sy1 = int(h * 0.68), int(h * 1.00)
                crop = img[sy0:sy1, x0:x1]
                if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                    hasil["sepatu"] = crop
                    kotak["sepatu"] = (x0, sy0, x1, sy1)
        else:
            # Fallback umum: Cari kontur oranye di seluruh frame (untuk helm)
            if h_lbl == 1:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                orange_mask = cv2.inRange(hsv, (7, 80, 80), (25, 255, 255))
                cnts, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                valid_cnts = [c for c in cnts if cv2.contourArea(c) > 600]
                if valid_cnts:
                    best_c = max(valid_cnts, key=cv2.contourArea)
                    bx, by, bw, bh = cv2.boundingRect(best_c)
                    pad_w = int(bw * 0.15)
                    pad_h = int(bh * 0.15)
                    hx0 = max(0, bx - pad_w)
                    hy0 = max(0, by - pad_h)
                    hx1 = min(w, bx + bw + pad_w)
                    hy1 = min(h, by + bh + pad_h)
                    crop = img[hy0:hy1, hx0:hx1]
                    if crop.size > 0 and np.mean(crop) < 195:
                        hasil["helm"] = crop
                        kotak["helm"] = (hx0, hy0, hx1, hy1)

            # Fallback proporsi vertikal tengah frame
            lebar = int(w * 0.30)
            x0 = (w - lebar) // 2
            x1 = x0 + lebar
            area_cfg = {
                "helm":   (0.05, 0.28),
                "baju":   (0.22, 0.58),
                "jeans":  (0.48, 0.86),
                "sepatu": (0.78, 1.00),
            }
            for it, v in zip(ITEM, label):
                if v is not None and it in area_cfg and it not in hasil:
                    a, b = area_cfg[it]
                    y0, y1 = int(h * a), int(h * b)
                    crop = img[y0:y1, x0:x1]
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID and np.mean(crop) < 195:
                        hasil[it] = crop
                        kotak[it] = (x0, y0, x1, y1)

    return hasil, kotak

    return hasil, kotak


def deteksi_kotak_wajah(img):
    """
    Crop ketat area wajah saja untuk model biometrik wajah (Basit, Chakim, Luki).
    
    Catatan Geometri:
    - Margin dahi sedikit diperlebar (+5%) untuk menangkap garis rambut.
    - Dagu dipotong SANGAT KETAT (-2%) agar kerah baju atau jaket TIDAK IKUT MASUK,
      sehingga model wajah tidak menghafal warna baju mahasiswa saat berganti pakaian.
    """
    if DETEKTOR_WAJAH is None:
        raise SystemExit("dlib tidak terpasang; dibutuhkan untuk detektor HOG crop wajah.")
    h, w = img.shape[:2]
    scale = 960.0 / w if w > 960 else 1.0
    sw, sh = int(w * scale), int(h * scale)
    small = cv2.resize(img, (sw, sh))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    rects = DETEKTOR_WAJAH(rgb, 0)
    if not rects:
        rects = DETEKTOR_WAJAH(rgb, 1)
    if not rects:
        return None
    r = max(rects, key=lambda b: b.width() * b.height())
    fx0, fy0, fx1, fy1 = (
        int(r.left() / scale),
        int(r.top() / scale),
        int(r.right() / scale),
        int(r.bottom() / scale)
    )
    fw, fh = fx1 - fx0, fy1 - fy0
    
    # Margin dahi sedikit, dagu ketat agar kerah baju tidak ikut
    x0 = max(0, int(fx0 - fw * 0.05))
    x1 = min(w, int(fx1 + fw * 0.05))
    y0 = max(0, int(fy0 - fh * 0.12))
    y1 = min(h, int(fy1 - fh * 0.02))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def gambar_preview(img, kotak, path):
    """Menggambar kotak bounding box warna-warni untuk inspeksi visual mata manusia."""
    warna = {
        "helm":   (0, 200, 255),  # Kuning / Oranye
        "baju":   (0, 255, 0),    # Hijau
        "jeans":  (255, 140, 0),  # Biru muda
        "sepatu": (255, 0, 255),  # Magenta
        "wajah":  (0, 255, 255),  # Kuning terang
    }
    prev = img.copy()
    for item, (x0, y0, x1, y1) in kotak.items():
        cv2.rectangle(prev, (x0, y0), (x1, y1), warna.get(item, (255, 255, 255)), 3)
        cv2.putText(prev, item, (x0 + 8, max(y0 + 32, 32)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, warna.get(item, (255, 255, 255)), 2)
    cv2.imwrite(str(path), prev)


def proses_wajah(masuk, keluar_wajah, preview_n):
    """Memproses dataset wajah individu (Basit, Chakim, Luki) menjadi citra RGB 128x128."""
    folder_wajah = sorted(p for p in masuk.iterdir() if p.is_dir() and p.name.lower().startswith("wajah "))
    if not folder_wajah:
        return
    if preview_n:
        (keluar_wajah / "preview").mkdir(parents=True, exist_ok=True)

    print("\n=== MEMPROSES DATASET WAJAH (CROP KETAT WAJAH SAJA, RGB) ===")
    total_ok, total_skip = 0, 0
    for folder in folder_wajah:
        nama_orang = folder.name[6:].strip()  # "Wajah Basit" -> "Basit"
        tujuan = keluar_wajah / nama_orang
        tujuan.mkdir(parents=True, exist_ok=True)
        files = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        ok, skip = 0, 0
        for f in files:
            img = cv2.imread(str(f))
            if img is None:
                skip += 1
                continue
            kotak = deteksi_kotak_wajah(img)
            if kotak is None:
                skip += 1
                continue
            x0, y0, x1, y1 = kotak
            crop = cv2.resize(img[y0:y1, x0:x1], UKURAN["wajah"], interpolation=cv2.INTER_AREA)
            nama_out = f"{nama_orang}__{f.stem}.jpg"
            cv2.imwrite(str(tujuan / nama_out), crop)
            if ok < preview_n:
                gambar_preview(img, {"wajah": kotak}, keluar_wajah / "preview" / nama_out)
            ok += 1
        total_ok += ok
        total_skip += skip
        print(f"  {nama_orang:<12} berhasil: {ok:>4}  |  dilewati (blur/samping): {skip:>3}")
    print(f"Total wajah bersih: {total_ok} (dilewati: {total_skip})")


def tambah_hard_negatives(masuk, keluar, hitung, n_bg=50, n_lintas=80, seed=42):
    """
    Suntikan Contoh Negatif Keras (Hard Negative Mining):
    1. Background Bertekstur (std >= 18.0):
       Mengambil sampel lantai bengkel, sudut meja mesin, dan bayangan lab agar model
       tidak salah mengira ubin/lantai sebagai sepatu safety atau meja sebagai baju.
    2. Lintas-Area (Cross-Area Negatives):
       Memasukkan potongan kemeja ke kelas 'tidak' pada helm & sepatu, agar model paham
       bahwa kain kemeja bukanlah helm, dan celana jeans bukanlah sepatu!
    """
    rnd = random.Random(seed)

    semua_foto = []
    for folder in sorted(p for p in masuk.iterdir() if p.is_dir()):
        fs = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        if fs:
            langkah = max(len(fs) // 20, 1)
            semua_foto.extend(fs[::langkah])
    rnd.shuffle(semua_foto)

    # Zona lantai lab, meja kerja, dan sudut ruangan
    zona_bg = [
        (0.00, 0.28, 0.50, 0.95),  # kiri bawah (meja / lantai)
        (0.72, 1.00, 0.50, 0.98),  # kanan bawah (lantai / sudut meja)
        (0.00, 0.30, 0.72, 1.00),  # pojok kiri bawah
        (0.70, 1.00, 0.72, 1.00),  # pojok kanan bawah
        (0.35, 0.65, 0.75, 1.00),  # tengah bawah lantai
    ]

    for item in ITEM_DILATIH:
        tujuan = keluar / item / "tidak"
        w_out, h_out = UKURAN[item]
        dibuat = 0
        attempts = 0
        while dibuat < n_bg and attempts < len(semua_foto) * len(zona_bg):
            f = semua_foto[attempts % len(semua_foto)]
            z = zona_bg[attempts % len(zona_bg)]
            attempts += 1
            img = cv2.imread(str(f))
            if img is None:
                continue
            h, w = img.shape[:2]
            x0p, x1p, y0p, y1p = z
            x0, x1 = int(w * x0p), int(w * x1p)
            y0, y1 = int(h * y0p), int(h * y1p)
            crop = img[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            # WAJIB bertekstur kuat (std >= 18.0), tembok putih kosong DILARANG masuk!
            if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) < 18.0:
                continue
            crop_res = cv2.resize(crop, (w_out, h_out), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(tujuan / f"BG_{item}_{dibuat:03d}.jpg"), crop_res)
            dibuat += 1
        hitung[item][1] += dibuat

    # Potongan lintas-area (area tubuh lain sebagai negatif keras)
    sumber_lintas = {
        "helm":   [keluar / "baju" / "pakai", keluar / "jeans" / "pakai", keluar / "sepatu" / "pakai"],
        "baju":   [keluar / "helm" / "tidak", keluar / "jeans" / "pakai", keluar / "sepatu" / "pakai"],
        "jeans":  [keluar / "helm" / "tidak", keluar / "baju" / "pakai", keluar / "sepatu" / "tidak"],
        "sepatu": [keluar / "helm" / "tidak", keluar / "baju" / "pakai", keluar / "jeans" / "tidak"],
    }

    for item in ITEM_DILATIH:
        tujuan = keluar / item / "tidak"
        w_out, h_out = UKURAN[item]
        kandidat = []
        for sdir in sumber_lintas[item]:
            if sdir.exists():
                kandidat.extend(sorted(f for f in sdir.iterdir()
                                       if f.suffix.lower() in EKSTENSI and not f.name.startswith(("BG_", "XA_"))))
        rnd.shuffle(kandidat)
        dibuat = 0
        for f in kandidat[:n_lintas]:
            img = cv2.imread(str(f))
            if img is None:
                continue
            if np.std(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)) < STD_MIN_VALID:
                continue
            crop = cv2.resize(img, (w_out, h_out), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(tujuan / f"XA_{item}_{dibuat:03d}.jpg"), crop_res)
            dibuat += 1
        hitung[item][1] += dibuat


def main():
    """
    Pipeline Utama Penyiapan Dataset:
    1. Parsing argumen CLI (--clean, --skip-wajah, --preview, dll).
    2. Pembersihan & pembuatan struktur folder output (dataset_area/ dan dataset_wajah/).
    3. Loop membaca setiap folder kategori APD di data_mentah/.
    4. Ekstraksi adaptif per foto, pencegahan duplikasi, dan filter tembok putih.
    5. Resize tajam dengan cv2.INTER_AREA dan penyimpanan ke kelas pakai / tidak.
    6. Ekspor riwayat data ke labels.csv dan visualisasi ke preview/.
    7. Hard negative mining dan pencetakan tabel ringkasan ke console terminal.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data_mentah", help="folder berisi data mentah")
    ap.add_argument("--output", default="dataset_area", help="folder output 4 area APD")
    ap.add_argument("--output-wajah", default="dataset_wajah", help="folder output crop wajah")
    ap.add_argument("--preview", type=int, default=5, help="jumlah foto preview per folder")
    ap.add_argument("--clean", action="store_true", help="bersihkan output sebelum proses")
    ap.add_argument("--skip-wajah", action="store_true", help="lewati proses dataset_wajah")
    args = ap.parse_args()

    masuk = Path(args.input)
    keluar = Path(args.output)
    keluar_wajah = Path(args.output_wajah)

    # 1. Bersihkan direktori lama jika parameter --clean diberikan
    if args.clean:
        if keluar.exists():
            shutil.rmtree(keluar)
        if (not args.skip_wajah) and keluar_wajah.exists():
            shutil.rmtree(keluar_wajah)

    # 2. Siapkan struktur subfolder dataset_area/<item>/<pakai|tidak>
    for item in ITEM_DILATIH:
        for kelas in ("pakai", "tidak"):
            (keluar / item / kelas).mkdir(parents=True, exist_ok=True)
    if args.preview:
        (keluar / "preview").mkdir(parents=True, exist_ok=True)

    # 3. Inisialisasi variabel pelacak statistik & anti-duplikasi
    baris = []
    hitung = {i: [0, 0] for i in ITEM_DILATIH}
    sudah_ada = {i: set() for i in ITEM_DILATIH}
    dilewati = []
    duplikat_skip = 0
    blank_skip = 0

    print("=== MEMPROSES DATASET 4 AREA APD (RGB) DENGAN ADAPTIVE FACE-ANCHORING ===")
    semua_folder = sorted(p for p in masuk.iterdir() if p.is_dir())
    for folder in semua_folder:
        # Folder wajah diproses terpisah oleh fungsi proses_wajah()
        if folder.name.lower().startswith("wajah "):
            continue
        label = cari_label(folder.name)
        if label is None:
            dilewati.append(folder.name)
            continue

        file_gambar = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        prev_count = 0
        print(f"Memproses folder: {folder.name} ({len(file_gambar)} foto)...")
        for f in file_gambar:
            img = cv2.imread(str(f))
            if img is None:
                continue

            # Jalankan Adaptive Face-Anchored Cropping
            hasil_potongan, kotak = potong_area_adaptif(img, folder.name, f, label)
            if not hasil_potongan:
                continue

            # Standarisasi penamaan file, contoh: ADP_H1_B1_J1_S1__WIN_20261125_14_30_00.jpg
            kode = "_".join(f"{i[0].upper()}{'-' if v is None else v}" for i, v in zip(ITEM, label))
            nama = f"ADP_{kode}__{f.stem}.jpg"

            disimpan_ada = False
            for item, v in zip(ITEM, label):
                # Lewati jika nilai label None (posisi duduk) atau gagal dipotong
                if v is None or item not in hasil_potongan:
                    continue
                # Cek duplikasi foto
                kunci_dup = (f.name.lower(), v)
                if kunci_dup in sudah_ada[item]:
                    duplikat_skip += 1
                    continue
                sudah_ada[item].add(kunci_dup)

                crop = hasil_potongan[item]
                # Resize tajam berkualitas tinggi menggunakan cv2.INTER_AREA
                crop_res = cv2.resize(crop, UKURAN[item], interpolation=cv2.INTER_AREA)
                kelas = "pakai" if v else "tidak"
                cv2.imwrite(str(keluar / item / kelas / nama), crop_res)
                hitung[item][0 if v else 1] += 1
                disimpan_ada = True

            # Simpan sampel preview visual berkotak bounding box
            if disimpan_ada and prev_count < args.preview:
                gambar_preview(img, kotak, keluar / "preview" / nama)
                prev_count += 1
            if disimpan_ada:
                baris.append([str(f.relative_to(masuk)), nama, folder.name,
                              *["" if v is None else v for v in label]])

    # 4. Tulis catatan riwayat metadata ke labels.csv
    with open(keluar / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        tulis = csv.writer(fh)
        tulis.writerow(["file_asli", "file_hasil", "folder", *ITEM])
        tulis.writerows(baris)

    print(f"\nTotal foto APD diproses: {len(baris)} (duplikat dilewati: {duplikat_skip})")
    
    # 5. Suntikkan Hard Negatives bertekstur
    print("Menambahkan contoh negatif tambahan bertekstur (std >= 18)...")
    tambah_hard_negatives(masuk, keluar, hitung)

    # 6. Tampilkan tabel statistik ringkasan akhir
    print(f"\n=== RINGKASAN FINAL DATASET AREA ===")
    print(f"{'item':<8}{'pakai':>8}{'tidak':>8}")
    for item in ITEM_DILATIH:
        p, t = hitung[item]
        catatan = "  <- TIDAK ADA contoh negatif!" if t == 0 else ("  <- tidak seimbang (ditangani class weight)" if min(p, t) < 0.3 * max(p, t) else "")
        print(f"{item:<8}{p:>8}{t:>8}{catatan}")
    if dilewati:
        print("\nFolder dilewati (belum ada di LABEL):", ", ".join(dilewati))

    # 7. Proses dataset biometrik wajah mahasiswa
    if not args.skip_wajah:
        proses_wajah(masuk, keluar_wajah, args.preview)


if __name__ == "__main__":
    main()
