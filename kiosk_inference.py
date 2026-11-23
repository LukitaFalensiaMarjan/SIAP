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
APD_THRESHOLD_ON = 0.75
APD_THRESHOLD_OFF = 0.58
APD_SCAN_CENTERS = (0.42, 0.50, 0.58)
FACE_SCAN_FRAME_COUNT = 4
FACE_CROP_MODES = ("hog", "guide")
APD_SCAN_GRID = {
    "helm": (0.26, ((0.02, 0.28), (0.14, 0.40))),
    "baju": (0.30, ((0.18, 0.54), (0.30, 0.66))),
    "jeans": (0.30, ((0.42, 0.80), (0.54, 0.92))),
    "sepatu": (0.28, ((0.64, 0.90), (0.76, 1.00))),
}
MODEL_LOCK = threading.RLock()


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


def _face_crop(frame: np.ndarray, crop_mode: str) -> np.ndarray | None:
    height, width = frame.shape[:2]
    if crop_mode == "guide":
        side = int(min(height, width) * 0.45)
        x0 = (width - side) // 2
        y0 = max(0, int(height * 0.18))
        x1 = min(width, x0 + side)
        y1 = min(height, y0 + side)
        return frame[y0:y1, x0:x1] if x1 > x0 and y1 > y0 else None
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
    if not faces:
        return None

    face = max(faces, key=lambda rect: rect.width() * rect.height())
    x0 = int(face.left() / scale)
    y0 = int(face.top() / scale)
    x1 = int(face.right() / scale)
    y1 = int(face.bottom() / scale)
    face_width = x1 - x0
    face_height = y1 - y0
    x0 = max(0, int(x0 - face_width * 0.05))
    x1 = min(width, int(x1 + face_width * 0.05))
    y0 = max(0, int(y0 - face_height * 0.12))
    y1 = min(height, int(y1 - face_height * 0.02))
    if x1 <= x0 + 20 or y1 <= y0 + 20:
        return None
    return frame[y0:y1, x0:x1]


def _face_probabilities(frame: np.ndarray, crop_mode: str) -> np.ndarray | None:
    crop = _face_crop(cv2.flip(frame, 1), crop_mode)
    if crop is None:
        return None
    return _predict("wajah", crop)


def _face_result(
    probabilities: np.ndarray | None,
    model: LoadedModel,
    student_name: str,
) -> dict[str, Any]:
    if probabilities is None:
        return {
            "detected": False,
            "matched": False,
            "label": None,
            "confidence": 0.0,
            "threshold": model.threshold,
            "classes": list(model.classes),
            "probabilities": None,
        }
    if len(probabilities) != len(model.classes) or not model.classes:
        raise ValueError("Label model wajah tidak sesuai dengan output model")
    index = int(np.argmax(probabilities))
    label = model.classes[index]
    name_tokens = set(re.findall(r"[a-z0-9]+", student_name.casefold()))
    confidence = float(probabilities[index])
    return {
        "detected": True,
        "matched": label.casefold() in name_tokens and confidence >= model.threshold,
        "label": label,
        "confidence": confidence,
        "threshold": model.threshold,
        "classes": list(model.classes),
        "probabilities": [float(value) for value in probabilities],
    }


def infer_face(
    frame: np.ndarray, student_name: str, crop_mode: str = "hog"
) -> dict[str, Any]:
    model = _load_model("wajah")
    return _face_result(_face_probabilities(frame, crop_mode), model, student_name)


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
    for frame in frames:
        probabilities = _face_probabilities(frame, crop_mode)
        if probabilities is None:
            probability_history.clear()
            current_probabilities = None
            continue
        if len(probabilities) != len(model.classes) or not model.classes:
            raise ValueError("Label model wajah tidak sesuai dengan output model")
        probability_history.append(probabilities)
        probability_history = probability_history[-FACE_SCAN_FRAME_COUNT:]
        current_probabilities = np.mean(probability_history, axis=0)
    return _face_result(current_probabilities, model, student_name)


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

    for frame_index, source_frame in enumerate(frames):
        frame = cv2.flip(source_frame, 1)
        height, width = frame.shape[:2]
        item = APD_ITEMS[frame_index % len(APD_ITEMS)]
        if item not in required_items:
            continue
        crop_width_ratio, y_ranges = APD_SCAN_GRID[item]
        crop_width = int(width * crop_width_ratio)
        best_probability = 0.0

        for top, bottom in y_ranges:
            y0, y1 = int(height * top), int(height * bottom)
            for center_x in APD_SCAN_CENTERS:
                x0 = max(0, int(width * center_x - crop_width / 2))
                x1 = min(width, x0 + crop_width)
                probability = float(_predict(item, frame[y0:y1, x0:x1])[0])
                best_probability = max(best_probability, probability)

        previous_count = scan_counts[item]
        probabilities[item] = (
            best_probability
            if previous_count == 0
            else 0.35 * best_probability + 0.65 * probabilities[item]
        )
        scan_counts[item] += 1

        if detected[item]:
            if probabilities[item] < APD_THRESHOLD_OFF:
                detected[item] = False
        elif probabilities[item] >= APD_THRESHOLD_ON:
            detected[item] = True

    return {
        item: {
            "probability": probabilities[item],
            "threshold": APD_THRESHOLD_ON,
            "worn": detected[item],
        }
        for item in APD_ITEMS
    }
