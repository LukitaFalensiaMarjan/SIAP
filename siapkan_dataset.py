"""
Siapkan dataset RGB untuk 4 model CNN APD (helm, baju, jeans, sepatu)
dan 1 model CNN Pengenalan Wajah (Basit, Chakim, Luki).

Pemakaian:
    python siapkan_dataset.py --input data_mentah --output dataset_area --output-wajah dataset_wajah --preview 5 --clean

Struktur hasil:
    dataset_area/
        labels.csv
        helm/{pakai,tidak}/*.jpg      (96x96 RGB)
        baju/{pakai,tidak}/*.jpg      (128x128 RGB)
        jeans/{pakai,tidak}/*.jpg     (128x128 RGB)
        sepatu/{pakai,tidak}/*.jpg    (128x128 RGB)
        preview/*.jpg                 (verifikasi kotak crop)
    dataset_wajah/
        Basit/*.jpg                   (128x128 RGB, crop ketat wajah saja)
        Chakim/*.jpg                  (128x128 RGB, crop ketat wajah saja)
        Luki/*.jpg                    (128x128 RGB, crop ketat wajah saja)
        preview/*.jpg
"""
import argparse
import csv
import shutil
from pathlib import Path

import cv2

try:
    import dlib
    DETEKTOR_WAJAH = dlib.get_frontal_face_detector()
except ImportError:
    DETEKTOR_WAJAH = None

# 1 = pakai APD wajib, 0 = tidak/salah, None = tidak terlihat di frame (jangan dipotong)
# Urutan: (helm, baju, jeans, sepatu)
LABEL_FULL_BODY = {
    "Full seragam":          (1, 1, 1, 1),
    "Salah Helm":            (0, 1, 1, 1),
    "Salah Kemeja":          (1, 0, 1, 1),
    "Salah Helm & kemeja":   (0, 0, 1, 1),
    "Salah Sepatu":          (1, 1, 1, 0),
    "Salah Sepatu & Helm":   (0, 1, 1, 0),
    "Salah Sepatu & Kemeja": (1, 0, 1, 0),
    "Hanya Jeans":           (0, 0, 1, 0),
    # Nama lama tetap didukung agar kompatibel:
    "Tanpa Helm":            (0, 1, 1, 1),
    "Tanpa Kemeja":          (1, 0, 1, 1),
    "Tanpa sepatu":          (1, 1, 1, 0),
    "Tanpa Sepatu & Helm":   (0, 1, 1, 0),
    "Tanpa Sepatu & Kemeja": (1, 0, 1, 0),
    "Tanpa Helm & kemeja":   (0, 0, 1, 1),
}

# Folder close-up pinggang ke bawah (hanya terlihat celana & sepatu)
LABEL_WAIST_DOWN = {
    "Salah Celana":          (None, None, 0, 0),
}

ITEM = ["helm", "baju", "jeans", "sepatu"]
ITEM_DILATIH = ["helm", "baju", "jeans", "sepatu"]

# Potongan horizontal full-body: bagian tengah 30% lebar frame
LEBAR_TENGAH = 0.30

# Potongan vertikal full-body (proporsi tinggi frame: atas, bawah)
AREA_FULL_BODY = {
    "helm":   (0.05, 0.28),
    "baju":   (0.22, 0.58),
    "jeans":  (0.48, 0.86),
    "sepatu": (0.78, 1.00),
}

# Potongan khusus foto close-up pinggang ke bawah (Salah Celana / sneakers close-up)
AREA_WAIST_DOWN = {
    "jeans":  (0.14, 0.80),
    "sepatu": (0.72, 1.00),
}
LEBAR_WAIST_DOWN = 0.34

# Ukuran akhir tiap potongan (lebar, tinggi) untuk input CNN RGB
UKURAN = {
    "helm":   (96, 96),
    "baju":   (128, 128),
    "jeans":  (128, 128),
    "sepatu": (128, 128),
    "wajah":  (128, 128),
}

EKSTENSI = {".jpg", ".jpeg", ".png", ".bmp"}


def cari_label(nama_folder, kamus):
    for nama, label in kamus.items():
        if nama.lower() == nama_folder.lower():
            return label
    return None


def adalah_closeup_bawah(folder_name, file_path):
    """
    Deteksi foto close-up pinggang-ke-bawah yang tercampur di 'Salah Sepatu'
    (foto tanggal 20261117 merupakan close-up celana cargo + sneakers).
    """
    if cari_label(folder_name, LABEL_WAIST_DOWN) is not None:
        return True
    if folder_name.lower() == "salah sepatu" and "20261117" in file_path.name:
        return True
    return False


def potong_area(img, area_cfg, lebar_proporsi, item_aktif):
    h, w = img.shape[:2]
    lebar = int(w * lebar_proporsi)
    x0 = (w - lebar) // 2
    hasil = {}
    for item in item_aktif:
        if item not in area_cfg:
            continue
        a, b = area_cfg[item]
        y0, y1 = int(h * a), int(h * b)
        hasil[item] = (img[y0:y1, x0:x0 + lebar], (x0, y0, x0 + lebar, y1))
    return hasil


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


def deteksi_kotak_wajah(img):
    """
    Crop ketat area wajah saja menggunakan detektor klasik HOG (bukan model DL/AI)
    supaya warna baju/jaket tidak ikut masuk ke dataset CNN wajah.
    """
    if DETEKTOR_WAJAH is None:
        raise SystemExit("dlib tidak terpasang; dibutuhkan untuk detektor HOG crop wajah.")
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 2, h // 2))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    rects = DETEKTOR_WAJAH(rgb, 0)
    if not rects:
        rects = DETEKTOR_WAJAH(rgb, 1)
    if not rects:
        return None
    r = max(rects, key=lambda b: b.width() * b.height())
    x0, y0, x1, y1 = r.left() * 2, r.top() * 2, r.right() * 2, r.bottom() * 2
    fw, fh = x1 - x0, y1 - y0
    # Crop ketat wajah: margin atas untuk dahi/rambut, bawah dipotong ketat di dagu agar baju tidak ikut
    x0 = max(0, int(x0 - fw * 0.05))
    x1 = min(w, int(x1 + fw * 0.05))
    y0 = max(0, int(y0 - fh * 0.12))
    y1 = min(h, int(y1 - fh * 0.02))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data_mentah", help="folder berisi folder-folder kombinasi & wajah")
    ap.add_argument("--output", default="dataset_area", help="folder output 4 area APD")
    ap.add_argument("--output-wajah", default="dataset_wajah", help="folder output crop wajah")
    ap.add_argument("--preview", type=int, default=5, help="jumlah foto preview per folder")
    ap.add_argument("--clean", action="store_true", help="hapus output lama sebelum membuat ulang")
    args = ap.parse_args()

    masuk = Path(args.input)
    keluar = Path(args.output)
    keluar_wajah = Path(args.output_wajah)

    if args.clean:
        if keluar.exists():
            shutil.rmtree(keluar)
        if keluar_wajah.exists():
            shutil.rmtree(keluar_wajah)

    for item in ITEM_DILATIH:
        for kelas in ("pakai", "tidak"):
            (keluar / item / kelas).mkdir(parents=True, exist_ok=True)
    if args.preview:
        (keluar / "preview").mkdir(parents=True, exist_ok=True)

    baris = []
    hitung = {i: [0, 0] for i in ITEM_DILATIH}
    sudah_ada = {i: set() for i in ITEM_DILATIH}  # deduplikasi foto duplikat antar folder
    dilewati = []
    duplikat_skip = 0

    print("=== MEMPROSES DATASET 4 AREA APD (RGB) ===")
    # Urutkan supaya Salah Celana diproses dengan label waist-down yang tepat
    semua_folder = sorted(p for p in masuk.iterdir() if p.is_dir())
    for folder in semua_folder:
        if folder.name.lower().startswith("wajah "):
            continue
        label_fb = cari_label(folder.name, LABEL_FULL_BODY)
        label_wd = cari_label(folder.name, LABEL_WAIST_DOWN)
        if label_fb is None and label_wd is None:
            dilewati.append(folder.name)
            continue

        file_gambar = sorted(f for f in folder.iterdir() if f.suffix.lower() in EKSTENSI)
        prev_count = 0
        for f in file_gambar:
            img = cv2.imread(str(f))
            if img is None:
                print(f"  gagal dibaca: {f}")
                continue

            if adalah_closeup_bawah(folder.name, f):
                label = (None, None, 0, 0)
                area_cfg = AREA_WAIST_DOWN
                lebar_p = LEBAR_WAIST_DOWN
                mode_tag = "WD"
            else:
                label = label_fb
                area_cfg = AREA_FULL_BODY
                lebar_p = LEBAR_TENGAH
                mode_tag = "FB"

            item_aktif = [it for it, v in zip(ITEM, label) if v is not None and it in ITEM_DILATIH]
            kode = "_".join(f"{i[0].upper()}{'-' if v is None else v}" for i, v in zip(ITEM, label))
            nama = f"{mode_tag}_{kode}__{f.stem}.jpg"
            potongan = potong_area(img, area_cfg, lebar_p, item_aktif)

            disimpan_ada = False
            for item, v in zip(ITEM, label):
                if v is None or item not in ITEM_DILATIH:
                    continue
                kunci_dup = (f.name.lower(), v)
                if kunci_dup in sudah_ada[item]:
                    duplikat_skip += 1
                    continue
                sudah_ada[item].add(kunci_dup)

                crop, _ = potongan[item]
                crop = cv2.resize(crop, UKURAN[item], interpolation=cv2.INTER_AREA)
                kelas = "pakai" if v else "tidak"
                cv2.imwrite(str(keluar / item / kelas / nama), crop)
                hitung[item][0 if v else 1] += 1
                disimpan_ada = True

            if disimpan_ada and prev_count < args.preview:
                gambar_preview(img, {k: v[1] for k, v in potongan.items()}, keluar / "preview" / nama)
                prev_count += 1
            if disimpan_ada:
                baris.append([str(f.relative_to(masuk)), nama, folder.name, mode_tag,
                              *["" if v is None else v for v in label]])

    with open(keluar / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        tulis = csv.writer(fh)
        tulis.writerow(["file_asli", "file_hasil", "folder", "mode", *ITEM])
        tulis.writerows(baris)

    print(f"\nTotal foto APD diproses: {len(baris)} (duplikat dilewati: {duplikat_skip})")
    print(f"{'item':<8}{'pakai':>8}{'tidak':>8}")
    for item in ITEM_DILATIH:
        p, t = hitung[item]
        catatan = "  <- TIDAK ADA contoh negatif!" if t == 0 else ("  <- tidak seimbang (ditangani class weight)" if min(p, t) < 0.3 * max(p, t) else "")
        print(f"{item:<8}{p:>8}{t:>8}{catatan}")
    if dilewati:
        print("\nFolder dilewati (belum ada di LABEL):", ", ".join(dilewati))

    proses_wajah(masuk, keluar_wajah, args.preview)


if __name__ == "__main__":
    main()
