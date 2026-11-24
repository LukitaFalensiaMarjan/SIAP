import base64
import binascii
import json
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
MODEL_STEMS = {
    "helm": "model_helm",
    "baju": "model_kemeja",
    "jeans": "model_jeans",
    "sepatu": "model_sepatu",
    "wajah": "model_wajah",
}
APD_ITEMS = ("helm", "baju", "jeans", "sepatu")
APD_SCAN_FRAME_COUNT = 8
# Tiga Tingkat Ambang Batas APD:
# >= 0.85 (85% ke atas): Otomatis Sesuai / OK
# 0.75 s.d. 0.84 (75% - 84%): Verifikasi Admin / PLP
# < 0.75 (di bawah 75%): Kurang / Tidak Terpakai
APD_THRESHOLD_VALID = 0.85
APD_THRESHOLD_VERIFY = 0.75
APD_THRESHOLD_ON = 0.85
APD_THRESHOLD_OFF = 0.70
APD_SCAN_CENTERS = (0.47, 0.50, 0.53)
FACE_SCAN_FRAME_COUNT = 4
FACE_CROP_MODES = ("hog", "guide")

# Grid Scanning APD yang terkunci ketat di dalam Siluet Manusia Berdiri (Koridor Tengah)
APD_SCAN_GRID = {
    "helm": (0.24, ((0.03, 0.22), (0.06, 0.25))),
    "baju": (0.32, ((0.22, 0.50), (0.26, 0.54))),
    "jeans": (0.30, ((0.50, 0.80), (0.54, 0.85))),
    "sepatu": (0.26, ((0.80, 0.98), (0.83, 1.00))),
}
APD_DISPLAY = {
    "helm": {"label": "Helm Safety", "color": "#FACC15"},
    "baju": {"label": "Baju Praktik", "color": "#22C55E"},
    "jeans": {"label": "Celana Jeans", "color": "#38BDF8"},
    "sepatu": {"label": "Sepatu Safety", "color": "#E879F9"},
}
MODEL_LOCK = threading.RLock()

# Batas Geometris Ketat Garis Panduan (Strict Guide Zone)
# Sumbu tengah frame: 0.50
# Koridor Siluet Kepala & Tubuh: Horizontal 0.39 s.d. 0.61 (menolak siapapun yang berdiri di luar garis panduan)
# Vertikal: 0.04 s.d. 0.30 (hanya mendeteksi kepala mahasiswa yang berdiri tepat di dalam siluet kepala)
GUIDE_FACE_MIN_X = 0.39
GUIDE_FACE_MAX_X = 0.61
GUIDE_FACE_MIN_Y = 0.04
GUIDE_FACE_MAX_Y = 0.30
GUIDE_FACE_MAX_HEIGHT_RATIO = 0.25


@dataclass(frozen=True)
class LoadedModel:
    interpreter: Any
    input_index: int
    output_index: int
    height: int
    width: int
    threshold: float
    classes: tuple[str, ...]


_models: dict[str, LoadedModel] = {}


def decode_frame(image_data: str) -> np.ndarray:
    if not isinstance(image_data, str) or len(image_data) > 3_000_000:
        raise ValueError("Ukuran gambar tidak valid atau terlalu besar")

    encoded = image_data
    if image_data.startswith("data:"):
        header, separator, encoded = image_data.partition(",")
        if not separator or not header.startswith(("data:image/jpeg;base64", "data:image/png;base64")):
            raise ValueError("Format gambar harus JPEG atau PNG")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Data gambar tidak valid") from exc
    if len(raw) > 2_000_000:
        raise ValueError("Ukuran gambar melebihi batas 2 MB")

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Gambar tidak dapat dibaca")
    height, width = frame.shape[:2]
    if width < 320 or height < 240:
        raise ValueError("Resolusi kamera minimal 320x240")
    if width > 1920 or height > 1080:
        raise ValueError("Resolusi gambar maksimal 1920x1080")
    return frame


def _load_model(item: str) -> LoadedModel:
    if item not in MODEL_STEMS:
        raise ValueError(f"Model {item} tidak dikenal")
    with MODEL_LOCK:
        cached = _models.get(item)
        if cached:
            return cached

        stem = MODEL_STEMS[item]
        metadata_path = ROOT / "models" / f"{stem}.json"
        model_path = ROOT / "models" / f"{stem}.tflite"
        if not metadata_path.is_file() or not model_path.is_file():
            raise FileNotFoundError(f"Model TFLite {item} belum tersedia")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        size = metadata.get("ukuran")
        if not isinstance(size, list) or len(size) != 2:
            raise ValueError(f"Metadata ukuran input model {item} tidak valid")

        import tensorflow as tf

        interpreter = tf.lite.Interpreter(model_path=str(model_path))
        interpreter.allocate_tensors()
        input_detail = interpreter.get_input_details()[0]
        output_detail = interpreter.get_output_details()[0]
        input_shape = tuple(int(value) for value in input_detail["shape"])
        if (
            input_shape != (1, int(size[0]), int(size[1]), 3)
            or input_detail["dtype"] != np.float32
            or output_detail["dtype"] != np.float32
        ):
            raise ValueError(f"Format tensor model {item} tidak sesuai metadata")

        loaded = LoadedModel(
            interpreter=interpreter,
            input_index=int(input_detail["index"]),
            output_index=int(output_detail["index"]),
            height=int(size[0]),
            width=int(size[1]),
            threshold=float(metadata["threshold"]),
            classes=tuple(metadata.get("kelas", ())),
        )
        _models[item] = loaded
        return loaded


def _predict(item: str, crop_bgr: np.ndarray) -> np.ndarray:
    model = _load_model(item)
    if crop_bgr.size == 0:
        raise ValueError(f"Area gambar untuk {item} kosong")
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(
        rgb, (model.width, model.height), interpolation=cv2.INTER_AREA
    )
    tensor = np.expand_dims(resized.astype(np.float32), axis=0)
    with MODEL_LOCK:
        model.interpreter.set_tensor(model.input_index, tensor)
        model.interpreter.invoke()
        return np.asarray(
            model.interpreter.get_tensor(model.output_index)[0], dtype=np.float32
        )


@lru_cache(maxsize=1)
def _face_detector() -> Any:
    import dlib

    return dlib.get_frontal_face_detector()


def _face_crop_and_box(frame: np.ndarray, crop_mode: str) -> tuple[np.ndarray | None, list[int] | None, int, str]:
    height, width = frame.shape[:2]
    if crop_mode == "guide":
        side = int(min(height, width) * 0.35)
        x0 = (width - side) // 2
        y0 = max(0, int(height * 0.06))
        x1 = min(width, x0 + side)
        y1 = min(height, y0 + side)
        if x1 > x0 and y1 > y0:
            return frame[y0:y1, x0:x1], [x0, y0, x1, y1], 1, "ok"
        return None, None, 0, "none"
    if crop_mode != "hog":
        raise ValueError(f"Mode crop wajah tidak dikenal: {crop_mode}")

    scale = 0.5 if width > 640 else 1.0
    detection_frame = (
        cv2.resize(frame, (int(width * scale), int(height * scale)))
        if scale < 1.0
        else frame
    )
    rgb = cv2.cvtColor(detection_frame, cv2.COLOR_BGR2RGB)
    faces = _face_detector()(rgb, 0)
    if not faces and scale < 1.0:
        detection_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = _face_detector()(rgb, 0)
        scale = 1.0
    if not faces:
        faces = _face_detector()(rgb, 1)
    if not faces:
        return None, None, 0, "none"

    face_count = len(faces)

    # VALIDASI KETAT SILUET MANUSIA BERDIRI:
    # 1. Wajah di luar garis siluet kepala TIDAK BOLEH dideteksi sama sekali
    # 2. Pengguna yang terlalu dekat (duduk dekat webcam) tidak boleh dideteksi
    # 3. Pembatasan multi-person: tidak boleh lebih dari 1 orang di area presensi
    valid_candidates = []
    outside_count = 0

    for rect in faces:
        # Konversi langsung koordinat bounding box ke resolusi asli frame penuh
        x0 = int(rect.left() / scale)
        y0 = int(rect.top() / scale)
        x1 = int(rect.right() / scale)
        y1 = int(rect.bottom() / scale)

        fcx = (x0 + x1) / (2.0 * width)
        fcy = (y0 + y1) / (2.0 * height)
        fnh = (y1 - y0) / float(height)
        area = (x1 - x0) * (y1 - y0)

        in_x = (GUIDE_FACE_MIN_X <= fcx <= GUIDE_FACE_MAX_X)
        in_y = (GUIDE_FACE_MIN_Y <= fcy <= GUIDE_FACE_MAX_Y)
        not_too_huge = (fnh <= GUIDE_FACE_MAX_HEIGHT_RATIO)

        if in_x and in_y and not_too_huge:
            center_dist = abs(fcx - 0.50)
            score = area * max(0.12, 1.0 - 2.0 * (center_dist ** 1.1))
            valid_candidates.append(([x0, y0, x1, y1], score))
        else:
            outside_count += 1

    # Jika tidak ada satupun wajah di dalam koridor garis siluet:
    if not valid_candidates:
        return None, None, face_count, "outside"

    # PILIH HANYA 1 ORANG YANG PALING UTAMA DI DALAM GARIS SILUET!
    # Siapapun di luar garis siluet (misal orang di samping/belakang) OTOMATIS DIABAIKAN.
    x0, y0, x1, y1 = max(valid_candidates, key=lambda item: item[1])[0]

    face_width = x1 - x0
    face_height = y1 - y0
    x0 = max(0, int(x0 - face_width * 0.05))
    x1 = min(width, int(x1 + face_width * 0.05))
    y0 = max(0, int(y0 - face_height * 0.12))
    y1 = min(height, int(y1 - face_height * 0.02))
    if x1 <= x0 + 20 or y1 <= y0 + 20:
        return None, None, face_count, "none"
    return frame[y0:y1, x0:x1], [x0, y0, x1, y1], face_count, "ok"


def _face_probabilities_and_box(
    frame: np.ndarray, crop_mode: str
) -> tuple[np.ndarray | None, list[int] | None, list[int], int, str]:
    flipped = cv2.flip(frame, 1)
    height, width = flipped.shape[:2]
    crop, box, face_count, reason = _face_crop_and_box(flipped, crop_mode)
    if crop is None:
        return None, None, [width, height], face_count, reason
    return _predict("wajah", crop), box, [width, height], face_count, reason


def _face_result(
    probabilities: np.ndarray | None,
    model: LoadedModel,
    student_name: str,
    box: list[int] | None = None,
    dimensions: list[int] | None = None,
    face_count: int = 0,
    reason: str = "none",
) -> dict[str, Any]:
    dims = dimensions or [640, 480]

    # Jika tidak ada wajah di dalam garis siluet:
    if probabilities is None:
        return {
            "detected": False,
            "matched": False,
            "label": None,
            "confidence": 0.0,
            "threshold": model.threshold,
            "classes": list(model.classes),
            "probabilities": None,
            "box": None,
            "dimensions": dims,
            "multi_person": face_count > 1,
            "face_count": face_count,
            "reason": reason,
        }

    if len(probabilities) != len(model.classes) or not model.classes:
        raise ValueError("Label model wajah tidak sesuai dengan output model")
    index = int(np.argmax(probabilities))
    label = model.classes[index]
    name_tokens = set(re.findall(r"[a-z0-9]+", student_name.casefold()))
    confidence = float(probabilities[index])
    matches_name = any(
        label.casefold() in token or token in label.casefold()
        for token in name_tokens
    )
    return {
        "detected": True,
        "matched": matches_name and confidence >= model.threshold,
        "label": label,
        "confidence": confidence,
        "threshold": model.threshold,
        "classes": list(model.classes),
        "probabilities": [float(value) for value in probabilities],
        "box": box,
        "dimensions": dims,
        "multi_person": face_count > 1,
        "face_count": face_count,
        "reason": "ok",
    }


def infer_face(
    frame: np.ndarray, student_name: str, crop_mode: str = "hog"
) -> dict[str, Any]:
    model = _load_model("wajah")
    probs, box, dims, face_count, reason = _face_probabilities_and_box(frame, crop_mode)
    return _face_result(
        probs, model, student_name, box=box, dimensions=dims, face_count=face_count, reason=reason
    )


def infer_face_sequence(
    frames: list[np.ndarray], student_name: str, crop_mode: str = "hog"
) -> dict[str, Any]:
    if len(frames) != FACE_SCAN_FRAME_COUNT:
        raise ValueError(
            f"Verifikasi wajah membutuhkan {FACE_SCAN_FRAME_COUNT} frame"
        )

    model = _load_model("wajah")
    probability_history = []
    current_probabilities = None
    last_box = None
    last_dims = [640, 480]
    last_face_count = 0
    for frame in frames:
        probabilities, box, dims, face_count = _face_probabilities_and_box(frame, crop_mode)
        last_dims = dims
        last_face_count = face_count
        if probabilities is None:
            probability_history.clear()
            current_probabilities = None
            continue
        last_box = box
        if len(probabilities) != len(model.classes) or not model.classes:
            raise ValueError("Label model wajah tidak sesuai dengan output model")
        probability_history.append(probabilities)
        probability_history = probability_history[-FACE_SCAN_FRAME_COUNT:]
        current_probabilities = np.mean(probability_history, axis=0)
    return _face_result(
        current_probabilities, model, student_name, box=last_box, dimensions=last_dims, face_count=last_face_count
    )


def infer_apd(
    frames: list[np.ndarray], required_items: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    if len(frames) != APD_SCAN_FRAME_COUNT:
        raise ValueError(
            f"Pemindaian APD membutuhkan {APD_SCAN_FRAME_COUNT} frame"
        )
    if required_items is None:
        required_items = set(APD_ITEMS)

    probabilities = {item: 0.0 for item in APD_ITEMS}
    scan_counts = {item: 0 for item in APD_ITEMS}
    detected = {item: False for item in APD_ITEMS}
    last_boxes = {item: None for item in APD_ITEMS}
    last_dims = [640, 480]

    for frame_index, source_frame in enumerate(frames):
        frame = cv2.flip(source_frame, 1)
        height, width = frame.shape[:2]
        last_dims = [width, height]
        item = APD_ITEMS[frame_index % len(APD_ITEMS)]
        if item not in required_items:
            continue
        crop_width_ratio, y_ranges = APD_SCAN_GRID[item]
        crop_width = int(width * crop_width_ratio)
        best_probability = 0.0
        best_box = None

        for top, bottom in y_ranges:
            y0, y1 = int(height * top), int(height * bottom)
            for center_x in APD_SCAN_CENTERS:
                x0 = max(0, int(width * center_x - crop_width / 2))
                x1 = min(width, x0 + crop_width)
                crop = frame[y0:y1, x0:x1]
                if crop.size == 0:
                    continue
                probability = float(_predict(item, crop)[0])
                if probability > best_probability:
                    best_probability = probability
                    best_box = [x0, y0, x1, y1]

        if best_box is not None and (
            best_probability >= APD_THRESHOLD_OFF or last_boxes[item] is None
        ):
            last_boxes[item] = best_box

        previous_count = scan_counts[item]
        probabilities[item] = (
            best_probability
            if previous_count == 0
            else 0.35 * best_probability + 0.65 * probabilities[item]
        )
        scan_counts[item] += 1

        p = probabilities[item]
        worn = (p >= APD_THRESHOLD_VALID)
        needs_verify = (APD_THRESHOLD_VERIFY <= p < APD_THRESHOLD_VALID)
        color = "#22C55E" if worn else ("#F59E0B" if needs_verify else "#EF4444")
        status_text = "OK" if worn else ("Verifikasi Admin" if needs_verify else "Kurang")

    return {
        item: {
            "probability": probabilities[item],
            "threshold": APD_THRESHOLD_VALID,
            "threshold_verify": APD_THRESHOLD_VERIFY,
            "worn": worn,
            "verifikasi_admin": needs_verify,
            "status_text": status_text,
            "box": last_boxes[item] if (worn or needs_verify) else None,
            "label": APD_DISPLAY[item]["label"],
            "color": color,
            "dimensions": last_dims,
        }
        for item in APD_ITEMS
    }


def infer_single_frame_apd(
    frame: np.ndarray,
    required_items: set[str] | None = None,
    previous_ema: dict[str, float] | None = None,
    previous_detected: dict[str, bool] | None = None,
    face_box: list[int] | None = None,
    face_detected_inside: bool = False,
) -> dict[str, dict[str, Any]]:
    if required_items is None:
        required_items = set(APD_ITEMS)

    prev_ema = previous_ema or {}
    prev_det = previous_detected or {}

    flipped = cv2.flip(frame, 1)
    height, width = flipped.shape[:2]
    dimensions = [width, height]

    # JIKA TIDAK ADA WAJAH VALID DI DALAM SILUET: JANGAN DETEKSI APD SAMA SEKALI!
    # Mengabaikan apapun di luar garis siluet agar tidak salah mendeteksi pakaian/benda sekitar
    if not face_detected_inside or not face_box:
        return {
            item: {
                "probability": 0.0,
                "threshold": APD_THRESHOLD_ON,
                "worn": False,
                "box": None,
                "label": APD_DISPLAY[item]["label"],
                "color": APD_DISPLAY[item]["color"],
                "dimensions": dimensions,
            }
            for item in APD_ITEMS
        }

    # Koordinat jangkar anatomi tubuh dinamis berbasis face_box
    fx0, fy0, fx1, fy1 = face_box
    fw = max(20, fx1 - fx0)
    fh = max(20, fy1 - fy0)
    fcx = (fx0 + fx1) // 2

    # Deteksi pose duduk / setengah badan (half body):
    # Dagu di bawah 36% tinggi frame atau rasio tinggi wajah > 22% tinggi frame
    is_half_body = (fy1 > 0.36 * height) or (fh > 0.22 * height)

    results = {}
    for item in APD_ITEMS:
        if item not in required_items:
            results[item] = {
                "probability": 0.0,
                "threshold": APD_THRESHOLD_ON,
                "worn": False,
                "box": None,
                "label": APD_DISPLAY[item]["label"],
                "color": APD_DISPLAY[item]["color"],
                "dimensions": dimensions,
                "reason": "not_required",
            }
            continue

        # JIKA DUDUK / SETENGAH BADAN: JEANS DAN SEPATU DI BAWAH MEJA (JANGAN DITEBAK DI DADA/PERUT)
        if is_half_body and item in ("jeans", "sepatu"):
            results[item] = {
                "probability": 0.0,
                "threshold": APD_THRESHOLD_ON,
                "worn": False,
                "box": None,
                "label": APD_DISPLAY[item]["label"],
                "color": APD_DISPLAY[item]["color"],
                "dimensions": dimensions,
                "reason": "half_body",
                "notice": "Silakan berdiri & mundur agar terlihat",
            }
            continue

        # Tentukan kandidat crop dinamis sesuai posisi fisik tubuh yang sebenarnya
        candidate_boxes = []
        if item == "helm":
            # Tepat di atas dahi dan kepala mahasiswa
            hy0 = max(0, fy0 - int(fh * 1.05))
            hy1 = min(height, fy0 + int(fh * 0.20))
            hw = int(fw * 1.25)
            hx0 = max(0, fcx - hw // 2)
            hx1 = min(width, fcx + hw // 2)
            candidate_boxes.append([hx0, hy0, hx1, hy1])
            candidate_boxes.append([max(0, hx0 - int(fw * 0.15)), max(0, hy0 - int(fh * 0.10)), min(width, hx1 - int(fw * 0.15)), hy1])
            candidate_boxes.append([max(0, hx0 + int(fw * 0.15)), max(0, hy0 - int(fh * 0.10)), min(width, hx1 + int(fw * 0.15)), hy1])
        elif item == "baju":
            # Dari leher / bahu sampai dada
            by0 = max(0, fy1 - int(fh * 0.15))
            by1 = min(height, fy1 + int(fh * (2.20 if is_half_body else 2.60)))
            bw = int(fw * 1.85)
            bx0 = max(0, fcx - bw // 2)
            bx1 = min(width, fcx + bw // 2)
            candidate_boxes.append([bx0, by0, bx1, by1])
            candidate_boxes.append([max(0, bx0 - int(fw * 0.20)), by0, min(width, bx1 - int(fw * 0.20)), by1])
            candidate_boxes.append([max(0, bx0 + int(fw * 0.20)), by0, min(width, bx1 + int(fw * 0.20)), by1])
        elif item == "jeans":
            jy0 = min(height, fy1 + int(fh * 2.40))
            jy1 = min(height, fy1 + int(fh * 5.80))
            jw = int(fw * 1.50)
            jx0 = max(0, fcx - jw // 2)
            jx1 = min(width, fcx + jw // 2)
            if jy1 > jy0 + 30:
                candidate_boxes.append([jx0, jy0, jx1, jy1])
        elif item == "sepatu":
            sy0 = min(height - 20, fy1 + int(fh * 5.50))
            sy1 = height
            sw = int(fw * 1.40)
            sx0 = max(0, fcx - sw // 2)
            sx1 = min(width, fcx + sw // 2)
            if sy1 > sy0 + 20:
                candidate_boxes.append([sx0, sy0, sx1, sy1])

        best_p = 0.0
        best_box = None

        for cbox in candidate_boxes:
            cx0, cy0, cx1, cy1 = cbox
            if cx1 <= cx0 + 20 or cy1 <= cy0 + 20:
                continue
            crop = flipped[cy0:cy1, cx0:cx1]
            if crop.size == 0:
                continue
            p = float(_predict(item, crop)[0])

            # Peningkatan deteksi helm K3 oranye berbasis saturasi warna helm
            if item == "helm":
                crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                orange_mask = cv2.inRange(crop_hsv, (7, 85, 85), (25, 255, 255))
                orange_ratio = np.count_nonzero(orange_mask) / orange_mask.size
                if orange_ratio >= 0.08:
                    p = max(p, 0.70 + 0.28 * min(1.0, orange_ratio * 4.0))

            if p > best_p:
                best_p = p
                best_box = cbox

        old_ema = float(prev_ema.get(item, 0.0))
        new_ema = best_p if old_ema == 0.0 else (0.40 * best_p + 0.60 * old_ema)

        # Evaluasi Tiga Tingkat Ambang Batas APD:
        # 1. >= 0.85 (85% ke atas): Otomatis Sesuai / OK (Hijau)
        # 2. 0.75 s.d. 0.84 (75% - 84%): Verifikasi Admin / PLP (Amber / Oranye)
        # 3. < 0.75 (di bawah 75%): Kurang / Tidak Terpakai (Merah)
        if new_ema >= APD_THRESHOLD_VALID:
            is_worn = True
            needs_verify = False
            status_text = "OK"
            item_color = "#22C55E"
        elif new_ema >= APD_THRESHOLD_VERIFY:
            is_worn = False
            needs_verify = True
            status_text = "Verifikasi Admin"
            item_color = "#F59E0B"
        else:
            is_worn = False
            needs_verify = False
            status_text = "Kurang"
            item_color = "#EF4444"

        results[item] = {
            "probability": new_ema,
            "threshold": APD_THRESHOLD_VALID,
            "threshold_verify": APD_THRESHOLD_VERIFY,
            "worn": is_worn,
            "verifikasi_admin": needs_verify,
            "status_text": status_text,
            "box": best_box if (is_worn or needs_verify) else None,
            "label": APD_DISPLAY[item]["label"],
            "color": item_color,
            "dimensions": dimensions,
            "is_half_body": is_half_body,
            "reason": "ok",
        }

    return results


def warmup_models() -> None:
    """Pre-load all TFLite models and the frontal face detector to avoid first-request delay."""
    for item in MODEL_STEMS:
        try:
            _load_model(item)
        except Exception as exc:
            print(f"[WARMUP] Error pre-loading {item}: {exc}")
    try:
        _face_detector()
    except Exception as exc:
        print(f"[WARMUP] Error pre-loading face detector: {exc}")

