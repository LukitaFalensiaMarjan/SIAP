# Matrik Pengujian Gabungan — 5 Model CNN (Simandiri CNN)

| Komponen | Pemilik | Arsitektur | Train / Val / Test | Accuracy (%) | Precision (Pakai) | Recall (Pakai) | Recall (Tidak) | Macro F1 | Kebocoran APD (%) | Threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HELM | Luki | Transfer Learning MobileNetV2 + Custom Head | 819 / 176 / 175 | 100.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5 |
| BAJU | Basit | Transfer Learning MobileNetV2 + Custom Head | 940 / 201 / 202 | 100.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5 |
| JEANS | Luki | Transfer Learning MobileNetV2 + Balanced Train | 1151 / 247 / 246 | 99.59 | 1.0 | 0.9957 | 1.0 | 0.9838 | 0.0 | 0.5 |
| SEPATU | Chakim | Transfer Learning MobileNetV2 + Custom Head | 854 / 183 / 184 | 100.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.5 |
| WAJAH | Basit & Chakim | Transfer Learning MobileNetV2 + Custom Head | 332 / 72 / 70 | 100.0 | 1.0 | 1.0 | - | 1.0 | - | 0.75 |


*Catatan: Kebocoran APD (%) = persentase kasus tidak memakai APD yang lolos sebagai 'pakai' (target <= 5%).*