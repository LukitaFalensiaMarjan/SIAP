"""
Uji coba deteksi & pengenalan WAJAH secara real-time menggunakan kamera (webcam).
Menggunakan model TFLite hasil Transfer Learning MobileNetV2 (models/model_wajah.tflite).

Cara menjalankan:
    python uji_kamera_wajah.py
    python uji_kamera_wajah.py --kamera 1          # jika pakai webcam eksternal
    python uji_kamera_wajah.py --target Luki       # simulasi verifikasi login milik 'Luki'

Kontrol keyboard saat kamera aktif:
    G  : Ganti mode crop (Otomatis HOG vs Kotak Panduan Tengah seperti di web)
    R  : Reset hitungan verifikasi 1.5 detik
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

try:
    import dlib
    DETEKTOR_HOG = dlib.get_frontal_face_detector()
except ImportError:
    DETEKTOR_HOG = None


class ModelTFLite:
    def __init__(self, path_json):
        info = json.loads(Path(path_json).read_text(encoding="utf-8"))
        self.kelas = info["kelas"]
        self.ukuran = tuple(info["ukuran"])  # (tinggi, lebar)
        self.threshold = float(info["threshold"])
        path_tfl = Path(info["path_tflite"])
        self.interp = tf.lite.Interpreter(model_path=str(path_tfl))
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]

    def prediksi_rgb(self, crop_bgr):
        """Konversi BGR->RGB, resize sesuai input model, jalankan inferensi TFLite."""
        h, w = self.ukuran
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
        x = np.expand_dims(rgb.astype(np.float32), axis=0)
        self.interp.set_tensor(self.inp["index"], x)
        self.interp.invoke()
        probs = self.interp.get_tensor(self.out["index"])[0]
        return probs


def cari_kotak_wajah_hog(frame):
    if DETEKTOR_HOG is None:
        return None
    h, w = frame.shape[:2]
    skala = 0.5 if w > 640 else 1.0
    kecil = cv2.resize(frame, (int(w * skala), int(h * skala)))
    rgb = cv2.cvtColor(kecil, cv2.COLOR_BGR2RGB)
    rects = DETEKTOR_HOG(rgb, 0)
    if not rects:
        return None
    r = max(rects, key=lambda b: b.width() * b.height())
    x0 = int(r.left() / skala)
    y0 = int(r.top() / skala)
    x1 = int(r.right() / skala)
    y1 = int(r.bottom() / skala)
    fw, fh = x1 - x0, y1 - y0
    # Crop ketat wajah saja (sama persis dengan siapkan_dataset.py)
    x0 = max(0, int(x0 - fw * 0.05))
    x1 = min(w, int(x1 + fw * 0.05))
    y0 = max(0, int(y0 - fh * 0.12))
    y1 = min(h, int(y1 - fh * 0.02))
    if x1 <= x0 + 20 or y1 <= y0 + 20:
        return None
    return (x0, y0, x1, y1)


def kotak_panduan_tengah(frame):
    h, w = frame.shape[:2]
    sisi = int(min(h, w) * 0.45)
    x0 = (w - sisi) // 2
    y0 = max(0, int(h * 0.18))
    x1 = min(w, x0 + sisi)
    y1 = min(h, y0 + sisi)
    return (x0, y0, x1, y1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kamera", type=int, default=0, help="indeks kamera (default 0)")
    ap.add_argument("--target", type=str, default="", help="opsional: simulasi verifikasi login nama tertentu (Basit/Chakim/Luki)")
    ap.add_argument("--durasi", type=float, default=1.5, help="durasi stabil verifikasi dalam detik (default 1.5)")
    args = ap.parse_args()

    model = ModelTFLite("models/model_wajah.json")
    print(f"Model wajah siap! Kelas: {model.kelas} | Threshold: {model.threshold}")
    if args.target:
        print(f"Mode simulasi verifikasi target login: {args.target}")

    cap = cv2.VideoCapture(args.kamera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        raise SystemExit(f"Gagal membuka kamera indeks {args.kamera}.")

    mode_hog = DETEKTOR_HOG is not None
    mulai_cocok = None
    nama_terkunci = None
    riwayat_prob = deque(maxlen=4)
    terverifikasi = False

    print("Kamera aktif. Tekan [G] ganti mode crop, [R] reset timer, [S] screenshot, [Q] keluar.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)  # mirror agar natural saat menghadap kamera
        tampilan = frame.copy()
        h, w = tampilan.shape[:2]

        kotak = cari_kotak_wajah_hog(frame) if mode_hog else kotak_panduan_tengah(frame)

        status_teks = "Wajah tidak terdeteksi"
        warna = (0, 165, 255)
        probs = None

        if kotak is not None:
            x0, y0, x1, y1 = kotak
            crop = frame[y0:y1, x0:x1]
            probs = model.prediksi_rgb(crop)
            riwayat_prob.append(probs)
            rata_prob = np.mean(riwayat_prob, axis=0)

            idx = int(np.argmax(rata_prob))
            nama_pred = model.kelas[idx]
            conf = float(rata_prob[idx])

            cocok_threshold = conf >= model.threshold
            cocok_target = (not args.target) or (nama_pred.lower() == args.target.lower())

            if cocok_threshold and cocok_target:
                warna = (0, 220, 0)
                if nama_terkunci != nama_pred:
                    nama_terkunci = nama_pred
                    mulai_cocok = time.time()
                    terverifikasi = False
                durasi_jalan = time.time() - (mulai_cocok or time.time())
                if durasi_jalan >= args.durasi:
                    terverifikasi = True
                    status_teks = f"TERVERIFIKASI: {nama_pred} ({conf*100:.1f}%)"
                else:
                    status_teks = f"{nama_pred} ({conf*100:.1f}%) - Tahan {durasi_jalan:.1f}/{args.durasi:.1f} dtk"
            else:
                warna = (0, 0, 240)
                mulai_cocok = None
                nama_terkunci = None
                terverifikasi = False
                if not cocok_threshold:
                    status_teks = f"TIDAK DIKENAL (maks: {nama_pred} {conf*100:.1f}%)"
                else:
                    status_teks = f"TIDAK COCOK! Terdeteksi {nama_pred}, target: {args.target}"

            cv2.rectangle(tampilan, (x0, y0), (x1, y1), warna, 3)
            cv2.putText(tampilan, status_teks, (x0, max(y0 - 12, 30)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.72, warna, 2)
        else:
            riwayat_prob.clear()
            mulai_cocok = None
            nama_terkunci = None
            terverifikasi = False

        # Panel info atas
        cv2.rectangle(tampilan, (0, 0), (w, 105), (25, 25, 25), -1)
        mode_str = "HOG Otomatis" if mode_hog else "Kotak Panduan Tengah"
        target_str = args.target if args.target else "Semua Kelas"
        cv2.putText(tampilan, f"UJI KAMERA WAJAH (MobileNetV2 TFLite)  |  Mode: {mode_str}  |  Target: {target_str}",
                    (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)

        if probs is not None:
            rincian = "   ".join(f"{k}: {p*100:5.1f}%" for k, p in zip(model.kelas, np.mean(riwayat_prob, axis=0)))
            cv2.putText(tampilan, rincian, (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        else:
            cv2.putText(tampilan, "Arahkan wajah ke kamera...", (15, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2)

        # Progress bar verifikasi 3 detik
        progres = 0.0
        if mulai_cocok is not None:
            progres = min(1.0, (time.time() - mulai_cocok) / args.durasi)
        cv2.rectangle(tampilan, (15, 76), (365, 94), (70, 70, 70), -1)
        cv2.rectangle(tampilan, (15, 76), (15 + int(350 * progres), 94),
                      (0, 230, 0) if terverifikasi else (0, 200, 255), -1)
        label_bar = "VERIFIKASI WAJAH LOLOS!" if terverifikasi else f"Verifikasi: {progres*100:.0f}%"
        cv2.putText(tampilan, label_bar, (380, 91), cv2.FONT_HERSHEY_SIMPLEX, 0.58,
                    (0, 255, 0) if terverifikasi else (220, 220, 220), 2)

        # Footer kontrol
        cv2.putText(tampilan, "[G] Ganti Mode  |  [R] Reset  |  [S] Screenshot  |  [Q] Keluar",
                    (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1)

        cv2.imshow("Uji Kamera - Pengenalan Wajah", tampilan)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (ord("g"), ord("G")):
            mode_hog = not mode_hog if DETEKTOR_HOG is not None else False
            riwayat_prob.clear()
            mulai_cocok = None
        elif key in (ord("r"), ord("R")):
            riwayat_prob.clear()
            mulai_cocok = None
            nama_terkunci = None
            terverifikasi = False
        elif key in (ord("s"), ord("S")):
            out_dir = Path("laporan/uji_kamera")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"wajah_{int(time.time())}.jpg"
            cv2.imwrite(str(out_path), tampilan)
            print(f"Screenshot disimpan: {out_path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
