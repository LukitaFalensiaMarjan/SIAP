# Matrik Pengujian Gabungan — 5 Model CNN (Simandiri CNN)

| Komponen | Pemilik | Arsitektur | Train / Val / Test | Accuracy (%) | Precision (Pakai) | Recall (Pakai) | Recall (Tidak) | Macro F1 | Kebocoran APD (%) | Threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HELM | Luki | Transfer Learning MobileNetV2 + Custom Head | 1276 / 273 / 274 | 96.72 | 0.9683 | 0.9606 | 0.9728 | 0.967 | 2.72 | 0.44 |
| BAJU | Basit | Transfer Learning MobileNetV2 + Custom Head | 1276 / 274 / 273 | 98.9 | 0.9826 | 1.0 | 0.9712 | 0.9883 | 2.88 | 0.5 |
| JEANS | Luki | Transfer Learning MobileNetV2 + Balanced Train | 1351 / 290 / 288 | 99.31 | 0.9913 | 1.0 | 0.9672 | 0.9895 | 3.28 | 0.5 |
| SEPATU | Chakim | Transfer Learning MobileNetV2 + Custom Head | 1350 / 289 / 290 | 99.31 | 0.9889 | 1.0 | 0.9821 | 0.9927 | 1.79 | 0.5 |
| WAJAH | Basit & Chakim | Transfer Learning MobileNetV2 + Custom Head | 168 / 37 / 34 | 94.12 | 0.9487 | 0.9524 | - | 0.9466 | - | 0.75 |


*Catatan: Kebocoran APD (%) = persentase kasus tidak memakai APD yang lolos sebagai 'pakai' (target <= 5%).*