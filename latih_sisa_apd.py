"""
Skrip otomatisasi melatih 4 model APD (Helm, Kemeja, Jeans, Sepatu) secara berurutan.
Model Wajah sudah berhasil dilatih sebelumnya dengan akurasi 98.6%.
"""
import sys
import time
import subprocess

MODELS = [
    ("Model Helm Safety", "train_helm.py"),
    ("Model Kemeja Praktik", "train_kemeja.py"),
    ("Model Celana Jeans", "train_jeans.py"),
    ("Model Sepatu Safety", "train_sepatu.py"),
]

def main():
    print("=" * 65)
    print("      PELATIHAN 4 MODEL APD SIMANDIRI CNN (HELM, KEMEJA, JEANS, SEPATU)     ")
    print("=" * 65)
    
    total_start = time.time()
    for idx, (label, script) in enumerate(MODELS, 1):
        print(f"\n[{idx}/4] Memulai pelatihan: {label} ({script})...")
        start = time.time()
        res = subprocess.run([sys.executable, script])
        durasi = time.time() - start
        if res.returncode == 0:
            print(f"[{idx}/4] BERHASIL: {label} selesai dalam {durasi/60:.1f} menit.")
        else:
            print(f"[{idx}/4] GAGAL pada {label} (exit code: {res.returncode}).")
            sys.exit(res.returncode)

    total_dur = time.time() - total_start
    print("\n" + "=" * 65)
    print(f"SELURUH 4 MODEL APD BERHASIL DILATIH DALAM {total_dur/60:.1f} MENIT!")
    print("File model TFLite siap digunakan di folder models/")
    print("=" * 65)

if __name__ == "__main__":
    main()
