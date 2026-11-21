"""
Uji coba deteksi 4 KOMPONEN APD (Helm, Baju Praktik, Celana Jeans, Sepatu Safety)
secara real-time menggunakan kamera (webcam) & 4 model Transfer Learning MobileNetV2 (TFLite).

Mendukung 2 Mode (tekan [M] untuk berpindah):
  1. DETEKSI OBJEK (Dinamis - Default):
     Memindai beberapa kandidat area di frame; bounding box HANYA muncul di lokasi
     objek yang benar-benar terdeteksi (tidak memunculkan kotak celana/sepatu saat duduk!).
  2. ZONA POS TETAP:
     4 kotak panduan tetap untuk mahasiswa berdiri penuh +-2m.

Cara menjalankan:
    python uji_kamera_apd.py
    python uji_kamera_apd.py --kamera 1
    python uji_kamera_apd.py --lab Automation

Kontrol keyboard saat kamera aktif:
    M  : Ganti mode (Deteksi Objek Dinamis vs Zona Pos Tetap)
    1  : Lab Manufaktur (Helm, Baju, Jeans, Sepatu WAJIB)
    2  : Lab Foundry    (Helm, Baju, Jeans, Sepatu WAJIB)
    3  : Lab Automation (Baju, Jeans, Sepatu WAJIB — Helm tidak wajib)
    4  : Lab Design     (Baju, Jeans, Sepatu WAJIB — Helm tidak wajib)
    R  : Reset buffer verifikasi stabil
    S  : Simpan tangkapan layar ke laporan/uji_kamera/
    Q  : Keluar
"""
import argparse
import json
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf

# Proporsi crop Zona Pos Tetap (full-body)
LEBAR_TENGAH = 0.30
AREA_FULL_BODY = {
    "helm":   (0.05, 0.28),
    "baju":   (0.22, 0.58),
    "jeans":  (0.48, 0.86),
    "sepatu": (0.78, 1.00),
}

# Grid kandidat untuk Mode Deteksi Objek Dinamis: (lebar_proporsi, daftar_rentang_y)
GRID_DETEKSI = {
    "helm":   (0.26, [(0.02, 0.28), (0.14, 0.40)]),
    "baju":   (0.30, [(0.18, 0.54), (0.30, 0.66)]),
    "jeans":  (0.30, [(0.42, 0.80), (0.54, 0.92)]),
    "sepatu": (0.28, [(0.64, 0.90), (0.76, 1.00)]),
}
PUSAT_X = (0.42, 0.50, 0.58)

ATURAN_LAB = {
    "Manufaktur": ["helm", "baju", "jeans", "sepatu"],
    "Foundry":    ["helm", "baju", "jeans", "sepatu"],
    "Automation": ["baju", "jeans", "sepatu"],
    "Design":     ["baju", "jeans", "sepatu"],
}

MODEL_JSON = {
    "helm":   "models/model_helm.json",
    "baju":   "models/model_kemeja.json",
    "jeans":  "models/model_jeans.json",
    "sepatu": "models/model_sepatu.json",
}

NAMA_TAMPIL = {
    "helm":   "Helm Safety",
    "baju":   "Baju Praktik",
    "jeans":  "Celana Jeans",
    "sepatu": "Sepatu Safety",
}

WARNA_ITEM = {
    "helm":   (0, 230, 255),
    "baju":   (0, 230, 0),
    "jeans":  (255, 160, 0),
    "sepatu": (255, 0, 220),
}


class ModelBinerTFLite:
    def __init__(self, path_json):
        info = json.loads(Path(path_json).read_text(encoding="utf-8"))
        self.ukuran = tuple(info["ukuran"])  # (tinggi, lebar)
        self.threshold = float(info["threshold"])
        path_tfl = Path(info["path_tflite"])
        self.interp = tf.lite.Interpreter(model_path=str(path_tfl))
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]

    def prediksi_prob(self, crop_bgr):
        """Konversi BGR->RGB, resize sesuai input CNN, kembalikan probabilitas 'pakai' (0..1)."""
        h, w = self.ukuran
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        x = np.expand_dims(rgb.astype(np.float32), axis=0)
        self.interp.set_tensor(self.inp["index"], x)
        self.interp.invoke()
        return float(self.interp.get_tensor(self.out["index"])[0, 0])


def pindai_item_dinamis(frame, item, model):
    """Pindai grid kandidat untuk satu item; kembalikan (prob_tertinggi, kotak_terbaik)."""
    h, w = frame.shape[:2]
    lebar_p, daftar_y = GRID_DETEKSI[item]
    lebar = int(w * lebar_p)
    terbaik_p = 0.0
    terbaik_box = None
    for a, b in daftar_y:
        y0, y1 = int(h * a), int(h * b)
        for cx_p in PUSAT_X:
            x0 = max(0, int(w * cx_p - lebar / 2))
            x1 = min(w, x0 + lebar)
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            p = model.prediksi_prob(crop)
            if p > terbaik_p:
                terbaik_p = p
                terbaik_box = (x0, y0, x1, y1)
    return terbaik_p, terbaik_box


def potong_4_area(frame):
    h, w = frame.shape[:2]
    lebar = int(w * LEBAR_TENGAH)
    x0 = (w - lebar) // 2
    x1 = x0 + lebar
    hasil = {}
    for item, (a, b) in AREA_FULL_BODY.items():
        y0, y1 = int(h * a), int(h * b)
        hasil[item] = (frame[y0:y1, x0:x1], (x0, y0, x1, y1))
    return hasil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kamera", type=int, default=0, help="indeks kamera (default 0)")
    ap.add_argument("--lab", default="Manufaktur", choices=list(ATURAN_LAB.keys()),
                    help="pilih aturan lab awal")
    ap.add_argument("--jendela", type=int, default=8,
                    help="jumlah siklus stabilitas untuk keputusan akhir")
    ap.add_argument("--ambang-on", type=float, default=0.75,
                    help="ambang menyalakan deteksi (hysteresis ON, default 0.75)")
    ap.add_argument("--ambang-off", type=float, default=0.58,
                    help="ambang mematikan deteksi agar tidak kedip-kedip (hysteresis OFF, default 0.58)")
    args = ap.parse_args()

    print("Memuat 4 model Transfer Learning MobileNetV2 TFLite (Helm, Baju, Jeans, Sepatu)...")
    models = {item: ModelBinerTFLite(p) for item, p in MODEL_JSON.items()}
    for item, m in models.items():
        print(f"  - {item:<7} siap (input={m.ukuran}x3, threshold={m.threshold})")

    cap = cv2.VideoCapture(args.kamera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        raise SystemExit(f"Gagal membuka kamera indeks {args.kamera}.")

    lab_aktif = args.lab
    mode_dinamis = True  # Default: Mode Deteksi Objek Dinamis
    ambang_on = args.ambang_on
    ambang_off = args.ambang_off
    daftar_item = ["helm", "baju", "jeans", "sepatu"]
    ema_prob = {item: 0.0 for item in daftar_item}
    status_terdeteksi = {item: False for item in daftar_item}
    jumlah_scan = {item: 0 for item in daftar_item}
    kotak_terakhir = {item: None for item in daftar_item}
    frame_idx = 0

    print("\nKamera aktif! Mode awal: DETEKSI OBJEK DINAMIS + Stabilisasi Hysteresis (anti-kedip).")
    print("Kontrol: [M] Ganti Mode | [1-4] Lab | [+/-] Sensitivitas | [R] Reset | [S] Screenshot | [Q] Keluar")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        tampilan = frame.copy()
        h, w = tampilan.shape[:2]

        wajib = ATURAN_LAB[lab_aktif]

        if mode_dinamis:
            # Round-robin 1 item per frame (6 box/frame) agar video tetap mulus real-time
            item_scan = daftar_item[frame_idx % len(daftar_item)]
            if item_scan in wajib:
                p_best, box_best = pindai_item_dinamis(frame, item_scan, models[item_scan])
                # EMA smoothing (0.35 baru + 0.65 lama) menghilangkan noise antar frame
                if jumlah_scan[item_scan] == 0:
                    ema_prob[item_scan] = p_best
                else:
                    ema_prob[item_scan] = 0.35 * p_best + 0.65 * ema_prob[item_scan]
                jumlah_scan[item_scan] += 1
                # Update posisi kotak hanya jika skornya cukup bagus atau belum punya kotak
                if box_best is not None and (p_best >= ambang_off or kotak_terakhir[item_scan] is None):
                    kotak_terakhir[item_scan] = box_best
            frame_idx += 1
        else:
            potongan = potong_4_area(frame)
            for item in daftar_item:
                crop, box = potongan[item]
                kotak_terakhir[item] = box
                if item in wajib:
                    p_now = models[item].prediksi_prob(crop)
                    if jumlah_scan[item] == 0:
                        ema_prob[item] = p_now
                    else:
                        ema_prob[item] = 0.35 * p_now + 0.65 * ema_prob[item]
                    jumlah_scan[item] += 1

        hasil_stabil = {}
        kurang = []

        for item in daftar_item:
            if item not in wajib:
                hasil_stabil[item] = None
                if not mode_dinamis and kotak_terakhir[item]:
                    x0, y0, x1, y1 = kotak_terakhir[item]
                    cv2.rectangle(tampilan, (x0, y0), (x1, y1), (160, 160, 160), 2)
                    cv2.putText(tampilan, f"{item.upper()}: SKIP", (x0 + 8, y0 + 26),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)
                continue

            if jumlah_scan[item] == 0:
                hasil_stabil[item] = (False, 0.0)
                kurang.append(NAMA_TAMPIL[item])
                continue

            rata = ema_prob[item]
            thr_on = ambang_on if mode_dinamis else models[item].threshold
            thr_off = ambang_off if mode_dinamis else max(0.35, models[item].threshold - 0.15)

            # Logika Hysteresis: anti kedip-kedip saat diam!
            if status_terdeteksi[item]:
                if rata < thr_off:
                    status_terdeteksi[item] = False
            else:
                if rata >= thr_on:
                    status_terdeteksi[item] = True

            terdeteksi = status_terdeteksi[item]
            hasil_stabil[item] = (terdeteksi, rata)

            if not terdeteksi:
                kurang.append(NAMA_TAMPIL[item])

            box = kotak_terakhir[item]
            if box is not None:
                x0, y0, x1, y1 = box
                if mode_dinamis:
                    if terdeteksi:
                        c = WARNA_ITEM[item]
                        cv2.rectangle(tampilan, (x0, y0), (x1, y1), c, 3)
                        cv2.rectangle(tampilan, (x0, max(0, y0 - 28)), (min(w, x0 + 210), y0), c, -1)
                        cv2.putText(tampilan, f"{NAMA_TAMPIL[item]} {rata*100:.0f}%",
                                    (x0 + 6, max(20, y0 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (15, 15, 15), 2)
                else:
                    c = (0, 220, 0) if terdeteksi else (0, 0, 240)
                    cv2.rectangle(tampilan, (x0, y0), (x1, y1), c, 3)
                    cv2.putText(tampilan, f"{item.upper()}: {'OK' if terdeteksi else 'KURANG'} ({rata*100:.0f}%)",
                                (x0 + 8, y0 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.60, c, 2)

        # Panel informasi kiri
        panel_w = 370
        overlay = tampilan.copy()
        cv2.rectangle(overlay, (0, 0), (panel_w, 305), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.80, tampilan, 0.20, 0, tampilan)

        mode_str = "DETEKSI OBJEK (Dinamis)" if mode_dinamis else "ZONA POS TETAP"
        cv2.putText(tampilan, f"LAB: {lab_aktif.upper()}", (14, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 255), 2)
        cv2.putText(tampilan, f"Mode: {mode_str} | ON:{ambang_on:.2f} OFF:{ambang_off:.2f}", (14, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (215, 215, 215), 1)

        y_baris = 92
        for item in daftar_item:
            info = hasil_stabil[item]
            if info is None:
                teks = f"- {NAMA_TAMPIL[item]:<13}: Tidak Wajib"
                c = (170, 170, 170)
            else:
                pakai, rata = info
                teks = f"- {NAMA_TAMPIL[item]:<13}: {'TERDETEKSI' if pakai else 'TIDAK'} ({rata*100:3.0f}%)"
                c = (0, 230, 0) if pakai else (70, 70, 255)
            cv2.putText(tampilan, teks, (14, y_baris), cv2.FONT_HERSHEY_SIMPLEX, 0.52, c, 2)
            y_baris += 30

        siap = all(jumlah_scan[i] >= 2 for i in wajib)
        if not siap:
            status_akhir, warna_akhir = "MEMINDAI...", (0, 200, 255)
        elif not kurang:
            status_akhir, warna_akhir = "STATUS: APD LENGKAP!", (0, 255, 0)
        else:
            status_akhir, warna_akhir = "STATUS: APD KURANG", (0, 0, 255)

        cv2.putText(tampilan, status_akhir, (14, 238), cv2.FONT_HERSHEY_SIMPLEX, 0.66, warna_akhir, 2)
        if siap and kurang:
            cv2.putText(tampilan, "Kurang: " + ", ".join(kurang), (14, 268),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (130, 160, 255), 1)

        # Footer kontrol
        cv2.rectangle(tampilan, (0, h - 34), (w, h), (20, 20, 20), -1)
        cv2.putText(tampilan, "[M] Mode | [1-4] Lab | [+/-] Sensitivitas | [R] Reset | [S] Screenshot | [Q] Keluar",
                    (12, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (235, 235, 235), 1)

        cv2.imshow("Uji Kamera - Deteksi APD (Object Detection Mode)", tampilan)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (ord("m"), ord("M")):
            mode_dinamis = not mode_dinamis
            for k in daftar_item:
                ema_prob[k], status_terdeteksi[k], jumlah_scan[k] = 0.0, False, 0
        elif key in (ord("+"), ord("=")):
            ambang_on = min(0.95, round(ambang_on + 0.03, 2))
            ambang_off = max(0.35, round(ambang_on - 0.17, 2))
        elif key in (ord("-"), ord("_")):
            ambang_on = max(0.50, round(ambang_on - 0.03, 2))
            ambang_off = max(0.30, round(ambang_on - 0.17, 2))
        elif key == ord("1"):
            lab_aktif = "Manufaktur"
        elif key == ord("2"):
            lab_aktif = "Foundry"
        elif key == ord("3"):
            lab_aktif = "Automation"
        elif key == ord("4"):
            lab_aktif = "Design"
        elif key in (ord("r"), ord("R")):
            for k in daftar_item:
                ema_prob[k], status_terdeteksi[k], jumlah_scan[k] = 0.0, False, 0
                kotak_terakhir[k] = None
        elif key in (ord("s"), ord("S")):
            out_dir = Path("laporan/uji_kamera")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"apd_{lab_aktif.lower()}_{int(time.time())}.jpg"
            cv2.imwrite(str(out_path), tampilan)
            print(f"Screenshot disimpan: {out_path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
