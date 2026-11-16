"""
Training CNN deteksi SEPATU SAFETY (dibuat dari nol, tanpa model pretrained).

Jalankan dari folder proyek:
    python train_sepatu.py

Hasil:
    models/model_sepatu.keras + models/model_sepatu.json (threshold, ukuran input)
    laporan/sepatu/ (grafik training, confusion matrix, hasil evaluasi, Grad-CAM)

Catatan: data 'tidak' saat ini hanya kaki tanpa alas kaki, jadi model belum
dilatih membedakan sepatu safety dari sepatu biasa.
"""
from tensorflow import keras

from cnn_apd import jalankan, lapisan_augmentasi

CFG = {
    "area": "sepatu",                   # nama folder di dataset_area
    "folder_dataset": "dataset_area",
    "path_model": "models/model_sepatu.keras",
    "ukuran": (128, 128),               # tinggi, lebar input CNN
    "batch": 32,
    "epochs": 60,
    "learning_rate": 1e-3,
    "patience": 8,                      # early stopping
    "min_recall_tidak": 0.95,           # target: 95% orang tanpa sepatu safety harus tertangkap
    "seed": 42,
}


def build_model(input_shape):
    """Arsitektur CNN sepatu. Silakan ubah jumlah blok/filter untuk eksperimen."""
    x_in = keras.Input(shape=input_shape)
    x = lapisan_augmentasi(flip=True)(x_in)
    x = keras.layers.Rescaling(1.0 / 255)(x)

    for filter_ in (32, 64, 128):
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
    return keras.Model(x_in, x_out, name="cnn_sepatu")


if __name__ == "__main__":
    jalankan(CFG, build_model)
