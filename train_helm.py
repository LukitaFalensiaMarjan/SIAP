"""
Training CNN deteksi HELM SAFETY (Transfer Learning MobileNetV2 + Custom Head, citra RGB).
Backbone MobileNetV2 dibekukan pada tahap 1 lalu fine-tuning tipis agar tahan beda ruangan.

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
    "arsitektur": "Transfer Learning MobileNetV2 + Custom Head",
    "pemilik": "Luki",
    "folder_dataset": "dataset_area",
    "path_model": "models/model_helm.keras",
    "ukuran": (96, 96),
    "batch": 32,
    "epochs": 20,
    "learning_rate": 8e-4,
    "patience": 6,
    "finetune_epochs": 8,
    "finetune_layers": 10,
    "finetune_lr": 3e-5,
    "label_smoothing": 0.05,
    "min_recall_tidak": 0.95,
    "flip": True,
    "seed": 42,
}


def build_model(input_shape):
    """Transfer Learning MobileNetV2 untuk deteksi helm safety (citra RGB 96x96x3)."""
    x_in = keras.Input(shape=input_shape)
    x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0)(x_in)

    backbone = keras.applications.MobileNetV2(
        input_shape=input_shape,
        include_top=False,
        weights="imagenet",
    )
    backbone.trainable = False

    x = backbone(x, training=False)
    # Lapisan adaptasi fitur kustom + nama 'conv_terakhir' untuk Grad-CAM
    x = keras.layers.Conv2D(128, 1, padding="same", use_bias=False)(x)
    x = keras.layers.BatchNormalization(momentum=0.9)(x)
    x = keras.layers.ReLU(name="conv_terakhir")(x)

    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.5)(x)
    x = keras.layers.Dense(64, activation="relu",
                           kernel_regularizer=keras.regularizers.l2(1e-3))(x)
    x = keras.layers.Dropout(0.3)(x)
    x_out = keras.layers.Dense(1, activation="sigmoid")(x)
    return keras.Model(x_in, x_out, name="cnn_helm_mobilenetv2")


if __name__ == "__main__":
    jalankan(CFG, build_model)
