"""
Training CNN deteksi CELANA JEANS (Transfer Learning MobileNetV2 + Custom Head, citra RGB).
Menggunakan balanced oversampling khusus pada data train (val/test tetap murni).

Jalankan dari folder proyek:
    python train_jeans.py

Hasil:
    models/model_jeans.keras + models/model_jeans.tflite + models/model_jeans.json
    laporan/jeans/ (grafik training, confusion matrix, metrik pengujian, Grad-CAM)
"""
from tensorflow import keras

from cnn_apd import jalankan

CFG = {
    "area": "jeans",
    "arsitektur": "Transfer Learning MobileNetV2 + Balanced Train",
    "pemilik": "Luki",
    "folder_dataset": "dataset_area",
    "path_model": "models/model_jeans.keras",
    "ukuran": (128, 128),
    "batch": 32,
    "epochs": 15,
    "learning_rate": 8e-4,
    "patience": 5,
    "finetune_epochs": 6,
    "finetune_layers": 10,
    "finetune_lr": 3e-5,
    "label_smoothing": 0.05,
    "min_recall_tidak": 0.95,
    "oversample_train": True,
    "flip": True,
    "seed": 42,
}


def build_model(input_shape):
    """Transfer Learning MobileNetV2 untuk deteksi celana jeans (citra RGB 128x128x3)."""
    x_in = keras.Input(shape=input_shape)
    x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0)(x_in)

    backbone = keras.applications.MobileNetV2(
        input_shape=input_shape,
        include_top=False,
        weights="imagenet",
    )
    backbone.trainable = False

    x = backbone(x, training=False)
    x = keras.layers.Conv2D(128, 1, padding="same", use_bias=False)(x)
    x = keras.layers.BatchNormalization(momentum=0.9)(x)
    x = keras.layers.ReLU(name="conv_terakhir")(x)

    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.5)(x)
    x = keras.layers.Dense(64, activation="relu",
                           kernel_regularizer=keras.regularizers.l2(1e-3))(x)
    x = keras.layers.Dropout(0.3)(x)
    x_out = keras.layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(x_in, x_out, name="cnn_jeans_mobilenetv2")


if __name__ == "__main__":
    jalankan(CFG, build_model)
