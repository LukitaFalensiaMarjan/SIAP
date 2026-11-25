"""
Siapkan dataset RGB untuk 4 model CNN APD (helm, baju, jeans, sepatu)
dan 1 model CNN Pengenalan Wajah (Basit, Chakim, Luki).

Peningkatan Algoritma (Adaptive Face-Anchored Cropping):
  1. Deteksi posisi kepala/wajah secara dinamis dengan dlib HOG.
  2. Bounding box helm, baju, jeans, dan sepatu berpatokan langsung pada posisi tubuh mahasiswa,
     bukan koordinat statis tetap yang memotong tembok/plafon kosong saat posisi duduk/setengah badan.
  3. Filter kualitas variansi citra (std >= 14) untuk mencegah potongan tembok putih polos masuk
     ke kelas 'pakai' maupun 'tidak'.
  4. Pengenalan otomatis pose duduk / setengah badan (half-body) agar jeans & sepatu diabaikan
     (tidak memotong meja / paha duduk sebagai celana/sepatu).

Pemakaian:
    python siapkan_dataset.py --clean
    python siapkan_dataset.py --skip-wajah
"""
import argparse
import csv
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

try:
    import dlib
    DETEKTOR_WAJAH = dlib.get_frontal_face_detector()
except ImportError:
    DETEKTOR_WAJAH = None

# 1 = pakai APD wajib, 0 = tidak/salah, None = tidak terlihat di frame (jangan dipotong)
# Urutan: (helm, baju, jeans, sepatu)
LABEL_FOLDER = {
    # 1. Full Seragam Lengkap (Semua APD Pakai)
    "Full seragam":            (1, 1, 1, 1),

    # 2. Kombinasi APD Pakai Sebagian
    # Catatan: Hanya Helm & Hanya Helm dan Kemeja diambil saat duduk / setengah badan
    "Hanya Helm":              (1, 0, None, None),
    "Hanya Helm dan Kemeja":   (1, 1, None, None),
    "Hanya Kemeja dan Jeans":  (0, 1, 1, 0),
    "Hanya Jeans dan Sepatu":  (0, 0, 1, 1),

    # 3. Kombinasi Pelanggaran / Salah APD
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

# Ukuran input CNN RGB (lebar, tinggi)
UKURAN = {
    "helm":   (96, 96),
    "baju":   (128, 128),
    "jeans":  (128, 128),
    "sepatu": (128, 128),
    "wajah":  (128, 128),
}

# Standar deviasi minimal piksel grayscale agar tidak menyimpan potongan tembok putih polos / hitam pekat
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
    """Deteksi wajah cepat menggunakan HOG dengan penskalaan adaptif."""
    if DETEKTOR_WAJAH is None:
        return None
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
    return (
        int(r.left() / scale),
        int(r.top() / scale),
        int(r.right() / scale),
        int(r.bottom() / scale)
    )


def potong_area_adaptif(img, folder_name, file_path, label):
    """
    Pemotongan adaptif berdasarkan deteksi wajah:
    - Jika wajah ada: helm di atas kepala, baju di dada, jeans & sepatu di bawah (jika berdiri).
    - Jika pose setengah badan / duduk (wajah di bawah y=0.38h): jeans & sepatu otomatis diabaikan.
    - Jika wajah tidak ada: fallback ke proporsi tubuh tengah / close-up.
    - Setiap potongan difilter std >= STD_MIN_VALID agar tidak menghasilkan kotak putih kosong.
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
        is_half_body = (fy1 > 0.38 * h)

        # 1. HELM
        if h_lbl is not None:
            helm_found = False
            # Jika kelas pakai (h_lbl == 1), prioritaskan deteksi kontur helm oranye di sekitar kepala
            if h_lbl == 1:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                orange_mask = cv2.inRange(hsv, (7, 80, 80), (25, 255, 255))
                cnts, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                head_cnts = []
                for c in cnts:
                    if cv2.contourArea(c) < 350:
                        continue
                    bx, by, bw, bh = cv2.boundingRect(c)
                    if abs((bx + bw // 2) - cx) < fw * 0.9 and by < fy1 and (by + bh) > (fy0 - int(fh * 1.1)):
                        head_cnts.append(c)
                if head_cnts:
                    best_c = max(head_cnts, key=cv2.contourArea)
                    bx, by, bw, bh = cv2.boundingRect(best_c)
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

            if not helm_found:
                hy0 = max(0, fy0 - int(fh * 0.85))
                hy1 = min(h, fy0 + int(fh * 0.25))
                hx0 = max(0, cx - int(fw * 0.75))
                hx1 = min(w, cx + int(fw * 0.75))
                if hy1 > hy0 + 20 and hx1 > hx0 + 20:
                    crop = img[hy0:hy1, hx0:hx1]
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID and np.mean(crop) < 195:
                        hasil["helm"] = crop
                        kotak["helm"] = (hx0, hy0, hx1, hy1)

        # 2. BAJU
        if b_lbl is not None:
            by0 = max(0, fy1 - int(fh * 0.15))
            by1 = min(h, fy1 + int(fh * (2.2 if is_half_body else 2.8)))
            bx0 = max(0, cx - int(fw * 1.5))
            bx1 = min(w, cx + int(fw * 1.5))
            if by1 > by0 + 20 and bx1 > bx0 + 20:
                crop = img[by0:by1, bx0:bx1]
                if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID:
                    hasil["baju"] = crop
                    kotak["baju"] = (bx0, by0, bx1, by1)

        # 3 & 4. JEANS & SEPATU (hanya jika full body berdiri)
        if not is_half_body:
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
        # Fallback jika wajah tidak terdeteksi
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
            # Fallback jika wajah tidak terdeteksi:
            # 1. Khusus helm pakai (h_lbl == 1): Cari kontur oranye di seluruh frame
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

            # 2. Full body standing fallback (tengah frame)
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
                    # Filter variansi DAN kecerahan agar tidak menyimpan plafon / tembok putih polos
                    if np.std(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)) >= STD_MIN_VALID and np.mean(crop) < 195:
                        hasil[it] = crop
                        kotak[it] = (x0, y0, x1, y1)

    return hasil, kotak


def deteksi_kotak_wajah(img):
    """Crop ketat area wajah saja untuk model CNN wajah (Basit, Chakim, Luki)."""
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
    warna = {
        "helm":   (0, 200, 255),
        "baju":   (0, 255, 0),
        "jeans":  (255, 140, 0),
        "sepatu": (255, 0, 255),
        "wajah":  (0, 255, 255),
    }
    prev = img.copy()
    for item, (x0, y0, x1, y1) in kotak.items():
        cv2.rectangle(prev, (x0, y0), (x1, y1), warna.get(item, (255, 255, 255)), 3)
        cv2.putText(prev, item, (x0 + 8, max(y0 + 32, 32)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, warna.get(item, (255, 255, 255)), 2)
    cv2.imwrite(str(path), prev)


def proses_wajah(masuk, keluar_wajah, preview_n):
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
    Tambahkan contoh negatif keras yang valid dan bertekstur (std >= 18).
    Tembok putih polos / plafon kosong DILARANG masuk.
    """
    rnd = random.Random(seed)

    semua_foto = []
    for folder in sorted(p for p in masuk.iterdir() if p.is_dir()):
        fs = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        if fs:
            langkah = max(len(fs) // 20, 1)
            semua_foto.extend(fs[::langkah])
    rnd.shuffle(semua_foto)

    # Potongan background dengan tekstur (lantai, meja, sudut ruangan)
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
            # WAJIB bertekstur, bukan tembok polos!
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
            cv2.imwrite(str(tujuan / f"XA_{item}_{dibuat:03d}.jpg"), crop)
            dibuat += 1
        hitung[item][1] += dibuat


def main():
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

    if args.clean:
        if keluar.exists():
            shutil.rmtree(keluar)
        if (not args.skip_wajah) and keluar_wajah.exists():
            shutil.rmtree(keluar_wajah)

    for item in ITEM_DILATIH:
        for kelas in ("pakai", "tidak"):
            (keluar / item / kelas).mkdir(parents=True, exist_ok=True)
    if args.preview:
        (keluar / "preview").mkdir(parents=True, exist_ok=True)

    baris = []
    hitung = {i: [0, 0] for i in ITEM_DILATIH}
    sudah_ada = {i: set() for i in ITEM_DILATIH}
    dilewati = []
    duplikat_skip = 0
    blank_skip = 0

    print("=== MEMPROSES DATASET 4 AREA APD (RGB) DENGAN ADAPTIVE FACE-ANCHORING ===")
    semua_folder = sorted(p for p in masuk.iterdir() if p.is_dir())
    for folder in semua_folder:
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

            hasil_potongan, kotak = potong_area_adaptif(img, folder.name, f, label)
            if not hasil_potongan:
                continue

            kode = "_".join(f"{i[0].upper()}{'-' if v is None else v}" for i, v in zip(ITEM, label))
            nama = f"ADP_{kode}__{f.stem}.jpg"

            disimpan_ada = False
            for item, v in zip(ITEM, label):
                if v is None or item not in hasil_potongan:
                    continue
                kunci_dup = (f.name.lower(), v)
                if kunci_dup in sudah_ada[item]:
                    duplikat_skip += 1
                    continue
                sudah_ada[item].add(kunci_dup)

                crop = hasil_potongan[item]
                crop_res = cv2.resize(crop, UKURAN[item], interpolation=cv2.INTER_AREA)
                kelas = "pakai" if v else "tidak"
                cv2.imwrite(str(keluar / item / kelas / nama), crop_res)
                hitung[item][0 if v else 1] += 1
                disimpan_ada = True

            if disimpan_ada and prev_count < args.preview:
                gambar_preview(img, kotak, keluar / "preview" / nama)
                prev_count += 1
            if disimpan_ada:
                baris.append([str(f.relative_to(masuk)), nama, folder.name,
                              *["" if v is None else v for v in label]])

    with open(keluar / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        tulis = csv.writer(fh)
        tulis.writerow(["file_asli", "file_hasil", "folder", *ITEM])
        tulis.writerows(baris)

    print(f"\nTotal foto APD diproses: {len(baris)} (duplikat dilewati: {duplikat_skip})")
    print("Menambahkan contoh negatif tambahan bertekstur (std >= 18)...")
    tambah_hard_negatives(masuk, keluar, hitung)

    print(f"\n=== RINGKASAN FINAL DATASET AREA ===")
    print(f"{'item':<8}{'pakai':>8}{'tidak':>8}")
    for item in ITEM_DILATIH:
        p, t = hitung[item]
        catatan = "  <- TIDAK ADA contoh negatif!" if t == 0 else ("  <- tidak seimbang (ditangani class weight)" if min(p, t) < 0.3 * max(p, t) else "")
        print(f"{item:<8}{p:>8}{t:>8}{catatan}")
    if dilewati:
        print("\nFolder dilewati (belum ada di LABEL):", ", ".join(dilewati))

    if not args.skip_wajah:
        proses_wajah(masuk, keluar_wajah, args.preview)


if __name__ == "__main__":
    main()
