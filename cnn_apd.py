"""
Modul bersama untuk training CNN APD (dipakai train_helm.py, train_kemeja.py, train_sepatu.py).

Isi:
- muat_data()      : baca dataset_area/<area>/{pakai,tidak}, bagi train/val/test per kelompok
- latih()          : training dengan augmentasi, class weight, early stopping
- evaluasi()       : confusion matrix, laporan klasifikasi, pilih threshold
- grad_cam()       : peta perhatian model untuk laporan

Label: 1 = pakai, 0 = tidak.
"""
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from tensorflow import keras
from sklearn.metrics import classification_report, confusion_matrix

EKSTENSI = {".jpg", ".jpeg", ".png", ".bmp"}


# ---------------------------------------------------------------- data

def kunci_kelompok(nama_file):
    """
    Kelompok dipakai supaya foto yang mirip (orang/sesi yang sama) tidak
    tersebar ke train dan test sekaligus.
    - Nama file berisi 'P01', 'P02', ... -> dikelompokkan per orang (paling baik)
    - Nama file kamera Windows 'WIN_YYYYMMDD_HH_MM_..' -> per menit pengambilan
    - Selain itu -> per file
    """
    stem = Path(nama_file).stem.split("__")[-1]
    m = re.search(r"(P\d+)", stem, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"WIN_(\d{8})_(\d{2})_(\d{2})", stem)
    if m:
        return "_".join(m.groups())
    return stem


def muat_data(folder_area, porsi=(0.70, 0.15, 0.15), seed=42):
    folder_area = Path(folder_area)
    # Kumpulkan per kelas secara terpisah supaya split tetap seimbang
    per_kelas = {0: [], 1: []}
    for kelas, label in (("pakai", 1), ("tidak", 0)):
        for f in sorted((folder_area / kelas).iterdir()):
            if f.suffix.lower() in EKSTENSI:
                per_kelas[label].append((str(f), label, kunci_kelompok(f.name)))
    if not any(per_kelas.values()):
        raise SystemExit(f"Tidak ada gambar di {folder_area}")

    rnd = random.Random(seed)
    bagian = {"train": [], "val": [], "test": []}

    # Split per kelas → distribusi seimbang di setiap split
    for label, daftar in per_kelas.items():
        daftar = list(daftar)
        rnd.shuffle(daftar)
        n = len(daftar)
        n_tr = round(n * porsi[0])
        n_va = round(n * porsi[1])
        bagian["train"].extend(daftar[:n_tr])
        bagian["val"].extend(daftar[n_tr:n_tr + n_va])
        bagian["test"].extend(daftar[n_tr + n_va:])

    print(f"Jumlah kelompok foto (orang/sesi): {len({x[2] for x in bagian['train'] + bagian['val'] + bagian['test']})}")
    for nama, isi in bagian.items():
        p = sum(1 for x in isi if x[1] == 1)
        print(f"  {nama:<6} total {len(isi):>5}  pakai {p:>5}  tidak {len(isi) - p:>5}")
    return bagian


def buat_dataset(isi, ukuran, batch, acak):
    path = [x[0] for x in isi]
    label = np.array([x[1] for x in isi], dtype="float32")

    def baca(p, y):
        img = tf.io.decode_image(tf.io.read_file(p), channels=3, expand_animations=False)
        img = tf.image.resize(img, ukuran)
        return tf.cast(img, tf.float32), y

    ds = tf.data.Dataset.from_tensor_slices((path, label))
    if acak:
        ds = ds.shuffle(len(path), reshuffle_each_iteration=True)
    return ds.map(baca, num_parallel_calls=tf.data.AUTOTUNE).batch(batch).prefetch(tf.data.AUTOTUNE)


def lapisan_augmentasi(flip=True):
    lapisan = []
    if flip:
        lapisan.append(keras.layers.RandomFlip("horizontal"))
    lapisan += [
        keras.layers.RandomRotation(0.10),          # lebih besar: +-36 derajat
        keras.layers.RandomZoom(0.20),
        keras.layers.RandomTranslation(0.10, 0.10),
        keras.layers.RandomBrightness(0.30, value_range=(0, 255)),
        keras.layers.RandomContrast(0.30),
    ]
    return keras.Sequential(lapisan, name="augmentasi")


# ---------------------------------------------------------------- training

def latih(model, bagian, cfg, folder_laporan):
    folder_laporan = Path(folder_laporan)
    folder_laporan.mkdir(parents=True, exist_ok=True)
    Path(cfg["path_model"]).parent.mkdir(parents=True, exist_ok=True)

    ds_train = buat_dataset(bagian["train"], cfg["ukuran"], cfg["batch"], acak=True)
    ds_val = buat_dataset(bagian["val"], cfg["ukuran"], cfg["batch"], acak=False)

    # Class weight: kelas yang lebih sedikit diberi bobot lebih besar
    y = np.array([x[1] for x in bagian["train"]])
    n, n1 = len(y), int(y.sum())
    n0 = n - n1
    bobot = {0: n / (2 * max(n0, 1)), 1: n / (2 * max(n1, 1))}
    print(f"Class weight: tidak={bobot[0]:.2f}  pakai={bobot[1]:.2f}")

    model.compile(
        optimizer=keras.optimizers.Adam(cfg["learning_rate"]),
        loss="binary_crossentropy",
        metrics=["accuracy", keras.metrics.Precision(name="precision"), keras.metrics.Recall(name="recall")],
    )
    model.summary()

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=cfg["patience"], restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=max(cfg["patience"] // 2, 2)),
        keras.callbacks.ModelCheckpoint(cfg["path_model"], monitor="val_loss", save_best_only=True),
        keras.callbacks.CSVLogger(str(folder_laporan / "riwayat_training.csv")),
    ]
    riwayat = model.fit(ds_train, validation_data=ds_val, epochs=cfg["epochs"],
                        class_weight=bobot, callbacks=callbacks)
    grafik_training(riwayat.history, folder_laporan / "grafik_training.png")
    return model


def grafik_training(h, path):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(h["loss"], label="train"); ax[0].plot(h["val_loss"], label="validasi")
    ax[0].set_title("Loss"); ax[0].set_xlabel("epoch"); ax[0].legend()
    ax[1].plot(h["accuracy"], label="train"); ax[1].plot(h["val_accuracy"], label="validasi")
    ax[1].set_title("Akurasi"); ax[1].set_xlabel("epoch"); ax[1].legend()
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


# ---------------------------------------------------------------- evaluasi

def prediksi(model, isi, cfg):
    ds = buat_dataset(isi, cfg["ukuran"], cfg["batch"], acak=False)
    return model.predict(ds, verbose=0).ravel(), np.array([x[1] for x in isi])


def pilih_threshold(prob, y, min_recall_tidak=0.95):
    """
    Pilih threshold dari data validasi.
    Prioritas: orang yang TIDAK memakai APD harus tertangkap (recall kelas 'tidak' >= target),
    lalu di antara itu pilih yang paling banyak benar untuk kelas 'pakai'.
    """
    terbaik, skor_terbaik = 0.5, -1
    for t in np.arange(0.05, 0.96, 0.01):
        pred = (prob >= t).astype(int)
        rec_tidak = ((pred == 0) & (y == 0)).sum() / max((y == 0).sum(), 1)
        rec_pakai = ((pred == 1) & (y == 1)).sum() / max((y == 1).sum(), 1)
        skor = rec_pakai if rec_tidak >= min_recall_tidak else rec_tidak - 1
        if skor > skor_terbaik:
            terbaik, skor_terbaik = float(t), skor
    return round(terbaik, 2)


def evaluasi(model, bagian, cfg, folder_laporan):
    folder_laporan = Path(folder_laporan)
    p_val, y_val = prediksi(model, bagian["val"], cfg)
    t = pilih_threshold(p_val, y_val, cfg["min_recall_tidak"])
    p_test, y_test = prediksi(model, bagian["test"], cfg)
    pred = (p_test >= t).astype(int)

    nama = ["tidak", "pakai"]
    cm = confusion_matrix(y_test, pred, labels=[0, 1])
    laporan = classification_report(y_test, pred, labels=[0, 1], target_names=nama, digits=3, zero_division=0)
    teks = f"Area: {cfg['area']}\nThreshold (dipilih dari validasi): {t}\n\nData TEST\n{laporan}\nConfusion matrix (baris=asli, kolom=prediksi) [tidak, pakai]:\n{cm}\n"
    print("\n" + teks)
    (folder_laporan / "hasil_evaluasi.txt").write_text(teks, encoding="utf-8")

    fig, ax = plt.subplots(figsize=(4.5, 4))
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=14,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xticks([0, 1], nama); ax.set_yticks([0, 1], nama)
    ax.set_xlabel("Prediksi"); ax.set_ylabel("Asli"); ax.set_title(f"Confusion matrix - {cfg['area']}")
    fig.tight_layout(); fig.savefig(folder_laporan / "confusion_matrix.png", dpi=120); plt.close(fig)

    # Simpan konfigurasi untuk dipakai aplikasi web nanti
    info = {"area": cfg["area"], "ukuran": list(cfg["ukuran"]), "threshold": t,
            "path_model": str(cfg["path_model"]), "label": {"0": "tidak", "1": "pakai"}}
    Path(cfg["path_model"]).with_suffix(".json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return t


# ---------------------------------------------------------------- Grad-CAM

def grad_cam(model, isi, cfg, folder_laporan, n=8, nama_conv="conv_terakhir"):
    """Simpan contoh Grad-CAM: bagian gambar yang paling dilihat model."""
    conv = model.get_layer(nama_conv)
    model_grad = keras.Model(model.inputs, [conv.output, model.output])
    rnd = random.Random(0)
    contoh = rnd.sample(isi, min(n, len(isi)))

    fig, axes = plt.subplots(2, len(contoh), figsize=(2.2 * len(contoh), 4.8))
    axes = np.array(axes).reshape(2, -1)
    for k, (path, label, _) in enumerate(contoh):
        img = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
        img = tf.cast(tf.image.resize(img, cfg["ukuran"]), tf.float32)[None]
        with tf.GradientTape() as tape:
            fitur, out = model_grad(img, training=False)
            # gradien terhadap kelas yang diprediksi
            skor = out[:, 0] if float(out[0, 0]) >= 0.5 else 1 - out[:, 0]
        grad = tape.gradient(skor, fitur)
        bobot = tf.reduce_mean(grad, axis=(0, 1, 2))
        peta = tf.nn.relu(tf.reduce_sum(fitur[0] * bobot, axis=-1))
        peta = (peta / (tf.reduce_max(peta) + 1e-8)).numpy()
        peta = tf.image.resize(peta[..., None], cfg["ukuran"]).numpy()[..., 0]

        asli = img[0].numpy().astype("uint8")
        axes[0, k].imshow(asli); axes[0, k].axis("off")
        axes[0, k].set_title(f"asli: {'pakai' if label else 'tidak'}", fontsize=8)
        axes[1, k].imshow(asli); axes[1, k].imshow(peta, cmap="jet", alpha=0.45); axes[1, k].axis("off")
        axes[1, k].set_title(f"prob pakai {float(out[0, 0]):.2f}", fontsize=8)
    fig.tight_layout(); fig.savefig(Path(folder_laporan) / "grad_cam.png", dpi=120); plt.close(fig)


# ---------------------------------------------------------------- jalankan semua

def jalankan(cfg, build_model):
    keras.utils.set_random_seed(cfg.get("seed", 42))
    folder_laporan = Path("laporan") / cfg["area"]
    bagian = muat_data(Path(cfg["folder_dataset"]) / cfg["area"], seed=cfg.get("seed", 42))
    model = build_model((*cfg["ukuran"], 3))
    model = latih(model, bagian, cfg, folder_laporan)
    evaluasi(model, bagian, cfg, folder_laporan)
    grad_cam(model, bagian["test"], cfg, folder_laporan)
    print(f"\nSelesai. Model: {cfg['path_model']}  |  Laporan: {folder_laporan}/")
