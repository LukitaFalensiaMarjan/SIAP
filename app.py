import csv
import io
import json
import sqlite3
from datetime import date, datetime, timedelta
from math import ceil
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from kiosk_inference import (
    APD_SCAN_FRAME_COUNT,
    FACE_CROP_MODES,
    FACE_SCAN_FRAME_COUNT,
    MODEL_STEMS,
    decode_frame,
    infer_apd,
    infer_face,
    infer_face_sequence,
    infer_single_frame_apd,
    warmup_models,
)


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DB_PATH = ROOT / "siap.db"

app = Flask(__name__)
app.secret_key = "siap-development-secret-change-before-deployment"

DEFAULT_APD_RULES = {
    "Manufaktur": {"helm": 1, "baju": 1, "jeans": 1, "sepatu": 1},
    "Foundry": {"helm": 1, "baju": 1, "jeans": 1, "sepatu": 1},
    "Automation": {"helm": 0, "baju": 1, "jeans": 1, "sepatu": 1},
    "Design": {"helm": 0, "baju": 1, "jeans": 1, "sepatu": 1},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apd_rule(conn, lab):
    row = conn.execute(
        """
        SELECT lab, wajib_helm, wajib_baju, wajib_jeans, wajib_sepatu, aktif
        FROM aturan_apd WHERE lab = ?
        """,
        (lab,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["wajib"] = [
        item
        for item, field in (
            ("helm", "wajib_helm"),
            ("baju", "wajib_baju"),
            ("jeans", "wajib_jeans"),
            ("sepatu", "wajib_sepatu"),
        )
        if result[field]
    ]
    return result


def attendance_status(values, required):
    for item in required:
        value = values.get(item)
        if item == "jeans" and value is None:
            return "menunggu_validasi"
        if value not in (True, 1):
            return "kurang"
    return "lengkap"


def attendance_tardiness(session_date, session_start, attendance_time):
    start_text = session_start.strip().replace(".", ":")
    if len(start_text) == 5:
        start_text += ":00"
    scheduled = datetime.fromisoformat(f"{session_date}T{start_text}")
    arrived = datetime.fromisoformat(attendance_time.replace(" ", "T"))
    if arrived.tzinfo is not None:
        arrived = arrived.astimezone().replace(tzinfo=None)
    if arrived.date() != scheduled.date():
        return None, None
    difference = (arrived - scheduled).total_seconds()
    late_minutes = 0 if difference <= 0 else ceil(difference / 60)
    return late_minutes, late_minutes * 5


def apd_followup_state(attendance, required):
    missing = [
        item for item in required
        if attendance[item] is not None and attendance[item] not in (True, 1)
    ]
    unresolved = [item for item in required if attendance[item] is None]
    all_missing = bool(required) and all(
        attendance[item] in (False, 0) for item in required
    )
    return missing, unresolved, all_missing


def decode_frame_batch(images, frame_count, label, max_total_chars):
    if not isinstance(images, list) or len(images) != frame_count:
        raise ValueError(f"{label} membutuhkan {frame_count} frame")
    if any(not isinstance(image, str) for image in images):
        raise ValueError(f"Format frame {label.lower()} tidak valid")
    if sum(len(image) for image in images) > max_total_chars:
        raise ValueError(f"Ukuran kumpulan frame {label.lower()} terlalu besar")
    return [decode_frame(image) for image in images]


def current_user():
    identifier = session.get("identifier")
    if not identifier:
        return None
    conn = get_db()
    user = conn.execute(
        "SELECT id, identifier, nama, peran FROM pengguna WHERE identifier = ?", (identifier,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def login_required(*roles):
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Autentikasi diperlukan"}), 401)
    if roles and user["peran"].lower() not in {r.lower() for r in roles}:
        return None, (jsonify({"error": "Anda tidak memiliki akses"}), 403)
    return user, None


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    file_path = WEB_DIR / path
    if file_path.is_file():
        return send_from_directory(WEB_DIR, path)
    return jsonify({"error": "Halaman tidak ditemukan"}), 404


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "database": "sqlite", "models": "tflite-local"})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("identifier", "")).strip()
    password = str(data.get("password", ""))
    if not identifier or not password:
        return jsonify({"error": "NIM/NIP dan kata sandi wajib diisi"}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM pengguna WHERE identifier = ?", (identifier,)
    ).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "NIM/NIP atau kata sandi salah"}), 401

    session.clear()
    session["identifier"] = user["identifier"]
    session["peran"] = user["peran"]
    destination = "/mahasiswa/dashboard.html" if user["peran"] == "mahasiswa" else "/admin/dashboard.html"
    return jsonify(
        {
            "user": {
                "identifier": user["identifier"],
                "nama": user["nama"],
                "peran": user["peran"],
            },
            "redirect": destination,
        }
    )


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def me():
    user = current_user()
    return jsonify({"user": user}) if user else (jsonify({"user": None}), 401)


@app.route("/api/sessions", methods=["GET", "POST"])
def sessions_api():
    if request.method == "POST":
        user, error = login_required("dosen", "PLP")
        if error:
            return error
        data, error = validate_session_payload(request.get_json(silent=True))
        if error:
            return error

        conn = get_db()
        cursor = conn.execute(
            """
            INSERT INTO sesi
            (lab, mata_kuliah, kelas, tanggal, jam_mulai, jam_selesai, dosen, ruang, aktif, dibuat_oleh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["lab"], data["mata_kuliah"], data["kelas"], data["tanggal"],
                data["jam_mulai"], data["jam_selesai"], data["dosen"], data["ruang"],
                data["aktif"], user["id"],
            ),
        )
        conn.commit()
        session_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM sesi WHERE id = ?", (session_id,)).fetchone()
        rule = apd_rule(conn, data["lab"])
        conn.close()
        result = dict(row)
        result["wajib"] = rule["wajib"]
        result["aturan_aktif"] = rule["aktif"]
        return jsonify({"session": result}), 201

    _, error = login_required("operator", "dosen", "PLP")
    if error:
        return error

    only_active = request.args.get("aktif") != "0"
    conn = get_db()
    query = "SELECT * FROM sesi"
    params = []
    if only_active:
        query += " WHERE aktif = 1"
    query += " ORDER BY tanggal DESC, jam_mulai DESC"
    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        rule = apd_rule(conn, item["lab"])
        if not rule:
            conn.close()
            return jsonify({"error": f"Aturan APD untuk lab {item['lab']} belum tersedia"}), 409
        item["wajib"] = rule["wajib"]
        item["aturan_aktif"] = rule["aktif"]
        result.append(item)
    conn.close()
    return jsonify({"sessions": result})


def validate_session_payload(data):
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Format data sesi tidak valid"}), 400)
    values = {
        "lab": str(data.get("lab", "")).strip(),
        "mata_kuliah": str(data.get("mata_kuliah", "")).strip(),
        "kelas": str(data.get("kelas", "")).strip(),
        "tanggal": str(data.get("tanggal", "")).strip(),
        "jam_mulai": str(data.get("jam_mulai", "")).strip(),
        "jam_selesai": str(data.get("jam_selesai", "")).strip(),
        "dosen": str(data.get("dosen", "")).strip(),
        "ruang": str(data.get("ruang", "")).strip(),
    }
    if values["lab"] not in DEFAULT_APD_RULES:
        return None, (jsonify({"error": "Lab tidak valid"}), 400)
    if any(not value for value in values.values()):
        return None, (jsonify({"error": "Semua data sesi wajib diisi"}), 400)
    if (
        len(values["mata_kuliah"]) > 150
        or len(values["kelas"]) > 30
        or len(values["dosen"]) > 150
        or len(values["ruang"]) > 100
    ):
        return None, (jsonify({"error": "Panjang data sesi melebihi batas"}), 400)
    try:
        date.fromisoformat(values["tanggal"])
        start = datetime.strptime(values["jam_mulai"], "%H:%M")
        end = datetime.strptime(values["jam_selesai"], "%H:%M")
    except ValueError:
        return None, (jsonify({"error": "Tanggal atau format jam tidak valid"}), 400)
    if end <= start:
        return None, (jsonify({"error": "Jam selesai harus setelah jam mulai"}), 400)

    active = data.get("aktif", 1)
    if isinstance(active, bool):
        values["aktif"] = int(active)
    elif active in (0, 1):
        values["aktif"] = active
    else:
        return None, (jsonify({"error": "Status sesi tidak valid"}), 400)
    return values, None


@app.route("/api/sessions/<int:sesi_id>", methods=["PUT", "DELETE"])
def session_detail(sesi_id):
    _, error = login_required("dosen", "PLP")
    if error:
        return error

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM sesi WHERE id = ?", (sesi_id,)
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Sesi tidak ditemukan"}), 404

    if request.method == "PUT":
        data, error = validate_session_payload(request.get_json(silent=True))
        if error:
            conn.close()
            return error
        conn.execute(
            """
            UPDATE sesi
            SET lab = ?, mata_kuliah = ?, kelas = ?, tanggal = ?, jam_mulai = ?,
                jam_selesai = ?, dosen = ?, ruang = ?, aktif = ?
            WHERE id = ?
            """,
            (
                data["lab"], data["mata_kuliah"], data["kelas"], data["tanggal"],
                data["jam_mulai"], data["jam_selesai"], data["dosen"], data["ruang"],
                data["aktif"], sesi_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sesi WHERE id = ?", (sesi_id,)).fetchone()
        rule = apd_rule(conn, data["lab"])
        conn.close()
        result = dict(row)
        result["wajib"] = rule["wajib"]
        result["aturan_aktif"] = rule["aktif"]
        return jsonify({"session": result})

    try:
        conn.execute("DELETE FROM sesi WHERE id = ?", (sesi_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify(
            {"error": "Sesi memiliki riwayat absensi dan tidak dapat dihapus"}
        ), 409
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/apd-rules", methods=["GET"])
def apd_rules():
    _, error = login_required("operator", "dosen", "PLP")
    if error:
        return error
    conn = get_db()
    rows = conn.execute("SELECT lab FROM aturan_apd ORDER BY lab").fetchall()
    rules = [apd_rule(conn, row["lab"]) for row in rows]
    conn.close()
    return jsonify({"rules": rules})


@app.route("/api/apd-rules/<lab>", methods=["PUT"])
def update_apd_rule(lab):
    _, error = login_required("operator")
    if error:
        return error
    if lab not in DEFAULT_APD_RULES:
        return jsonify({"error": "Lab tidak dikenal"}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format aturan tidak valid"}), 400
    fields = {
        "helm": "wajib_helm",
        "baju": "wajib_baju",
        "jeans": "wajib_jeans",
        "sepatu": "wajib_sepatu",
        "aktif": "aktif",
    }
    values = {}
    for key, column in fields.items():
        value = data.get(key)
        if isinstance(value, bool):
            values[column] = int(value)
        elif type(value) is int and value in (0, 1):
            values[column] = value
        else:
            return jsonify({"error": f"Nilai aturan {key} tidak valid"}), 400

    conn = get_db()
    conn.execute(
        """
        UPDATE aturan_apd
        SET wajib_helm = ?, wajib_baju = ?, wajib_jeans = ?, wajib_sepatu = ?, aktif = ?
        WHERE lab = ?
        """,
        (
            values["wajib_helm"], values["wajib_baju"], values["wajib_jeans"],
            values["wajib_sepatu"], values["aktif"], lab,
        ),
    )
    conn.commit()
    rule = apd_rule(conn, lab)
    conn.close()
    if not rule:
        return jsonify({"error": "Aturan lab tidak ditemukan"}), 404
    return jsonify({"rule": rule})


@app.route("/api/mahasiswa", methods=["GET", "POST"])
def mahasiswa():
    if request.method == "GET":
        _, error = login_required("dosen", "PLP", "operator")
        if error:
            return error
        conn = get_db()
        rows = conn.execute(
            """
            SELECT m.nim, m.nama, m.kelas,
                   CASE WHEN u.id IS NULL THEN 0 ELSE 1 END AS has_account
            FROM mahasiswa m
            LEFT JOIN pengguna u
              ON u.identifier = m.nim AND lower(u.peran) = 'mahasiswa'
            ORDER BY m.nim
            """
        ).fetchall()
        conn.close()
        return jsonify({"mahasiswa": [dict(row) for row in rows]})

    _, error = login_required("operator")
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format data tidak valid"}), 400
    nim = str(data.get("nim", "")).strip()
    nama = str(data.get("nama", "")).strip()
    kelas = str(data.get("kelas", "")).strip()
    password = data.get("password")
    if not nim or not nama or not kelas:
        return jsonify({"error": "NIM, nama, dan kelas wajib diisi"}), 400
    if len(nim) > 32 or len(nama) > 150 or len(kelas) > 30:
        return jsonify({"error": "Panjang NIM, nama, atau kelas melebihi batas"}), 400
    if (
        not isinstance(password, str)
        or not password.strip()
        or not 8 <= len(password) <= 128
    ):
        return jsonify(
            {"error": "Kata sandi awal harus terdiri dari 8 sampai 128 karakter"}
        ), 400

    conn = get_db()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO mahasiswa (nim, nama, kelas) VALUES (?, ?, ?)",
            (nim, nama, kelas),
        )
        conn.execute(
            """
            INSERT INTO pengguna (identifier, nama, peran, password_hash)
            VALUES (?, ?, 'mahasiswa', ?)
            """,
            (nim, nama, generate_password_hash(password)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT nim, nama, kelas FROM mahasiswa WHERE nim = ?", (nim,)
        ).fetchone()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"error": "NIM sudah terdaftar atau digunakan akun lain"}), 409
    conn.close()
    result = dict(row)
    result["has_account"] = 1
    return jsonify({"mahasiswa": result}), 201


@app.route("/api/mahasiswa/<nim>", methods=["PUT", "DELETE"])
def mahasiswa_detail(nim):
    _, error = login_required("operator")
    if error:
        return error

    conn = get_db()
    existing = conn.execute(
        "SELECT nim FROM mahasiswa WHERE nim = ?", (nim,)
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Mahasiswa tidak ditemukan"}), 404

    if request.method == "PUT":
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            conn.close()
            return jsonify({"error": "Format data tidak valid"}), 400
        nama = str(data.get("nama", "")).strip()
        kelas = str(data.get("kelas", "")).strip()
        password = data.get("password", "")
        if not nama or not kelas:
            conn.close()
            return jsonify({"error": "Nama dan kelas wajib diisi"}), 400
        if len(nama) > 150 or len(kelas) > 30:
            conn.close()
            return jsonify({"error": "Panjang nama atau kelas melebihi batas"}), 400
        if not isinstance(password, str):
            conn.close()
            return jsonify({"error": "Format kata sandi tidak valid"}), 400
        if password and (not password.strip() or not 8 <= len(password) <= 128):
            conn.close()
            return jsonify(
                {"error": "Kata sandi harus terdiri dari 8 sampai 128 karakter"}
            ), 400

        conn.execute("BEGIN")
        conflicting_account = conn.execute(
            "SELECT id FROM pengguna WHERE identifier = ? AND lower(peran) != 'mahasiswa'",
            (nim,),
        ).fetchone()
        if conflicting_account:
            conn.rollback()
            conn.close()
            return jsonify(
                {"error": "NIM sudah digunakan oleh akun dengan peran lain"}
            ), 409
        student_account = conn.execute(
            "SELECT id FROM pengguna WHERE identifier = ? AND lower(peran) = 'mahasiswa'",
            (nim,),
        ).fetchone()
        if not student_account and not password:
            conn.rollback()
            conn.close()
            return jsonify(
                {"error": "Kata sandi awal wajib untuk membuat akun mahasiswa"}
            ), 400

        try:
            conn.execute(
                "UPDATE mahasiswa SET nama = ?, kelas = ? WHERE nim = ?",
                (nama, kelas, nim),
            )
            if password and student_account:
                conn.execute(
                    """
                    UPDATE pengguna SET nama = ?, password_hash = ?
                    WHERE identifier = ? AND lower(peran) = 'mahasiswa'
                    """,
                    (nama, generate_password_hash(password), nim),
                )
            elif password:
                conn.execute(
                    """
                    INSERT INTO pengguna (identifier, nama, peran, password_hash)
                    VALUES (?, ?, 'mahasiswa', ?)
                    """,
                    (nim, nama, generate_password_hash(password)),
                )
            elif student_account:
                conn.execute(
                    """
                    UPDATE pengguna SET nama = ?
                    WHERE identifier = ? AND lower(peran) = 'mahasiswa'
                    """,
                    (nama, nim),
                )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            return jsonify(
                {"error": "Akun mahasiswa gagal dibuat karena NIM sudah digunakan"}
            ), 409
        row = conn.execute(
            "SELECT nim, nama, kelas FROM mahasiswa WHERE nim = ?", (nim,)
        ).fetchone()
        row_data = dict(row)
        row_data["has_account"] = 1
        conn.close()
        return jsonify({"mahasiswa": row_data})

    try:
        conn.execute("DELETE FROM mahasiswa WHERE nim = ?", (nim,))
        conn.execute(
            "DELETE FROM pengguna WHERE identifier = ? AND lower(peran) = 'mahasiswa'",
            (nim,),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify(
            {"error": "Mahasiswa memiliki riwayat absensi dan tidak dapat dihapus"}
        ), 409
    conn.close()
    return jsonify({"ok": True})


def kiosk_student():
    user, error = login_required("mahasiswa")
    if error:
        return None, None, error
    conn = get_db()
    student = conn.execute(
        "SELECT nim, nama, kelas FROM mahasiswa WHERE nim = ?",
        (user["identifier"],),
    ).fetchone()
    conn.close()
    if not student:
        return None, None, (jsonify({"error": "Data mahasiswa tidak ditemukan"}), 404)
    return user, dict(student), None


def kiosk_identity(data):
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Data identitas mahasiswa tidak valid"}), 400)

    nim = str(data.get("nim", "")).strip()
    if not nim:
        return None, (jsonify({"error": "NIM wajib diisi"}), 400)

    conn = get_db()
    row = conn.execute(
        "SELECT nim, nama, kelas FROM mahasiswa WHERE nim = ?",
        (nim,),
    ).fetchone()

    if not row:
        conn.close()
        return None, (jsonify({"error": "Data mahasiswa tidak ditemukan"}), 404)

    student = dict(row)

    # 1. Autentikasi dengan NIM dan Password
    password = data.get("password")
    if password is not None:
        user = conn.execute(
            "SELECT password_hash FROM pengguna WHERE identifier = ?",
            (nim,),
        ).fetchone()
        conn.close()
        if not user or not check_password_hash(user["password_hash"], str(password)):
            return None, (jsonify({"error": "Kata sandi salah"}), 401)
        return student, None

    conn.close()

    # 2. Dukungan data identitas lengkap (nama & kelas)
    if "nama" in data and "kelas" in data:
        normalized_name = " ".join(str(data["nama"]).casefold().split())
        normalized_class = " ".join(str(data["kelas"]).casefold().split())
        if (
            normalized_name != " ".join(student["nama"].casefold().split())
            or normalized_class != " ".join(student["kelas"].casefold().split())
        ):
            return None, (
                jsonify({"error": "Nama atau kelas tidak sesuai dengan NIM yang dimasukkan"}),
                403,
            )
        return student, None

    return None, (jsonify({"error": "Kata sandi atau identitas wajib diisi"}), 400)


def kiosk_session(student, session_id):
    if isinstance(session_id, bool) or not isinstance(session_id, int):
        return None, None, (jsonify({"error": "Sesi praktikum tidak valid"}), 400)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sesi WHERE id = ? AND aktif = 1 AND tanggal = ?",
        (session_id, date.today().isoformat()),
    ).fetchone()
    if not row:
        conn.close()
        return None, None, (jsonify({"error": "Sesi praktikum tidak aktif"}), 404)
    if row["kelas"] != student["kelas"]:
        conn.close()
        return None, None, (jsonify({"error": "Sesi ini bukan untuk kelas Anda"}), 403)
    rule = apd_rule(conn, row["lab"])
    conn.close()
    if not rule or not rule["aktif"]:
        return None, None, (jsonify({"error": "Aturan APD lab ini tidak aktif"}), 409)
    return dict(row), rule, None


@app.route("/api/kiosk/context", methods=["POST"])
def kiosk_context():
    student, error = kiosk_identity(request.get_json(silent=True))
    if error:
        return error

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sesi WHERE aktif = 1 AND kelas = ? AND tanggal = ? "
        "ORDER BY tanggal DESC, jam_mulai DESC",
        (student["kelas"], date.today().isoformat()),
    ).fetchall()
    sessions = []
    for row in rows:
        rule = apd_rule(conn, row["lab"])
        if rule and rule["aktif"]:
            item = dict(row)
            item["wajib"] = rule["wajib"]
            sessions.append(item)
    conn.close()
    return jsonify({"student": student, "sessions": sessions})


@app.route("/api/student/overview")
def student_overview():
    _, student, error = kiosk_student()
    if error:
        return error

    today = date.today().isoformat()
    conn = get_db()
    session_rows = conn.execute(
        "SELECT * FROM sesi WHERE aktif = 1 AND kelas = ? AND tanggal = ? "
        "ORDER BY jam_mulai",
        (student["kelas"], today),
    ).fetchall()
    sessions = []
    for row in session_rows:
        rule = apd_rule(conn, row["lab"])
        if rule and rule["aktif"]:
            item = dict(row)
            item["wajib"] = rule["wajib"]
            sessions.append(item)

    attendance_rows = conn.execute(
        """
        SELECT a.id, a.waktu, a.helm, a.baju, a.jeans, a.sepatu, a.status,
               s.id AS sesi_id, s.tanggal, s.jam_mulai, s.jam_selesai,
               s.mata_kuliah, s.lab, s.ruang
        FROM absensi a
        JOIN sesi s ON s.id = a.sesi_id
        WHERE a.nim = ?
        ORDER BY a.waktu DESC, a.id DESC
        """,
        (student["nim"],),
    ).fetchall()
    attendance = []
    for row in attendance_rows:
        item = dict(row)
        rule = apd_rule(conn, item["lab"])
        item["wajib"] = rule["wajib"] if rule else []
        attendance.append(item)

    summary = {
        "total": len(attendance),
        "lengkap": sum(item["status"] == "lengkap" for item in attendance),
        "kurang": sum(item["status"] == "kurang" for item in attendance),
        "menunggu_validasi": sum(
            item["status"] == "menunggu_validasi" for item in attendance
        ),
    }
    conn.close()
    return jsonify(
        {
            "student": student,
            "sessions_today": sessions,
            "attendance": attendance,
            "summary": summary,
        }
    )


@app.route("/api/kiosk/scan", methods=["POST"])
def kiosk_scan():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format permintaan tidak valid"}), 400
    student, error = kiosk_identity(data)
    if error:
        return error
    phase = data.get("phase")
    if phase not in ("wajah", "apd", "live_apd"):
        return jsonify({"error": "Tahap pemindaian tidak valid"}), 400
    if phase == "wajah":
        crop_mode = data.get("crop_mode", "hog")
        if crop_mode not in FACE_CROP_MODES:
            return jsonify({"error": "Mode deteksi wajah tidak valid"}), 400
        try:
            frame = decode_frame(data.get("image"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            return jsonify({"face": infer_face(frame, student["nama"], crop_mode)})
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            return jsonify({"error": f"Model wajah tidak dapat dijalankan: {exc}"}), 503

    session_row, rule, error = kiosk_session(student, data.get("sesi_id"))
    if error:
        return error

    # Pemindaian Real-Time: Deteksi APD Dinamis + Tetap Mendeteksi Wajah Mahasiswa
    if (phase in ("live_apd", "apd")) and data.get("image"):
        crop_mode = data.get("crop_mode", "hog")
        try:
            frame = decode_frame(data.get("image"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            face_result = infer_face(frame, student["nama"], crop_mode)
            prev_ema = data.get("previous_ema") or {}
            prev_det = data.get("previous_detected") or {}
            apd_result = infer_single_frame_apd(
                frame, set(rule["wajib"]), prev_ema, prev_det
            )
            for item, res in apd_result.items():
                res["wajib"] = item in rule["wajib"]
                res["validasi_manual"] = item == "jeans" and item in rule["wajib"]
            return jsonify(
                {
                    "lab": session_row["lab"],
                    "wajib": rule["wajib"],
                    "face": face_result,
                    "apd": apd_result,
                }
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            return jsonify({"error": f"Model tidak dapat dijalankan: {exc}"}), 503

    try:
        frames = decode_frame_batch(
            data.get("images"), APD_SCAN_FRAME_COUNT, "Pemindaian APD", 12_000_000
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        results = infer_apd(frames, set(rule["wajib"]))
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": f"Model APD tidak dapat dijalankan: {exc}"}), 503
    for item, result in results.items():
        result["wajib"] = item in rule["wajib"]
        result["validasi_manual"] = item == "jeans" and item in rule["wajib"]
    return jsonify(
        {
            "lab": session_row["lab"],
            "wajib": rule["wajib"],
            "apd": results,
        }
    )


@app.route("/api/kiosk/attendance", methods=["POST"])
def kiosk_attendance():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format permintaan tidak valid"}), 400
    student, error = kiosk_identity(data)
    if error:
        return error
    session_row, rule, error = kiosk_session(student, data.get("sesi_id"))
    if error:
        return error
    face_crop_mode = data.get("face_crop_mode", "hog")
    if face_crop_mode not in FACE_CROP_MODES:
        return jsonify({"error": "Mode deteksi wajah tidak valid"}), 400
    try:
        frames = decode_frame_batch(
            data.get("images"), APD_SCAN_FRAME_COUNT, "Pemindaian APD", 12_000_000
        )
        face_frames = decode_frame_batch(
            data.get("face_images"), FACE_SCAN_FRAME_COUNT, "Verifikasi wajah", 6_000_000
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    conn = get_db()
    duplicate = conn.execute(
        "SELECT id FROM absensi WHERE nim = ? AND sesi_id = ?",
        (student["nim"], session_row["id"]),
    ).fetchone()
    conn.close()
    if duplicate:
        return jsonify({"error": "Anda sudah absen pada sesi ini"}), 409

    try:
        face = infer_face_sequence(face_frames, student["nama"], face_crop_mode)
        if not face["detected"]:
            return jsonify({"error": "Wajah belum terdeteksi dengan jelas"}), 409
        if not face["matched"]:
            return jsonify({"error": "Wajah tidak cocok dengan akun mahasiswa ini"}), 403
        apd = infer_apd(frames, set(rule["wajib"]))
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": f"Model tidak dapat dijalankan: {exc}"}), 503

    values = {item: None for item in ("helm", "baju", "jeans", "sepatu")}
    for item in ("helm", "baju", "sepatu"):
        if item in rule["wajib"]:
            values[item] = int(apd[item]["worn"])
    status = attendance_status(values, rule["wajib"])
    confidence = {
        item: apd[item]["probability"] for item in ("helm", "baju", "jeans", "sepatu")
    }

    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO absensi
            (nim, sesi_id, waktu, helm, baju, jeans, sepatu, status, confidence, foto_path, catatan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                student["nim"],
                session_row["id"],
                datetime.now().isoformat(timespec="seconds"),
                values["helm"],
                values["baju"],
                None,
                values["sepatu"],
                status,
                json.dumps(confidence),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Anda sudah absen pada sesi ini"}), 409
    row = conn.execute(
        """
        SELECT a.*, m.nama, m.kelas, s.lab, s.mata_kuliah
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
        WHERE a.id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    conn.close()
    return jsonify(
        {
            "attendance": dict(row),
            "face": face,
            "apd": apd,
            "wajib": rule["wajib"],
        }
    ), 201


@app.route("/api/absensi", methods=["GET", "POST"])
def attendance_api():
    if request.method == "POST":
        _, error = login_required("operator", "dosen", "PLP")
        if error:
            return error
        data = request.get_json(silent=True) or {}
        nim = str(data.get("nim", "")).strip()
        sesi_id = data.get("sesi_id")
        if not nim or not sesi_id:
            return jsonify({"error": "NIM dan sesi wajib diisi"}), 400

        conn = get_db()
        mahasiswa = conn.execute(
            "SELECT nim, nama, kelas FROM mahasiswa WHERE nim = ?", (nim,)
        ).fetchone()
        sesi_row = conn.execute("SELECT * FROM sesi WHERE id = ?", (sesi_id,)).fetchone()
        if not mahasiswa:
            conn.close()
            return jsonify({"error": "NIM tidak terdaftar"}), 404
        if not sesi_row:
            conn.close()
            return jsonify({"error": "Sesi tidak ditemukan"}), 404
        if not sesi_row["aktif"]:
            conn.close()
            return jsonify({"error": "Sesi praktikum tidak aktif"}), 409
        rule = apd_rule(conn, sesi_row["lab"])
        if not rule or not rule["aktif"]:
            conn.close()
            return jsonify({"error": "Aturan APD lab ini tidak aktif"}), 409
        existing = conn.execute(
            "SELECT id FROM absensi WHERE nim = ? AND sesi_id = ?", (nim, sesi_id)
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "Mahasiswa sudah absen pada sesi ini"}), 409

        wajib = rule["wajib"]
        confidence = data.get("confidence", {})
        hasil_apd = {}
        for item in ("helm", "baju", "jeans", "sepatu"):
            if item not in wajib:
                hasil_apd[item] = None
                continue
            value = data.get(item)
            if value is None and item == "jeans":
                hasil_apd[item] = None
            elif isinstance(value, bool):
                hasil_apd[item] = int(value)
            elif type(value) is int and value in (0, 1):
                hasil_apd[item] = value
            else:
                conn.close()
                return jsonify({"error": f"Hasil pemeriksaan {item} tidak valid"}), 400
        status = attendance_status(hasil_apd, wajib)
        cursor = conn.execute(
            """
            INSERT INTO absensi
            (nim, sesi_id, waktu, helm, baju, jeans, sepatu, status, confidence, foto_path, catatan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nim,
                sesi_id,
                datetime.now().isoformat(timespec="seconds"),
                hasil_apd["helm"],
                hasil_apd["baju"],
                hasil_apd["jeans"],
                hasil_apd["sepatu"],
                status,
                json.dumps(confidence),
                data.get("foto_path"),
                data.get("catatan"),
            ),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT a.*, m.nama, m.kelas, s.lab, s.mata_kuliah
            FROM absensi a
            JOIN mahasiswa m ON m.nim = a.nim
            JOIN sesi s ON s.id = a.sesi_id
            WHERE a.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        conn.close()
        result = dict(row)
        result["wajib"] = wajib
        return jsonify({"attendance": result}), 201

    _, error = login_required("operator", "dosen", "PLP")
    if error:
        return error

    sesi_id = request.args.get("sesi_id")
    conn = get_db()
    query = """
        SELECT a.*, m.nama, m.kelas, s.lab, s.mata_kuliah
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
    """
    params = []
    if sesi_id:
        query += " WHERE a.sesi_id = ?"
        params.append(sesi_id)
    query += " ORDER BY a.waktu DESC"
    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        rule = apd_rule(conn, item["lab"])
        if not rule:
            conn.close()
            return jsonify({"error": f"Aturan APD untuk lab {item['lab']} belum tersedia"}), 409
        item["wajib"] = rule["wajib"]
        result.append(item)
    conn.close()
    return jsonify({"attendance": result})


def followup_attendance_row(conn, attendance_id):
    row = conn.execute(
        """
        SELECT a.*, m.nama, m.kelas, s.tanggal, s.jam_mulai, s.lab,
               s.mata_kuliah, s.ruang
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
        WHERE a.id = ?
        """,
        (attendance_id,),
    ).fetchone()
    return dict(row) if row else None


def active_academic_period(conn):
    row = conn.execute(
        "SELECT * FROM periode_akademik WHERE aktif = 1"
    ).fetchone()
    return dict(row) if row else None


@app.route("/api/follow-up", methods=["GET"])
def followup_api():
    user, error = login_required("operator", "dosen", "PLP")
    if error:
        return error

    conn = get_db()
    period = active_academic_period(conn)
    attendance_query = """
        SELECT a.*, m.nama, m.kelas, s.tanggal, s.jam_mulai, s.lab,
               s.mata_kuliah, s.ruang
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
    """
    attendance_params = []
    if period:
        attendance_query += " WHERE s.tanggal BETWEEN ? AND ?"
        attendance_params.extend([period["tanggal_mulai"], period["tanggal_selesai"]])
    attendance_query += " ORDER BY s.tanggal DESC, s.jam_mulai DESC, a.waktu DESC"
    rows = conn.execute(attendance_query, attendance_params).fetchall()
    if period:
        case_rows = conn.execute(
            """
            SELECT k.*, p.nama AS periode_nama
            FROM kasus_tindak_lanjut k
            JOIN periode_akademik p ON p.id = k.periode_id
            WHERE k.periode_id = ?
            """,
            (period["id"],),
        ).fetchall()
    else:
        case_rows = conn.execute(
            """
            SELECT k.*, p.nama AS periode_nama
            FROM kasus_tindak_lanjut k
            JOIN periode_akademik p ON p.id = k.periode_id
            """
        ).fetchall()
    cases = {row["absensi_id"]: dict(row) for row in case_rows}

    attendance = []
    try:
        for row in rows:
            item = dict(row)
            rule = apd_rule(conn, item["lab"])
            if not rule:
                conn.close()
                return jsonify({"error": f"Aturan APD untuk lab {item['lab']} belum tersedia"}), 409
            missing, unresolved, all_missing = apd_followup_state(item, rule["wajib"])
            late_minutes, compensation_minutes = attendance_tardiness(
                item["tanggal"], item["jam_mulai"], item["waktu"]
            )
            case = cases.get(item["id"])
            if case:
                case["atribut_tidak_sesuai"] = json.loads(case["atribut_tidak_sesuai"])
            item.update(
                {
                    "periode_nama": period["nama"] if period else (case["periode_nama"] if case else None),
                    "wajib": rule["wajib"],
                    "atribut_tidak_sesuai": missing,
                    "atribut_belum_diperiksa": unresolved,
                    "semua_atribut_tidak_sesuai": all_missing,
                    "terlambat_menit": late_minutes,
                    "kompensasi_menit": compensation_minutes,
                    "tanggal_absensi_cocok": late_minutes is not None,
                    "kasus": case,
                }
            )
            attendance.append(item)
    except ValueError as exc:
        conn.close()
        return jsonify({"error": f"Waktu absensi tidak dapat dihitung: {exc}"}), 409

    conn.close()
    return jsonify(
        {
            "period": period,
            "attendance": attendance,
            "can_manage": user["peran"].lower() in {"dosen", "plp"},
        }
    )


@app.route("/api/follow-up/periods", methods=["POST"])
def create_followup_period():
    user, error = login_required("dosen", "PLP")
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format data tidak valid"}), 400
    name = str(data.get("nama", "")).strip()
    start_text = str(data.get("tanggal_mulai", "")).strip()
    end_text = str(data.get("tanggal_selesai", "")).strip()
    if not name or len(name) > 100:
        return jsonify({"error": "Nama semester wajib diisi (maksimal 100 karakter)"}), 400
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError:
        return jsonify({"error": "Tanggal semester harus menggunakan format YYYY-MM-DD"}), 400
    if start > end:
        return jsonify({"error": "Tanggal mulai semester tidak boleh melewati tanggal selesai"}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    overlap = conn.execute(
        """
        SELECT id FROM periode_akademik
        WHERE tanggal_mulai <= ? AND tanggal_selesai >= ?
        LIMIT 1
        """,
        (end_text, start_text),
    ).fetchone()
    if overlap:
        conn.close()
        return jsonify({"error": "Rentang semester bertumpang tindih dengan periode yang sudah tersimpan"}), 409

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE periode_akademik SET aktif = 0 WHERE aktif = 1")
    cursor = conn.execute(
        """
        INSERT INTO periode_akademik
        (nama, tanggal_mulai, tanggal_selesai, aktif, dibuat_oleh, dibuat_pada)
        VALUES (?, ?, ?, 1, ?, ?)
        """,
        (name, start_text, end_text, user["id"], now),
    )
    period_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO audit_log (pengguna_id, aksi, detail, waktu) VALUES (?, ?, ?, ?)",
        (user["id"], "membuat_periode_akademik", json.dumps({"periode_id": period_id, "nama": name}), now),
    )
    conn.commit()
    period = dict(conn.execute(
        "SELECT * FROM periode_akademik WHERE id = ?", (period_id,)
    ).fetchone())
    conn.close()
    return jsonify({"period": period}), 201


@app.route("/api/follow-up/<int:attendance_id>/confirm", methods=["POST"])
def confirm_followup_violation(attendance_id):
    user, error = login_required("dosen", "PLP")
    if error:
        return error

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    period = active_academic_period(conn)
    item = followup_attendance_row(conn, attendance_id)
    if not item:
        conn.close()
        return jsonify({"error": "Data absensi tidak ditemukan"}), 404
    if not period or not period["tanggal_mulai"] <= item["tanggal"] <= period["tanggal_selesai"]:
        conn.close()
        return jsonify({"error": "Absensi tidak termasuk semester aktif"}), 409
    rule = apd_rule(conn, item["lab"])
    if not rule:
        conn.close()
        return jsonify({"error": f"Aturan APD untuk lab {item['lab']} belum tersedia"}), 409
    missing, unresolved, all_missing = apd_followup_state(item, rule["wajib"])
    if unresolved:
        conn.close()
        return jsonify({"error": "Selesaikan pemeriksaan APD wajib sebelum mengonfirmasi pelanggaran"}), 409
    late_minutes, compensation_minutes = attendance_tardiness(
        item["tanggal"], item["jam_mulai"], item["waktu"]
    )
    late_violation = late_minutes is not None and late_minutes > 120
    if not missing and not late_violation:
        conn.close()
        return jsonify({"error": "Absensi ini tidak memiliki pelanggaran APD atau keterlambatan lebih dari 2 jam"}), 409
    existing = conn.execute(
        "SELECT id FROM kasus_tindak_lanjut WHERE absensi_id = ?", (attendance_id,)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Tindak lanjut untuk absensi ini sudah diproses"}), 409

    previous = conn.execute(
        """
        SELECT COUNT(*) AS jumlah, MAX(sp_level) AS level_tertinggi
        FROM kasus_tindak_lanjut k
        JOIN absensi a ON a.id = k.absensi_id
        WHERE k.periode_id = ? AND a.nim = ?
          AND k.status IN ('draf', 'diterbitkan')
        """,
        (period["id"], item["nim"]),
    ).fetchone()
    violation_number = previous["jumlah"] + 1
    if previous["level_tertinggi"] and previous["level_tertinggi"] >= 3:
        sp_level = 3
    elif violation_number > 3 and late_minutes is not None and late_minutes > 0 and all_missing:
        sp_level = 3
    elif violation_number > 3:
        sp_level = 2
    else:
        sp_level = 1

    now = datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO kasus_tindak_lanjut
        (absensi_id, periode_id, status, sp_level, urutan_pelanggaran, terlambat_menit,
         kompensasi_menit, tanggal_absensi_cocok, atribut_tidak_sesuai,
         dikonfirmasi_oleh, dikonfirmasi_pada)
        VALUES (?, ?, 'draf', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attendance_id,
            period["id"],
            sp_level,
            violation_number,
            late_minutes if late_minutes is not None else 0,
            compensation_minutes if compensation_minutes is not None else 0,
            int(late_minutes is not None),
            json.dumps(missing),
            user["id"],
            now,
        ),
    )
    case_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO audit_log (pengguna_id, aksi, detail, waktu) VALUES (?, ?, ?, ?)",
        (
            user["id"],
            "mengonfirmasi_pelanggaran_apd",
            json.dumps({"kasus_id": case_id, "absensi_id": attendance_id, "sp_level": sp_level}),
            now,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"case": {"id": case_id, "status": "draf", "sp_level": sp_level}})


@app.route("/api/follow-up/<int:attendance_id>/dismiss", methods=["POST"])
def dismiss_followup_violation(attendance_id):
    user, error = login_required("dosen", "PLP")
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format data tidak valid"}), 400
    note = str(data.get("catatan", "")).strip()
    if not note:
        return jsonify({"error": "Alasan penolakan wajib diisi"}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    period = active_academic_period(conn)
    item = followup_attendance_row(conn, attendance_id)
    if not item:
        conn.close()
        return jsonify({"error": "Data absensi tidak ditemukan"}), 404
    if not period or not period["tanggal_mulai"] <= item["tanggal"] <= period["tanggal_selesai"]:
        conn.close()
        return jsonify({"error": "Absensi tidak termasuk semester aktif"}), 409
    rule = apd_rule(conn, item["lab"])
    if not rule:
        conn.close()
        return jsonify({"error": f"Aturan APD untuk lab {item['lab']} belum tersedia"}), 409
    missing, unresolved, _ = apd_followup_state(item, rule["wajib"])
    late_minutes, compensation_minutes = attendance_tardiness(
        item["tanggal"], item["jam_mulai"], item["waktu"]
    )
    late_violation = late_minutes is not None and late_minutes > 120
    if unresolved or (not missing and not late_violation):
        conn.close()
        return jsonify({"error": "Absensi ini belum memiliki pelanggaran yang dapat ditolak"}), 409
    existing = conn.execute(
        "SELECT id FROM kasus_tindak_lanjut WHERE absensi_id = ?", (attendance_id,)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Tindak lanjut untuk absensi ini sudah diproses"}), 409

    now = datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        """
        INSERT INTO kasus_tindak_lanjut
        (absensi_id, periode_id, status, sp_level, urutan_pelanggaran, terlambat_menit,
         kompensasi_menit, tanggal_absensi_cocok, atribut_tidak_sesuai, catatan,
         dikonfirmasi_oleh, dikonfirmasi_pada)
        VALUES (?, ?, 'ditolak', NULL, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attendance_id,
            period["id"],
            late_minutes if late_minutes is not None else 0,
            compensation_minutes if compensation_minutes is not None else 0,
            int(late_minutes is not None),
            json.dumps(missing),
            note,
            user["id"],
            now,
        ),
    )
    case_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO audit_log (pengguna_id, aksi, detail, waktu) VALUES (?, ?, ?, ?)",
        (
            user["id"],
            "menolak_pelanggaran_apd",
            json.dumps({"kasus_id": case_id, "absensi_id": attendance_id, "catatan": note}),
            now,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"case": {"id": case_id, "status": "ditolak"}})


@app.route("/api/follow-up/cases/<int:case_id>/issue", methods=["POST"])
def issue_followup_warning(case_id):
    user, error = login_required("dosen", "PLP")
    if error:
        return error
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    case = conn.execute(
        "SELECT id, status FROM kasus_tindak_lanjut WHERE id = ?", (case_id,)
    ).fetchone()
    if not case:
        conn.close()
        return jsonify({"error": "Draf surat peringatan tidak ditemukan"}), 404
    if case["status"] != "draf":
        conn.close()
        return jsonify({"error": "Hanya draf yang dapat diterbitkan"}), 409
    now = datetime.now().isoformat(timespec="seconds")
    updated = conn.execute(
        """
        UPDATE kasus_tindak_lanjut
        SET status = 'diterbitkan', diterbitkan_oleh = ?, diterbitkan_pada = ?
        WHERE id = ? AND status = 'draf'
        """,
        (user["id"], now, case_id),
    )
    if updated.rowcount != 1:
        conn.close()
        return jsonify({"error": "Draf telah diproses oleh petugas lain"}), 409
    conn.execute(
        "INSERT INTO audit_log (pengguna_id, aksi, detail, waktu) VALUES (?, ?, ?, ?)",
        (user["id"], "menerbitkan_surat_peringatan", json.dumps({"kasus_id": case_id}), now),
    )
    conn.commit()
    conn.close()
    return jsonify({"case": {"id": case_id, "status": "diterbitkan"}})


@app.route("/api/absensi/<int:attendance_id>/jeans", methods=["PATCH"])
def update_jeans(attendance_id):
    user, error = login_required("PLP")
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Format data tidak valid"}), 400
    jeans = data.get("jeans")
    if jeans not in (True, False, 1, 0):
        return jsonify({"error": "Nilai jeans harus sesuai atau tidak sesuai"}), 400

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """
        SELECT a.*, s.lab FROM absensi a
        JOIN sesi s ON s.id = a.sesi_id
        WHERE a.id = ?
        """,
        (attendance_id,),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Data absensi tidak ditemukan"}), 404
    rule = apd_rule(conn, row["lab"])
    if not rule or "jeans" not in rule["wajib"]:
        conn.close()
        return jsonify({"error": "Pemeriksaan jeans tidak diwajibkan untuk lab ini"}), 409
    existing_case = conn.execute(
        "SELECT id FROM kasus_tindak_lanjut WHERE absensi_id = ?", (attendance_id,)
    ).fetchone()
    if existing_case:
        conn.close()
        return jsonify({"error": "Hasil pemeriksaan terkunci karena tindak lanjut sudah diproses"}), 409
    result = dict(row)
    result["jeans"] = int(bool(jeans))
    result["status"] = attendance_status(result, rule["wajib"])
    conn.execute(
        "UPDATE absensi SET jeans = ?, status = ? WHERE id = ?",
        (result["jeans"], result["status"], attendance_id),
    )
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO audit_log (pengguna_id, aksi, detail, waktu) VALUES (?, ?, ?, ?)",
        (
            user["id"],
            "verifikasi_jeans_manual",
            json.dumps({"absensi_id": attendance_id, "sesuai": bool(result["jeans"])}),
            now,
        ),
    )
    conn.commit()
    conn.close()
    result["wajib"] = rule["wajib"]
    return jsonify({"attendance": result})


def attendance_report_rows():
    _, error = login_required("dosen", "PLP")
    if error:
        return None, error

    date_from = request.args.get("tanggal_mulai", "").strip()
    date_to = request.args.get("tanggal_selesai", "").strip()
    kelas = request.args.get("kelas", "").strip()
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()
    for label, value in (("tanggal mulai", date_from), ("tanggal selesai", date_to)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                return None, (jsonify({"error": f"Format {label} tidak valid"}), 400)
    if date_from and date_to and date_from > date_to:
        return None, (jsonify({"error": "Tanggal mulai tidak boleh setelah tanggal selesai"}), 400)
    if status and status not in {"lengkap", "kurang", "menunggu_validasi"}:
        return None, (jsonify({"error": "Filter status tidak valid"}), 400)

    conditions = []
    params = []
    if date_from:
        conditions.append("substr(a.waktu, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("substr(a.waktu, 1, 10) <= ?")
        params.append(date_to)
    if kelas:
        conditions.append("m.kelas = ?")
        params.append(kelas)
    if status:
        conditions.append("a.status = ?")
        params.append(status)
    if search:
        conditions.append(
            "(a.nim LIKE ? OR m.nama LIKE ? OR m.kelas LIKE ? "
            "OR s.mata_kuliah LIKE ? OR s.lab LIKE ?)"
        )
        params.extend([f"%{search}%"] * 5)

    query = """
        SELECT a.id, a.waktu, a.nim, m.nama, m.kelas,
               s.mata_kuliah, s.lab, a.helm, a.baju, a.jeans, a.sepatu,
               a.status, a.confidence, a.foto_path, a.catatan
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY a.waktu DESC, a.id DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        rule = apd_rule(conn, item["lab"])
        item["wajib"] = rule["wajib"] if rule else []
        item["aturan_aktif"] = rule["aktif"] if rule else 0
        result.append(item)
    conn.close()
    return result, None


@app.route("/api/reports/attendance")
def attendance_report():
    rows, error = attendance_report_rows()
    if error:
        return error
    return jsonify(
        {
            "attendance": rows,
            "summary": {
                "total": len(rows),
                "lengkap": sum(row["status"] == "lengkap" for row in rows),
                "kurang": sum(row["status"] == "kurang" for row in rows),
                "menunggu_validasi": sum(
                    row["status"] == "menunggu_validasi" for row in rows
                ),
            },
        }
    )


@app.route("/api/reports/attendance.csv")
def export_attendance_report():
    rows, error = attendance_report_rows()
    if error:
        return error

    def csv_value(value):
        if value is None:
            return ""
        text = str(value)
        if text.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text
        return text

    def apd_value(value, item, required):
        if value is None:
            if item == "jeans":
                return "Belum diverifikasi manual"
            return "Belum diperiksa" if required else "Tidak wajib"
        return "Sesuai" if value else "Tidak sesuai"

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Waktu",
            "NIM",
            "Nama Mahasiswa",
            "Kelas",
            "Mata Kuliah",
            "Lab",
            "Helm",
            "Baju Praktik",
            "Jeans (manual)",
            "Sepatu Safety",
            "Status Pemeriksaan",
            "Confidence",
            "Catatan",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                csv_value(row["waktu"]),
                csv_value(row["nim"]),
                csv_value(row["nama"]),
                csv_value(row["kelas"]),
                csv_value(row["mata_kuliah"]),
                csv_value(row["lab"]),
                apd_value(row["helm"], "helm", "helm" in row["wajib"]),
                apd_value(row["baju"], "baju", "baju" in row["wajib"]),
                apd_value(row["jeans"], "jeans", "jeans" in row["wajib"]),
                apd_value(row["sepatu"], "sepatu", "sepatu" in row["wajib"]),
                {
                    "lengkap": "Lengkap",
                    "kurang": "Tidak lengkap",
                    "menunggu_validasi": "Menunggu validasi jeans",
                }[row["status"]],
                csv_value(row["confidence"]),
                csv_value(row["catatan"]),
            ]
        )

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=laporan-absensi-{date.today().isoformat()}.csv"
    )
    return response


@app.route("/api/dashboard/summary")
def dashboard_summary():
    _, error = login_required("operator", "dosen", "PLP")
    if error:
        return error

    period = request.args.get("period", "all")
    today = date.today()
    if period == "today":
        date_from = date_to = today.isoformat()
    elif period == "week":
        date_from = (today - timedelta(days=today.weekday())).isoformat()
        date_to = today.isoformat()
    elif period == "month":
        date_from = today.replace(day=1).isoformat()
        date_to = today.isoformat()
    elif period == "all":
        date_from = date_to = None
    else:
        return jsonify({"error": "Rentang dashboard tidak valid"}), 400

    conn = get_db()
    date_filter = ""
    date_params = []
    if date_from:
        date_filter = " WHERE substr(waktu, 1, 10) BETWEEN ? AND ?"
        date_params = [date_from, date_to]
    session_filter = ""
    session_params = []
    if date_from:
        session_filter = " WHERE tanggal BETWEEN ? AND ?"
        session_params = [date_from, date_to]

    total_sesi = conn.execute(
        "SELECT COUNT(*) FROM sesi" + session_filter, session_params
    ).fetchone()[0]
    active_sessions_query = "SELECT COUNT(*) FROM sesi WHERE aktif = 1"
    active_session_params = []
    if date_from:
        active_sessions_query += " AND tanggal BETWEEN ? AND ?"
        active_session_params = [date_from, date_to]
    aktif = conn.execute(
        active_sessions_query, active_session_params
    ).fetchone()[0]
    lengkap = conn.execute(
        "SELECT COUNT(*) FROM absensi"
        + date_filter
        + (" AND status = 'lengkap'" if date_filter else " WHERE status = 'lengkap'"),
        date_params,
    ).fetchone()[0]
    kurang = conn.execute(
        "SELECT COUNT(*) FROM absensi"
        + date_filter
        + (" AND status = 'kurang'" if date_filter else " WHERE status = 'kurang'"),
        date_params,
    ).fetchone()[0]
    menunggu = conn.execute(
        "SELECT COUNT(*) FROM absensi"
        + date_filter
        + (" AND status = 'menunggu_validasi'"
           if date_filter else " WHERE status = 'menunggu_validasi'"),
        date_params,
    ).fetchone()[0]
    total_absensi = conn.execute(
        "SELECT COUNT(*) FROM absensi" + date_filter, date_params
    ).fetchone()[0]
    mahasiswa = conn.execute("SELECT COUNT(*) FROM mahasiswa").fetchone()[0]

    recent_rows = conn.execute(
        """
        SELECT a.id, a.waktu, a.nim, m.nama, m.kelas,
               s.mata_kuliah, a.status
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
        """
        + (" WHERE substr(a.waktu, 1, 10) BETWEEN ? AND ?" if date_from else "")
        + " ORDER BY a.waktu DESC, a.id DESC LIMIT 8",
        date_params,
    ).fetchall()
    queue_rows = conn.execute(
        """
        SELECT a.id, a.waktu, a.nim, m.nama, m.kelas,
               s.mata_kuliah
        FROM absensi a
        JOIN mahasiswa m ON m.nim = a.nim
        JOIN sesi s ON s.id = a.sesi_id
        WHERE a.status = 'menunggu_validasi'
        """
        + (" AND substr(a.waktu, 1, 10) BETWEEN ? AND ?" if date_from else "")
        + " ORDER BY a.waktu DESC, a.id DESC LIMIT 5",
        date_params,
    ).fetchall()
    sessions_today = conn.execute(
        """
        SELECT id, mata_kuliah, kelas, jam_mulai, jam_selesai, aktif
        FROM sesi WHERE tanggal = ? ORDER BY jam_mulai
        """,
        (today.isoformat(),),
    ).fetchall()
    trend_rows = conn.execute(
        """
        SELECT substr(waktu, 1, 10) AS tanggal,
               SUM(CASE WHEN status = 'lengkap' THEN 1 ELSE 0 END) AS lengkap,
               SUM(CASE WHEN status = 'kurang' THEN 1 ELSE 0 END) AS kurang,
               SUM(CASE WHEN status = 'menunggu_validasi' THEN 1 ELSE 0 END) AS menunggu
        FROM absensi
        WHERE substr(waktu, 1, 10) BETWEEN ? AND ?
        GROUP BY substr(waktu, 1, 10)
        """,
        [
            (today - timedelta(days=5)).isoformat(),
            today.isoformat(),
        ],
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "period": period,
            "total_sesi": total_sesi,
            "sesi_aktif": aktif,
            "mahasiswa": mahasiswa,
            "lengkap": lengkap,
            "kurang": kurang,
            "menunggu_validasi": menunggu,
            "total_absensi": total_absensi,
            "recent": [dict(row) for row in recent_rows],
            "validation_queue": [dict(row) for row in queue_rows],
            "sessions_today": [dict(row) for row in sessions_today],
            "trend": [dict(row) for row in trend_rows],
        }
    )


@app.route("/api/models/status")
def models_status():
    items = {}
    for item, stem in MODEL_STEMS.items():
        json_path = ROOT / "models" / f"{stem}.json"
        tflite_path = ROOT / "models" / f"{stem}.tflite"
        info = (
            json.loads(json_path.read_text(encoding="utf-8"))
            if json_path.is_file()
            else {}
        )
        items[item] = {
            "ready": tflite_path.is_file() and bool(info),
            "threshold": info.get("threshold"),
            "tflite": tflite_path.is_file(),
        }
    return jsonify({"mode": "local-tflite", "items": items})


def init_db():
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mahasiswa "
        "(nim TEXT PRIMARY KEY, nama TEXT NOT NULL, kelas TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pengguna "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, identifier TEXT UNIQUE NOT NULL, "
        "nama TEXT NOT NULL, peran TEXT NOT NULL, password_hash TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sesi "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, lab TEXT NOT NULL, mata_kuliah TEXT NOT NULL, "
        "kelas TEXT NOT NULL, tanggal TEXT NOT NULL, jam_mulai TEXT NOT NULL, "
        "jam_selesai TEXT NOT NULL, aktif INTEGER NOT NULL DEFAULT 1, "
        "dibuat_oleh INTEGER NOT NULL, FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id))"
    )
    session_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(sesi)").fetchall()
    }
    if "dosen" not in session_columns:
        conn.execute("ALTER TABLE sesi ADD COLUMN dosen TEXT NOT NULL DEFAULT ''")
    if "ruang" not in session_columns:
        conn.execute("ALTER TABLE sesi ADD COLUMN ruang TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        UPDATE sesi SET dosen = COALESCE(
            NULLIF(dosen, ''),
            (SELECT nama FROM pengguna WHERE pengguna.id = sesi.dibuat_oleh),
            'Belum ditentukan'
        ) WHERE dosen = ''
        """
    )
    conn.execute(
        """
        UPDATE sesi
        SET ruang = CASE lab
            WHEN 'Manufaktur' THEN 'Lab. CNC'
            WHEN 'Foundry' THEN 'Lab. Foundry'
            WHEN 'Automation' THEN 'Lab. Automation'
            WHEN 'Design' THEN 'Lab. Design'
            ELSE 'Lab. ' || lab
        END
        WHERE ruang = ''
        """
    )
    conn.execute(
        "UPDATE sesi SET jam_mulai = replace(jam_mulai, '.', ':'), "
        "jam_selesai = replace(jam_selesai, '.', ':') "
        "WHERE instr(jam_mulai, '.') > 0 OR instr(jam_selesai, '.') > 0"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS absensi "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, nim TEXT NOT NULL, sesi_id INTEGER NOT NULL, "
        "waktu TEXT NOT NULL, helm INTEGER, baju INTEGER, jeans INTEGER, sepatu INTEGER, "
        "status TEXT NOT NULL, confidence TEXT, foto_path TEXT, catatan TEXT, "
        "UNIQUE(nim, sesi_id), FOREIGN KEY (nim) REFERENCES mahasiswa(nim), "
        "FOREIGN KEY (sesi_id) REFERENCES sesi(id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_log "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, pengguna_id INTEGER, aksi TEXT NOT NULL, "
        "detail TEXT, waktu TEXT NOT NULL, FOREIGN KEY (pengguna_id) REFERENCES pengguna(id))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS periode_akademik "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL, "
        "tanggal_mulai TEXT NOT NULL, tanggal_selesai TEXT NOT NULL, "
        "aktif INTEGER NOT NULL DEFAULT 0, dibuat_oleh INTEGER NOT NULL, "
        "dibuat_pada TEXT NOT NULL, "
        "FOREIGN KEY (dibuat_oleh) REFERENCES pengguna(id), "
        "CHECK (tanggal_mulai <= tanggal_selesai))"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_periode_akademik_satu_aktif "
        "ON periode_akademik (aktif) WHERE aktif = 1"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kasus_tindak_lanjut "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, absensi_id INTEGER NOT NULL UNIQUE, "
        "periode_id INTEGER NOT NULL, status TEXT NOT NULL, sp_level INTEGER, "
        "urutan_pelanggaran INTEGER NOT NULL, "
        "terlambat_menit INTEGER NOT NULL, kompensasi_menit INTEGER NOT NULL, "
        "tanggal_absensi_cocok INTEGER NOT NULL DEFAULT 1, "
        "atribut_tidak_sesuai TEXT NOT NULL, catatan TEXT, "
        "dikonfirmasi_oleh INTEGER NOT NULL, dikonfirmasi_pada TEXT NOT NULL, "
        "diterbitkan_oleh INTEGER, diterbitkan_pada TEXT, "
        "FOREIGN KEY (absensi_id) REFERENCES absensi(id), "
        "FOREIGN KEY (periode_id) REFERENCES periode_akademik(id), "
        "FOREIGN KEY (dikonfirmasi_oleh) REFERENCES pengguna(id), "
        "FOREIGN KEY (diterbitkan_oleh) REFERENCES pengguna(id), "
        "CHECK (status IN ('draf', 'diterbitkan', 'ditolak')), "
        "CHECK (sp_level IS NULL OR sp_level BETWEEN 1 AND 3))"
    )
    followup_columns = {
        row["name"] for row in conn.execute(
            "PRAGMA table_info(kasus_tindak_lanjut)"
        ).fetchall()
    }
    if "urutan_pelanggaran" not in followup_columns:
        conn.execute(
            "ALTER TABLE kasus_tindak_lanjut "
            "ADD COLUMN urutan_pelanggaran INTEGER NOT NULL DEFAULT 0"
        )
    if "tanggal_absensi_cocok" not in followup_columns:
        conn.execute(
            "ALTER TABLE kasus_tindak_lanjut "
            "ADD COLUMN tanggal_absensi_cocok INTEGER NOT NULL DEFAULT 1"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kasus_tindak_lanjut_periode "
        "ON kasus_tindak_lanjut (periode_id, status)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS aturan_apd "
        "(lab TEXT PRIMARY KEY, wajib_helm INTEGER NOT NULL, wajib_baju INTEGER NOT NULL, "
        "wajib_jeans INTEGER NOT NULL, wajib_sepatu INTEGER NOT NULL, "
        "aktif INTEGER NOT NULL DEFAULT 1)"
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO aturan_apd
        (lab, wajib_helm, wajib_baju, wajib_jeans, wajib_sepatu, aktif)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        [
            (
                lab,
                rule["helm"],
                rule["baju"],
                rule["jeans"],
                rule["sepatu"],
            )
            for lab, rule in DEFAULT_APD_RULES.items()
        ],
    )

    if conn.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0:
        users = [
            ("admin", "Administrator SIAP", "operator", "admin123"),
            ("dosen01", "Dr. Dosen Polman", "dosen", "dosen123"),
            ("plp01", "Petugas PLP", "PLP", "plp123"),
            ("224443009", "Lukita Falensia Marjan", "mahasiswa", "mahasiswa123"),
            ("224443003", "Bintang Shobri Al Chakim", "mahasiswa", "mahasiswa123"),
            ("224443012", "Muhammad Basit", "mahasiswa", "mahasiswa123"),
        ]
        conn.executemany(
            "INSERT INTO pengguna (identifier, nama, peran, password_hash) VALUES (?, ?, ?, ?)",
            [(u, n, r, generate_password_hash(p)) for u, n, r, p in users],
        )

    if conn.execute("SELECT COUNT(*) FROM mahasiswa").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO mahasiswa (nim, nama, kelas) VALUES (?, ?, ?)",
            [
                ("224443009", "Lukita Falensia Marjan", "3AEC1"),
                ("224443003", "Bintang Shobri Al Chakim", "3AEC1"),
                ("224443012", "Muhammad Basit", "3AEC1"),
                ("224201020", "Fajar Ramadhan", "2MEA"),
                ("223104021", "Dinda Larasati", "3FEA"),
                ("224302008", "Rafi Maulana", "2AEB"),
            ],
        )

    if conn.execute("SELECT COUNT(*) FROM sesi").fetchone()[0] == 0:
        admin = conn.execute(
            "SELECT id, nama FROM pengguna WHERE identifier = 'dosen01'"
        ).fetchone()
        conn.execute(
            "INSERT INTO sesi "
            "(lab, mata_kuliah, kelas, tanggal, jam_mulai, jam_selesai, dosen, ruang, aktif, dibuat_oleh) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            ("Manufaktur", "Praktik Proses Manufaktur", "3AEC1",
             date.today().isoformat(), "07:00", "10:00",
             admin["nama"], "Lab. CNC", admin["id"]),
        )

    conn.commit()
    conn.close()


init_db()


if __name__ == "__main__":
    print("[SIAP] Melakukan pre-loading model AI ke memori...")
    warmup_models()
    print("[SIAP] Model AI siap. Menjalankan server di http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
