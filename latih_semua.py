"""
Skrip otomatisasi untuk melatih seluruh 5 model CNN secara berurutan:
1. Model Wajah (train_wajah.py)
2. Model Helm (train_helm.py)
3. Model Kemeja (train_kemeja.py)
4. Model Jeans (train_jeans.py)
5. Model Sepatu (train_sepatu.py)

Hasil model .keras, .tflite, dan .json akan otomatis tersimpan di models/
dan grafik evaluasi di laporan/
"""
import sys
import time
import subprocess

MODELS = [
    ("Model Wajah (Basit, Chakim, Luki)", "train_wajah.py"),
    ("Model Helm Safety", "train_helm.py"),
    ("Model Kemeja Praktik", "train_kemeja.py"),
    ("Model Celana Jeans", "train_jeans.py"),
    ("Model Sepatu Safety", "train_sepatu.py"),
]

def main():
    print("=" * 65)
    print("      PELATIHAN ULANG SEMUA MODEL CNN SIMANDIRI (RGB TFLITE)     ")
    print("=" * 65)
    
    total_start = time.time()
    for idx, (label, script) in enumerate(MODELS, 1):
        print(f"\n[{idx}/5] Memulai pelatihan: {label} ({script})...")
        start = time.time()
        res = subprocess.run([sys.executable, script])
        durasi = time.time() - start
        if res.returncode == 0:
            print(f"[{idx}/5] BERHASIL: {label} selesai dalam {durasi/60:.1f} menit.")
        else:
            print(f"[{idx}/5] GAGAL pada {label} (exit code: {res.returncode}).")
            sys.exit(res.returncode)

    total_dur = time.time() - total_start
    print("\n" + "=" * 65)
    print(f"SELURUH 5 MODEL BERHASIL DILATIH DALAM {total_dur/60:.1f} MENIT!")
    print("File model TFLite siap digunakan di folder models/")
    print("Membuat rekap otomatis matrik pengujian gabungan...")
    subprocess.run([sys.executable, "rekap_matrik_pengujian.py"])
    print("=" * 65)

if __name__ == "__main__":
    main()
