"""
Training CNN deteksi HELM SAFETY (dibuat dari nol / from scratch, citra RGB).

Jalankan dari folder proyek:
    python train_helm.py

Hasil:
    models/model_helm.keras + models/model_helm.tflite + models/model_helm.json
    laporan/helm/ (grafik training, confusion matrix, metrik pengujian, Grad-CAM)
"""
from tensorflow import keras

from cnn_apd import jalankan

CFG = {
    "area": "helm",
    "arsitektur": "CNN from scratch (3 blok Conv2D)",
    "pemilik": "Luki",
    "folder_dataset": "dataset_area",
    "path_model": "models/model_helm.keras",
    "ukuran": (96, 96),
    "batch": 16,
    "epochs": 60,
    "learning_rate": 5e-4,
    "patience": 10,
    "min_recall_tidak": 0.90,
    "flip": True,
    "seed": 42,
}


def build_model(input_shape):
    """Arsitektur CNN helm (input citra RGB 96x96x3)."""
    x_in = keras.Input(shape=input_shape)
    x = keras.layers.Rescaling(1.0 / 255)(x_in)

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
    x = keras.layers.Dense(64, activation="relu",
                           kernel_regularizer=keras.regularizers.l2(1e-3))(x)
    x = keras.layers.Dropout(0.5)(x)
    x_out = keras.layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(x_in, x_out, name="cnn_helm")


if __name__ == "__main__":
    jalankan(CFG, build_model)
