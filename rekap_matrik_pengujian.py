"""
Rekap otomatis Matrik Pengujian gabungan dari seluruh 5 model CNN
(helm, baju, jeans, sepatu, wajah) ke format Markdown dan Excel (.xlsx).

Jalankan setelah semua model selesai dilatih:
    python rekap_matrik_pengujian.py
"""
import json
from pathlib import Path

import pandas as pd

KOMPONEN = ["helm", "baju", "jeans", "sepatu", "wajah"]


def main():
    laporan_dir = Path("laporan")
    baris = []
    for k in KOMPONEN:
        p = laporan_dir / k / "metrik_pengujian.json"
        if not p.exists():
            print(f"[Belum ada] {p}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["tipe"] == "biner":
            baris.append({
                "Komponen": d["komponen"].upper(),
                "Pemilik": d.get("pemilik", "-"),
                "Arsitektur": d["arsitektur"],
                "Train / Val / Test": f"{d['jumlah_train']} / {d['jumlah_val']} / {d['jumlah_test']}",
                "Accuracy (%)": round(d["accuracy"] * 100, 2),
                "Precision (Pakai)": d["precision_pakai"],
                "Recall (Pakai)": d["recall_pakai"],
                "Recall (Tidak)": d["recall_tidak"],
                "Macro F1": d["macro_f1"],
                "Kebocoran APD (%)": d["kebocoran_apd_pct"],
                "Threshold": d["threshold"],
            })
        else:
            baris.append({
                "Komponen": d["komponen"].upper(),
                "Pemilik": d.get("pemilik", "-"),
                "Arsitektur": d["arsitektur"],
                "Train / Val / Test": f"{d['jumlah_train']} / {d['jumlah_val']} / {d['jumlah_test']}",
                "Accuracy (%)": round(d["accuracy"] * 100, 2),
                "Precision (Pakai)": d["macro_precision"],
                "Recall (Pakai)": d["macro_recall"],
                "Recall (Tidak)": "-",
                "Macro F1": d["macro_f1"],
                "Kebocoran APD (%)": "-",
                "Threshold": d["threshold"],
            })

    if not baris:
        print("Belum ada file metrik_pengujian.json. Jalankan script training terlebih dahulu.")
        return

    df = pd.DataFrame(baris)
    out_md = laporan_dir / "matrik_pengujian_gabungan.md"
    out_xlsx = laporan_dir / "matrik_pengujian_gabungan.xlsx"

    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = ["| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in df.iterrows()]
    tabel_md = "\n".join([header, sep, *rows])

    md_lines = [
        "# Matrik Pengujian Gabungan — 5 Model CNN (Simandiri CNN)\n",
        tabel_md,
        "\n\n*Catatan: Kebocoran APD (%) = persentase kasus tidak memakai APD yang lolos sebagai 'pakai' (target <= 5%).*",
    ]
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    df.to_excel(out_xlsx, index=False)

    print("\n=== MATRIK PENGUJIAN GABUNGAN ===")
    print(df.to_string(index=False))
    print(f"\nDisimpan ke:\n  - {out_md}\n  - {out_xlsx}")


if __name__ == "__main__":
    main()
