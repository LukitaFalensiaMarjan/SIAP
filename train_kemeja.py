"""
Training CNN deteksi BAJU PRAKTIK / KEMEJA (dibuat dari nol / from scratch, citra RGB).

Jalankan dari folder proyek:
    python train_kemeja.py

Hasil:
    models/model_kemeja.keras + models/model_kemeja.tflite + models/model_kemeja.json
    laporan/baju/ (grafik training, confusion matrix, metrik pengujian, Grad-CAM)
"""
from tensorflow import keras

from cnn_apd import jalankan

CFG = {
    "area": "baju",
    "arsitektur": "CNN from scratch (4 blok Conv2D)",
    "pemilik": "Basit",
    "folder_dataset": "dataset_area",
    "path_model": "models/model_kemeja.keras",
    "ukuran": (128, 128),
    "batch": 32,
    "epochs": 60,
    "learning_rate": 1e-3,
    "patience": 8,
    "min_recall_tidak": 0.95,
    "flip": True,
    "seed": 42,
}


def build_model(input_shape):
    """Arsitektur CNN baju praktik (input citra RGB 128x128x3)."""
    x_in = keras.Input(shape=input_shape)
    x = keras.layers.Rescaling(1.0 / 255)(x_in)

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
    return keras.Model(x_in, x_out, name="cnn_kemeja")


if __name__ == "__main__":
    jalankan(CFG, build_model)
