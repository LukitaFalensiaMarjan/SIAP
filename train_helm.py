"""
Training CNN deteksi HELM (dibuat dari nol, tanpa model pretrained).

Jalankan dari folder proyek:
    python train_helm.py

Hasil:
    models/model_helm.keras + models/model_helm.json (threshold, ukuran input)
    laporan/helm/ (grafik training, confusion matrix, hasil evaluasi, Grad-CAM)
"""
from tensorflow import keras

from cnn_apd import jalankan, lapisan_augmentasi

CFG = {
    "area": "helm",                     # nama folder di dataset_area
    "folder_dataset": "dataset_area",
    "path_model": "models/model_helm.keras",
    "ukuran": (96, 96),                 # tinggi, lebar input CNN
    "batch": 32,
    "epochs": 60,
    "learning_rate": 1e-3,
    "patience": 8,                      # early stopping
    "min_recall_tidak": 0.95,           # target: 95% orang tanpa helm harus tertangkap
    "seed": 42,
}


def build_model(input_shape):
    """Arsitektur CNN helm. Silakan ubah jumlah blok/filter untuk eksperimen."""
    x_in = keras.Input(shape=input_shape)
    x = lapisan_augmentasi(flip=True)(x_in)
    x = keras.layers.Rescaling(1.0 / 255)(x)

    for filter_ in (32, 64):
        x = keras.layers.Conv2D(filter_, 3, padding="same", use_bias=False)(x)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.ReLU()(x)
        x = keras.layers.MaxPooling2D()(x)

    # Blok terakhir diberi nama 'conv_terakhir' untuk Grad-CAM
    x = keras.layers.Conv2D(128, 3, padding="same", use_bias=False)(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.ReLU(name="conv_terakhir")(x)
    x = keras.layers.MaxPooling2D()(x)

    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dense(64, activation="relu")(x)
    x = keras.layers.Dropout(0.4)(x)
    x_out = keras.layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(x_in, x_out, name="cnn_helm")


if __name__ == "__main__":
    jalankan(CFG, build_model)
