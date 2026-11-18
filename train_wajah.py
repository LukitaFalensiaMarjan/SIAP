"""
Training CNN PENGENALAN WAJAH (Transfer Learning MobileNetV2, citra RGB).
Kelas: Basit, Chakim, Luki (hasil crop ketat wajah saja tanpa baju).

Jalankan dari folder proyek:
    python train_wajah.py

Hasil:
    models/model_wajah.keras + models/model_wajah.tflite + models/model_wajah.json
    laporan/wajah/ (grafik training, confusion matrix 3x3, metrik pengujian)
"""
from tensorflow import keras

from cnn_apd import jalankan_multikelas

CFG = {
    "area": "wajah",
    "arsitektur": "Transfer Learning MobileNetV2 + Custom Head",
    "pemilik": "Basit & Chakim",
    "folder_dataset": "dataset_wajah",
    "path_model": "models/model_wajah.keras",
    "ukuran": (128, 128),
    "batch": 16,
    "epochs": 25,
    "learning_rate": 1e-3,
    "patience": 6,
    "finetune_epochs": 12,
    "finetune_layers": 20,
    "finetune_lr": 1e-4,
    "confidence_threshold": 0.75,
    "flip": True,
    "seed": 42,
}


def build_model(input_shape, n_kelas):
    """Transfer Learning MobileNetV2 untuk klasifikasi wajah RGB (128x128x3)."""
    x_in = keras.Input(shape=input_shape)
    # Normalisasi MobileNetV2: [0, 255] -> [-1, 1]
    x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0)(x_in)

    backbone = keras.applications.MobileNetV2(
        input_shape=input_shape,
        include_top=False,
        weights="imagenet",
    )
    backbone.trainable = False  # tahap 1: freeze backbone, latih head dulu

    x = backbone(x, training=False)
    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.4)(x)
    x = keras.layers.Dense(128, activation="relu",
                           kernel_regularizer=keras.regularizers.l2(1e-3))(x)
    x = keras.layers.Dropout(0.3)(x)
    x_out = keras.layers.Dense(n_kelas, activation="softmax")(x)
    return keras.Model(x_in, x_out, name="cnn_wajah_mobilenetv2")


if __name__ == "__main__":
    jalankan_multikelas(CFG, build_model)
