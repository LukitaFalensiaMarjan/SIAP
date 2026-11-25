"""
Modul bersama untuk training & evaluasi CNN APD + Pengenalan Wajah
(dipakai oleh train_helm.py, train_kemeja.py, train_jeans.py, train_sepatu.py, train_wajah.py).

Ketentuan yang dipenuhi:
- Seluruh citra diproses dalam format RGB 3-channel (H, W, 3).
- Mendukung klasifikasi biner (4 model APD: CNN from scratch) dan
  multiclass (model Wajah: Transfer Learning MobileNetV2).
- Menghasilkan Matrik Pengujian lengkap (Confusion Matrix, Accuracy, Precision,
  Recall, F1-Score, Specificity, Kebocoran APD, Grad-CAM) di laporan/<komponen>/.
- Mengekspor model ringan (.tflite) secara otomatis untuk deployment di PythonAnywhere.

Label biner: 1 = pakai, 0 = tidak.
"""
import json
import random
import re
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from tensorflow import keras
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

EKSTENSI = {".jpg", ".jpeg", ".png", ".bmp"}


class SafeModelCheckpoint(keras.callbacks.ModelCheckpoint):
    """ModelCheckpoint dengan toleransi retry & anti-crash file lock di Windows."""
    def _save_model(self, epoch, batch, logs):
        for attempt in range(5):
            try:
                super()._save_model(epoch, batch, logs)
                return
            except OSError as exc:
                if attempt < 4:
                    time.sleep(0.5)
                else:
                    print(f"Peringatan ModelCheckpoint (epoch {epoch}): {exc}")


class SafeCSVLogger(keras.callbacks.CSVLogger):
    """CSVLogger dengan toleransi retry jika file sedang diakses proses lain."""
    def on_epoch_end(self, epoch, logs=None):
        for attempt in range(5):
            try:
                super().on_epoch_end(epoch, logs)
                return
            except OSError as exc:
                if attempt < 4:
                    time.sleep(0.5)
                else:
                    print(f"Peringatan CSVLogger: {exc}")


# ---------------------------------------------------------------- data

def kunci_kelompok(nama_file):
    """Kelompok foto berdasarkan ID orang (P01..) atau timestamp kamera Windows."""
    stem = Path(nama_file).stem.split("__")[-1]
    m = re.search(r"(P\d+)", stem, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"WIN_(\d{8})_(\d{2})_(\d{2})", stem)
    if m:
        return "_".join(m.groups())
    return stem


def muat_data(folder_area, porsi=(0.70, 0.15, 0.15), seed=42):
    """Muat dataset biner dari folder_area/{pakai,tidak} dengan split stratified."""
    folder_area = Path(folder_area)
    per_kelas = {0: [], 1: []}
    for kelas, label in (("pakai", 1), ("tidak", 0)):
        sub = folder_area / kelas
        if not sub.exists():
            continue
        for f in sorted(sub.iterdir()):
            if f.suffix.lower() in EKSTENSI:
                per_kelas[label].append((f.resolve().as_posix(), label, kunci_kelompok(f.name)))
    if not any(per_kelas.values()):
        raise SystemExit(f"Tidak ada gambar di {folder_area}")

    rnd = random.Random(seed)
    bagian = {"train": [], "val": [], "test": []}

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


def muat_data_multikelas(folder_dataset, porsi=(0.70, 0.15, 0.15), seed=42):
    """Muat dataset multiclass (misal dataset_wajah/{Basit,Chakim,Luki})."""
    folder_dataset = Path(folder_dataset)
    kelas_list = sorted(p.name for p in folder_dataset.iterdir() if p.is_dir() and p.name != "preview")
    if not kelas_list:
        raise SystemExit(f"Tidak ada subfolder kelas di {folder_dataset}")

    rnd = random.Random(seed)
    bagian = {"train": [], "val": [], "test": []}
    for idx, nama_kelas in enumerate(kelas_list):
        daftar = []
        for f in sorted((folder_dataset / nama_kelas).iterdir()):
            if f.suffix.lower() in EKSTENSI:
                daftar.append((str(f), idx, kunci_kelompok(f.name)))
        rnd.shuffle(daftar)
        n = len(daftar)
        n_tr = round(n * porsi[0])
        n_va = round(n * porsi[1])
        bagian["train"].extend(daftar[:n_tr])
        bagian["val"].extend(daftar[n_tr:n_tr + n_va])
        bagian["test"].extend(daftar[n_tr + n_va:])

    print(f"Kelas ({len(kelas_list)}): {kelas_list}")
    for nama, isi in bagian.items():
        rincian = "  ".join(f"{k}={sum(1 for x in isi if x[1] == i)}" for i, k in enumerate(kelas_list))
        print(f"  {nama:<6} total {len(isi):>5}  ({rincian})")
    return bagian, kelas_list


def lapisan_augmentasi(flip=True):
    """Augmentasi citra RGB untuk mencegah overfitting & tahan beda ruangan/cahaya."""
    lapisan = []
    if flip:
        lapisan.append(keras.layers.RandomFlip("horizontal"))
    lapisan += [
        keras.layers.RandomRotation(0.08),
        keras.layers.RandomZoom(0.20),
        keras.layers.RandomTranslation(0.10, 0.10),
        keras.layers.RandomBrightness(0.30, value_range=(0, 255)),
        keras.layers.RandomContrast(0.30),
    ]
    return keras.Sequential(lapisan, name="augmentasi")


def buat_dataset(isi, ukuran, batch, acak, augment=False, flip=True, multiclass=False):
    """Bangun tf.data.Dataset citra RGB (H, W, 3) dengan augmentasi opsional pada train."""
    path = [x[0] for x in isi]
    dtype_y = "int32" if multiclass else "float32"
    label = np.array([x[1] for x in isi], dtype=dtype_y)

    def baca(p, y):
        # channels=3 menjamin seluruh citra dibaca sebagai RGB 3-channel
        img = tf.io.decode_image(tf.io.read_file(p), channels=3, expand_animations=False)
        img = tf.image.resize(img, ukuran)
        return tf.cast(img, tf.float32), y

    ds = tf.data.Dataset.from_tensor_slices((path, label))
    if acak:
        ds = ds.shuffle(len(path), reshuffle_each_iteration=True)
    ds = ds.map(baca, num_parallel_calls=tf.data.AUTOTUNE).batch(batch)
    if augment:
        aug = lapisan_augmentasi(flip=flip)
        ds = ds.map(lambda x, y: (aug(x, training=True), y), num_parallel_calls=tf.data.AUTOTUNE)
    return ds.prefetch(tf.data.AUTOTUNE)


# ---------------------------------------------------------------- ekspor ringan (PythonAnywhere)

def ekspor_tflite(model, path_model):
    """
    Ekspor model Keras (.keras) ke TFLite (.tflite) agar super ringan & cepat di CPU
    untuk deployment online di PythonAnywhere.com.
    """
    path_tflite = Path(path_model).with_suffix(".tflite")
    try:
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_bytes = converter.convert()
        path_tflite.write_bytes(tflite_bytes)
        ukuran_kb = len(tflite_bytes) / 1024
        print(f"Ekspor TFLite berhasil: {path_tflite} ({ukuran_kb:.1f} KB)")
        return str(path_tflite)
    except Exception as exc:
        print(f"Peringatan: ekspor TFLite gagal ({exc}); gunakan model .keras lokal.")
        return None


# ---------------------------------------------------------------- training biner (APD)

def latih(model, bagian, cfg, folder_laporan):
    folder_laporan = Path(folder_laporan)
    folder_laporan.mkdir(parents=True, exist_ok=True)
    Path(cfg["path_model"]).parent.mkdir(parents=True, exist_ok=True)

    data_train = list(bagian["train"])
    if cfg.get("oversample_train", False):
        k0 = [x for x in data_train if x[1] == 0]
        k1 = [x for x in data_train if x[1] == 1]
        rnd = random.Random(cfg.get("seed", 42))
        if 0 < len(k0) < len(k1):
            tambahan = rnd.choices(k0, k=len(k1) - len(k0))
            data_train = k1 + k0 + tambahan
            rnd.shuffle(data_train)
            print(f"Oversampling train (kelas minoritas): {len(k0)} -> {len(k1)} (total train={len(data_train)})")
        elif 0 < len(k1) < len(k0):
            tambahan = rnd.choices(k1, k=len(k0) - len(k1))
            data_train = k0 + k1 + tambahan
            rnd.shuffle(data_train)
            print(f"Oversampling train (kelas minoritas): {len(k1)} -> {len(k0)} (total train={len(data_train)})")

    ds_train = buat_dataset(data_train, cfg["ukuran"], cfg["batch"], acak=True,
                            augment=True, flip=cfg.get("flip", True))
    ds_val = buat_dataset(bagian["val"], cfg["ukuran"], cfg["batch"], acak=False, augment=False)

    y = np.array([x[1] for x in data_train])
    n, n1 = len(y), int(y.sum())
    n0 = n - n1
    bobot = {0: n / (2 * max(n0, 1)), 1: n / (2 * max(n1, 1))}
    print(f"Class weight: tidak={bobot[0]:.2f}  pakai={bobot[1]:.2f}")

    loss_fn = keras.losses.BinaryCrossentropy(label_smoothing=cfg.get("label_smoothing", 0.0))
    model.compile(
        optimizer=keras.optimizers.Adam(cfg["learning_rate"]),
        loss=loss_fn,
        metrics=["accuracy", keras.metrics.Precision(name="precision"), keras.metrics.Recall(name="recall")],
    )
    model.summary()

    path_model_str = str(cfg["path_model"])
    csv_log_str = str(folder_laporan / "riwayat_training.csv")
    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=cfg["patience"], restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=max(cfg["patience"] // 2, 2)),
        SafeModelCheckpoint(path_model_str, monitor="val_loss", save_best_only=True),
        SafeCSVLogger(csv_log_str),
    ]
    riwayat = model.fit(ds_train, validation_data=ds_val, epochs=cfg["epochs"],
                        class_weight=bobot, callbacks=callbacks)

    # Tahap 2 (opsional): fine-tuning tipis lapisan atas backbone Transfer Learning
    if cfg.get("finetune_epochs", 0) > 0:
        for layer in model.layers:
            if isinstance(layer, keras.Model):
                layer.trainable = True
                for sub in layer.layers[:-cfg.get("finetune_layers", 15)]:
                    sub.trainable = False
        model.compile(
            optimizer=keras.optimizers.Adam(cfg.get("finetune_lr", 5e-5)),
            loss=loss_fn,
            metrics=["accuracy", keras.metrics.Precision(name="precision"), keras.metrics.Recall(name="recall")],
        )
        riwayat_ft = model.fit(
            ds_train, validation_data=ds_val,
            epochs=cfg["finetune_epochs"], class_weight=bobot,
            callbacks=[
                keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
                SafeModelCheckpoint(path_model_str, monitor="val_loss", save_best_only=True),
            ],
        )
        for k in riwayat.history:
            if k in riwayat_ft.history:
                riwayat.history[k] += riwayat_ft.history[k]

    grafik_training(riwayat.history, folder_laporan / "grafik_training.png")
    return model


def grafik_training(h, path):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(h["loss"], label="train")
    ax[0].plot(h["val_loss"], label="validasi")
    ax[0].set_title("Loss")
    ax[0].set_xlabel("epoch")
    ax[0].legend()
    ax[1].plot(h["accuracy"], label="train")
    ax[1].plot(h["val_accuracy"], label="validasi")
    ax[1].set_title("Akurasi")
    ax[1].set_xlabel("epoch")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- evaluasi & Matrik Pengujian (Biner)

def prediksi(model, isi, cfg):
    ds = buat_dataset(isi, cfg["ukuran"], cfg["batch"], acak=False, augment=False)
    return model.predict(ds, verbose=0).ravel(), np.array([x[1] for x in isi])


def pilih_threshold(prob, y, min_recall_tidak=0.95):
    """
    Pilih threshold dari data validasi:
    prioritas menangkap orang yang TIDAK memakai APD (recall kelas 'tidak' >= target),
    lalu di antara skor terbaik yang seri pilih yang paling dekat dengan 0.50 (aman untuk kamera live).
    """
    kandidat = []
    for t in np.arange(0.10, 0.91, 0.01):
        pred = (prob >= t).astype(int)
        rec_tidak = ((pred == 0) & (y == 0)).sum() / max((y == 0).sum(), 1)
        rec_pakai = ((pred == 1) & (y == 1)).sum() / max((y == 1).sum(), 1)
        skor = rec_pakai if rec_tidak >= min_recall_tidak else rec_tidak - 1
        kandidat.append((round(float(t), 2), float(skor)))
    maks = max(k[1] for k in kandidat)
    terbaik_list = [t for t, s in kandidat if abs(s - maks) < 1e-9]
    return min(terbaik_list, key=lambda t: abs(t - 0.50))


def evaluasi(model, bagian, cfg, folder_laporan, path_tflite=None):
    folder_laporan = Path(folder_laporan)
    p_val, y_val = prediksi(model, bagian["val"], cfg)
    t = pilih_threshold(p_val, y_val, cfg["min_recall_tidak"])
    p_test, y_test = prediksi(model, bagian["test"], cfg)
    pred = (p_test >= t).astype(int)

    nama = ["tidak", "pakai"]
    cm = confusion_matrix(y_test, pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    acc = float(accuracy_score(y_test, pred))
    prec_pakai = float(precision_score(y_test, pred, pos_label=1, zero_division=0))
    rec_pakai = float(recall_score(y_test, pred, pos_label=1, zero_division=0))
    f1_pakai = float(f1_score(y_test, pred, pos_label=1, zero_division=0))
    prec_tidak = float(precision_score(y_test, pred, pos_label=0, zero_division=0))
    rec_tidak = float(recall_score(y_test, pred, pos_label=0, zero_division=0))
    f1_tidak = float(f1_score(y_test, pred, pos_label=0, zero_division=0))
    macro_f1 = float(f1_score(y_test, pred, average="macro", zero_division=0))
    # Kebocoran APD = persentase kasus 'tidak pakai' yang salah lolos sebagai 'pakai'
    kebocoran_pct = (fp / max(tn + fp, 1)) * 100.0

    laporan = classification_report(y_test, pred, labels=[0, 1], target_names=nama, digits=4, zero_division=0)
    teks = (
        f"Area       : {cfg['area']}\n"
        f"Arsitektur : {cfg.get('arsitektur', 'CNN from scratch')}\n"
        f"Threshold  : {t} (dipilih dari data validasi)\n"
        f"Split      : train={len(bagian['train'])}, val={len(bagian['val'])}, test={len(bagian['test'])}\n\n"
        f"=== MATRIK PENGUJIAN (DATA TEST) ===\n"
        f"{laporan}\n"
        f"Confusion Matrix (baris=Asli, kolom=Prediksi) [tidak, pakai]:\n{cm}\n"
        f"  TN (Asli Tidak -> Pred Tidak) : {tn}\n"
        f"  FP (Asli Tidak -> Pred Pakai) : {fp}  [Kebocoran APD: {kebocoran_pct:.2f}%]\n"
        f"  FN (Asli Pakai -> Pred Tidak) : {fn}\n"
        f"  TP (Asli Pakai -> Pred Pakai) : {tp}\n"
        f"  Accuracy                      : {acc:.4f}\n"
        f"  Macro F1-Score                : {macro_f1:.4f}\n"
    )
    print("\n" + teks)
    (folder_laporan / "hasil_evaluasi.txt").write_text(teks, encoding="utf-8")

    metrik = {
        "komponen": cfg["area"],
        "tipe": "biner",
        "arsitektur": cfg.get("arsitektur", "CNN from scratch"),
        "pemilik": cfg.get("pemilik", "-"),
        "ukuran_input": list(cfg["ukuran"]) + [3],
        "jumlah_train": len(bagian["train"]),
        "jumlah_val": len(bagian["val"]),
        "jumlah_test": len(bagian["test"]),
        "threshold": t,
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "accuracy": round(acc, 4),
        "precision_pakai": round(prec_pakai, 4),
        "recall_pakai": round(rec_pakai, 4),
        "f1_pakai": round(f1_pakai, 4),
        "precision_tidak": round(prec_tidak, 4),
        "recall_tidak": round(rec_tidak, 4),
        "f1_tidak": round(f1_tidak, 4),
        "macro_f1": round(macro_f1, 4),
        "kebocoran_apd_pct": round(kebocoran_pct, 2),
    }
    (folder_laporan / "metrik_pengujian.json").write_text(json.dumps(metrik, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=14,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xticks([0, 1], nama)
    ax.set_yticks([0, 1], nama)
    ax.set_xlabel("Prediksi")
    ax.set_ylabel("Asli")
    ax.set_title(f"Confusion Matrix - {cfg['area']} (Acc: {acc*100:.1f}%)")
    fig.tight_layout()
    fig.savefig(folder_laporan / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    info = {
        "area": cfg["area"],
        "tipe": "biner",
        "ukuran": list(cfg["ukuran"]),
        "threshold": t,
        "path_model": str(cfg["path_model"]),
        "path_tflite": path_tflite,
        "label": {"0": "tidak", "1": "pakai"},
    }
    Path(cfg["path_model"]).with_suffix(".json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return t


# ---------------------------------------------------------------- Grad-CAM

def grad_cam(model, isi, cfg, folder_laporan, n=8, nama_conv="conv_terakhir", kelas_list=None):
    """Simpan contoh Grad-CAM: bagian gambar yang paling diperhatikan CNN."""
    try:
        conv = model.get_layer(nama_conv)
    except ValueError:
        print(f"Grad-CAM dilewati: layer '{nama_conv}' tidak ditemukan.")
        return

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
            if kelas_list is None:
                prob = float(out[0, 0])
                skor = out[:, 0] if prob >= 0.5 else 1 - out[:, 0]
                judul_asli = f"asli: {'pakai' if label else 'tidak'}"
                judul_pred = f"prob pakai {prob:.2f}"
            else:
                pred_idx = int(tf.argmax(out[0]))
                prob = float(out[0, pred_idx])
                skor = out[:, pred_idx]
                judul_asli = f"asli: {kelas_list[label]}"
                judul_pred = f"{kelas_list[pred_idx]} ({prob:.2f})"
        grad = tape.gradient(skor, fitur)
        bobot = tf.reduce_mean(grad, axis=(0, 1, 2))
        peta = tf.nn.relu(tf.reduce_sum(fitur[0] * bobot, axis=-1))
        peta = (peta / (tf.reduce_max(peta) + 1e-8)).numpy()
        peta = tf.image.resize(peta[..., None], cfg["ukuran"]).numpy()[..., 0]

        asli = img[0].numpy().astype("uint8")
        axes[0, k].imshow(asli)
        axes[0, k].axis("off")
        axes[0, k].set_title(judul_asli, fontsize=8)
        axes[1, k].imshow(asli)
        axes[1, k].imshow(peta, cmap="jet", alpha=0.45)
        axes[1, k].axis("off")
        axes[1, k].set_title(judul_pred, fontsize=8)
    fig.tight_layout()
    fig.savefig(Path(folder_laporan) / "grad_cam.png", dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- training & evaluasi multiclass (Wajah)

def jalankan_multikelas(cfg, build_model):
    """Pipeline lengkap untuk model multiclass (misal pengenalan wajah Transfer Learning)."""
    keras.utils.set_random_seed(cfg.get("seed", 42))
    folder_laporan = Path("laporan") / cfg["area"]
    folder_laporan.mkdir(parents=True, exist_ok=True)
    Path(cfg["path_model"]).parent.mkdir(parents=True, exist_ok=True)

    bagian, kelas_list = muat_data_multikelas(cfg["folder_dataset"], seed=cfg.get("seed", 42))
    n_kelas = len(kelas_list)

    ds_train = buat_dataset(bagian["train"], cfg["ukuran"], cfg["batch"], acak=True,
                            augment=True, flip=cfg.get("flip", True), multiclass=True)
    ds_val = buat_dataset(bagian["val"], cfg["ukuran"], cfg["batch"], acak=False,
                          augment=False, multiclass=True)
    ds_test = buat_dataset(bagian["test"], cfg["ukuran"], cfg["batch"], acak=False,
                           augment=False, multiclass=True)

    # Class weight seimbang antar individu
    y_tr = np.array([x[1] for x in bagian["train"]])
    bobot = {i: len(y_tr) / (n_kelas * max(int((y_tr == i).sum()), 1)) for i in range(n_kelas)}

    model = build_model((*cfg["ukuran"], 3), n_kelas)
    model.compile(
        optimizer=keras.optimizers.Adam(cfg["learning_rate"]),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    model.summary()

    callbacks = [
        keras.callbacks.EarlyStopping(monitor="val_loss", patience=cfg["patience"], restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=max(cfg["patience"] // 2, 2)),
        SafeModelCheckpoint(cfg["path_model"], monitor="val_loss", save_best_only=True),
        SafeCSVLogger(str(folder_laporan / "riwayat_training.csv")),
    ]
    riwayat = model.fit(ds_train, validation_data=ds_val, epochs=cfg["epochs"],
                        class_weight=bobot, callbacks=callbacks)

    # Tahap 2 (opsional): fine-tuning ringan lapisan atas backbone Transfer Learning
    if cfg.get("finetune_epochs", 0) > 0:
        for layer in model.layers:
            if isinstance(layer, keras.Model):  # backbone MobileNetV2
                layer.trainable = True
                for sub in layer.layers[:-cfg.get("finetune_layers", 20)]:
                    sub.trainable = False
        model.compile(
            optimizer=keras.optimizers.Adam(cfg.get("finetune_lr", 1e-4)),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        riwayat_ft = model.fit(
            ds_train, validation_data=ds_val,
            epochs=cfg["finetune_epochs"], class_weight=bobot,
            callbacks=[
                keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
                SafeModelCheckpoint(cfg["path_model"], monitor="val_loss", save_best_only=True),
            ],
        )
        for k in riwayat.history:
            if k in riwayat_ft.history:
                riwayat.history[k] += riwayat_ft.history[k]

    grafik_training(riwayat.history, folder_laporan / "grafik_training.png")

    # Ekspor TFLite ringan untuk PythonAnywhere
    path_tflite = ekspor_tflite(model, cfg["path_model"])

    # Evaluasi Matrik Pengujian pada data test
    prob_test = model.predict(ds_test, verbose=0)
    y_test = np.array([x[1] for x in bagian["test"]])
    pred_test = np.argmax(prob_test, axis=1)

    cm = confusion_matrix(y_test, pred_test, labels=list(range(n_kelas)))
    acc = float(accuracy_score(y_test, pred_test))
    macro_prec = float(precision_score(y_test, pred_test, average="macro", zero_division=0))
    macro_rec = float(recall_score(y_test, pred_test, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_test, pred_test, average="macro", zero_division=0))

    laporan = classification_report(y_test, pred_test, labels=list(range(n_kelas)),
                                    target_names=kelas_list, digits=4, zero_division=0)
    teks = (
        f"Komponen   : {cfg['area']}\n"
        f"Arsitektur : {cfg.get('arsitektur', 'Transfer Learning MobileNetV2')}\n"
        f"Kelas      : {kelas_list}\n"
        f"Threshold  : {cfg.get('confidence_threshold', 0.75)}\n"
        f"Split      : train={len(bagian['train'])}, val={len(bagian['val'])}, test={len(bagian['test'])}\n\n"
        f"=== MATRIK PENGUJIAN (DATA TEST) ===\n"
        f"{laporan}\n"
        f"Confusion Matrix (baris=Asli, kolom=Prediksi) {kelas_list}:\n{cm}\n"
        f"  Accuracy        : {acc:.4f}\n"
        f"  Macro Precision : {macro_prec:.4f}\n"
        f"  Macro Recall    : {macro_rec:.4f}\n"
        f"  Macro F1-Score  : {macro_f1:.4f}\n"
    )
    print("\n" + teks)
    (folder_laporan / "hasil_evaluasi.txt").write_text(teks, encoding="utf-8")

    metrik = {
        "komponen": cfg["area"],
        "tipe": "multikelas",
        "arsitektur": cfg.get("arsitektur", "Transfer Learning MobileNetV2"),
        "pemilik": cfg.get("pemilik", "-"),
        "kelas": kelas_list,
        "ukuran_input": list(cfg["ukuran"]) + [3],
        "jumlah_train": len(bagian["train"]),
        "jumlah_val": len(bagian["val"]),
        "jumlah_test": len(bagian["test"]),
        "threshold": cfg.get("confidence_threshold", 0.75),
        "confusion_matrix": cm.tolist(),
        "accuracy": round(acc, 4),
        "macro_precision": round(macro_prec, 4),
        "macro_recall": round(macro_rec, 4),
        "macro_f1": round(macro_f1, 4),
    }
    (folder_laporan / "metrik_pengujian.json").write_text(json.dumps(metrik, indent=2), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(5.2, 4.5))
    ax.imshow(cm, cmap="Blues")
    for i in range(n_kelas):
        for j in range(n_kelas):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=13,
                    color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xticks(range(n_kelas), kelas_list)
    ax.set_yticks(range(n_kelas), kelas_list)
    ax.set_xlabel("Prediksi")
    ax.set_ylabel("Asli")
    ax.set_title(f"Confusion Matrix - Wajah (Acc: {acc*100:.1f}%)")
    fig.tight_layout()
    fig.savefig(folder_laporan / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    info = {
        "area": cfg["area"],
        "tipe": "multikelas",
        "ukuran": list(cfg["ukuran"]),
        "threshold": cfg.get("confidence_threshold", 0.75),
        "kelas": kelas_list,
        "path_model": str(cfg["path_model"]),
        "path_tflite": path_tflite,
    }
    Path(cfg["path_model"]).with_suffix(".json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"\nSelesai. Model: {cfg['path_model']}  |  TFLite: {path_tflite}  |  Laporan: {folder_laporan}/")


# ---------------------------------------------------------------- jalankan biner (APD)

def jalankan(cfg, build_model):
    keras.utils.set_random_seed(cfg.get("seed", 42))
    folder_laporan = Path("laporan") / cfg["area"]
    bagian = muat_data(Path(cfg["folder_dataset"]) / cfg["area"], seed=cfg.get("seed", 42))
    model = build_model((*cfg["ukuran"], 3))
    model = latih(model, bagian, cfg, folder_laporan)
    path_tflite = ekspor_tflite(model, cfg["path_model"])
    evaluasi(model, bagian, cfg, folder_laporan, path_tflite=path_tflite)
    grad_cam(model, bagian["test"], cfg, folder_laporan)
    print(f"\nSelesai. Model: {cfg['path_model']}  |  TFLite: {path_tflite}  |  Laporan: {folder_laporan}/")
