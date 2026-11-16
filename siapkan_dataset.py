"""
Siapkan dataset APD: baca folder per kombinasi, buat labels.csv,
lalu potong tiap foto menjadi 4 area (helm, baju, jeans, sepatu).

Pemakaian:
    python siapkan_dataset.py --input dataset_mentah --output dataset_area
    python siapkan_dataset.py --input dataset_mentah --output dataset_area --preview 5

Struktur hasil:
    dataset_area/
        labels.csv
        helm/pakai/...jpg     helm/tidak/...jpg
        baju/pakai/...jpg     baju/tidak/...jpg
        sepatu/pakai/...jpg   sepatu/tidak/...jpg

Jeans TIDAK dideteksi CNN (tidak ada data tanpa jeans); dicek manual oleh PLP.
Kolom jeans tetap dicatat di labels.csv supaya bisa diaktifkan lagi nanti.
        preview/...jpg        (opsional, untuk cek posisi potongan)
"""
import argparse
import csv
from pathlib import Path

import cv2

# 1 = dipakai, 0 = tidak dipakai. Urutan: helm, baju, jeans, sepatu
LABEL_FOLDER = {
    "Full seragam":          (1, 1, 1, 1),
    "Tanpa Helm":            (0, 1, 1, 1),
    "Tanpa Kemeja":          (1, 0, 1, 1),
    "Tanpa sepatu":          (1, 1, 1, 0),
    "Tanpa Sepatu & Helm":   (0, 1, 1, 0),
    "Tanpa Sepatu & Kemeja": (1, 0, 1, 0),
    "Tanpa Helm & kemeja":   (0, 0, 1, 1),
    "Hanya Jeans":           (0, 0, 1, 0),
    # Tambahkan folder baru di sini, misalnya:
    # "Tanpa Jeans":         (1, 1, 0, 1),
    # "Pakaian bebas":       (0, 0, 0, 0),
}

ITEM = ["helm", "baju", "jeans", "sepatu"]          # urutan label di LABEL_FOLDER
ITEM_DILATIH = ["helm", "baju", "sepatu"]           # yang dipotong dan dilatih CNN
# Untuk mengaktifkan jeans lagi (setelah ada data tanpa jeans), tambahkan "jeans" di ITEM_DILATIH.

# Potongan horizontal: bagian tengah frame (orang berdiri di tengah).
LEBAR_TENGAH = 0.26  # 26% lebar frame (sekitar 500 px di 1920)

# Potongan vertikal per area, dalam proporsi tinggi frame (atas, bawah).
# Sesuaikan setelah melihat folder preview.
AREA = {
    "helm":   (0.08, 0.30),
    "baju":   (0.22, 0.60),
    "jeans":  (0.50, 0.88),
    "sepatu": (0.78, 1.00),
}

# Ukuran akhir tiap potongan untuk input CNN
UKURAN = {"helm": (96, 96), "baju": (128, 128), "jeans": (128, 128), "sepatu": (128, 128)}

EKSTENSI = {".jpg", ".jpeg", ".png", ".bmp"}


def cari_label(nama_folder):
    for nama, label in LABEL_FOLDER.items():
        if nama.lower() == nama_folder.lower():
            return label
    return None


def potong(img):
    h, w = img.shape[:2]
    lebar = int(w * LEBAR_TENGAH)
    x0 = (w - lebar) // 2
    hasil = {}
    for item in ITEM_DILATIH:
        a, b = AREA[item]
        y0, y1 = int(h * a), int(h * b)
        hasil[item] = (img[y0:y1, x0:x0 + lebar], (x0, y0, x0 + lebar, y1))
    return hasil


def gambar_preview(img, kotak, path):
    warna = {"helm": (0, 200, 255), "baju": (0, 255, 0), "jeans": (255, 120, 0), "sepatu": (255, 0, 255)}
    prev = img.copy()
    for item, (x0, y0, x1, y1) in kotak.items():
        cv2.rectangle(prev, (x0, y0), (x1, y1), warna[item], 3)
        cv2.putText(prev, item, (x0 + 8, y0 + 32), cv2.FONT_HERSHEY_SIMPLEX, 1, warna[item], 2)
    cv2.imwrite(str(path), prev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="folder berisi folder-folder kombinasi")
    ap.add_argument("--output", required=True)
    ap.add_argument("--preview", type=int, default=0, help="jumlah foto preview per folder")
    args = ap.parse_args()

    masuk, keluar = Path(args.input), Path(args.output)
    for item in ITEM_DILATIH:
        for kelas in ("pakai", "tidak"):
            (keluar / item / kelas).mkdir(parents=True, exist_ok=True)
    if args.preview:
        (keluar / "preview").mkdir(parents=True, exist_ok=True)

    baris, hitung, dilewati = [], {i: [0, 0] for i in ITEM_DILATIH}, []
    for folder in sorted(p for p in masuk.iterdir() if p.is_dir()):
        label = cari_label(folder.name)
        if label is None:
            dilewati.append(folder.name)
            continue
        kode = "_".join(f"{i[0].upper()}{v}" for i, v in zip(ITEM, label))
        file_gambar = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        for n, f in enumerate(file_gambar):
            img = cv2.imread(str(f))
            if img is None:
                print(f"  gagal dibaca: {f}")
                continue
            nama = f"{kode}__{f.stem}.jpg"
            potongan = potong(img)
            for item, v in zip(ITEM, label):
                if item not in ITEM_DILATIH:
                    continue
                crop, _ = potongan[item]
                crop = cv2.resize(crop, UKURAN[item], interpolation=cv2.INTER_AREA)
                kelas = "pakai" if v else "tidak"
                cv2.imwrite(str(keluar / item / kelas / nama), crop)
                hitung[item][0 if v else 1] += 1
            if n < args.preview:
                gambar_preview(img, {k: v[1] for k, v in potongan.items()}, keluar / "preview" / nama)
            baris.append([str(f.relative_to(masuk)), nama, folder.name, *label])

    with open(keluar / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        tulis = csv.writer(fh)
        tulis.writerow(["file_asli", "file_hasil", "folder", *ITEM])
        tulis.writerows(baris)

    print(f"\nTotal foto: {len(baris)}")
    print(f"{'item':<8}{'pakai':>8}{'tidak':>8}")
    for item in ITEM_DILATIH:
        p, t = hitung[item]
        catatan = "  <- TIDAK ADA contoh negatif!" if t == 0 else ("  <- tidak seimbang" if min(p, t) < 0.3 * max(p, t) else "")
        print(f"{item:<8}{p:>8}{t:>8}{catatan}")
    if dilewati:
        print("\nFolder dilewati (belum ada di LABEL_FOLDER):", ", ".join(dilewati))


if __name__ == "__main__":
    main()
