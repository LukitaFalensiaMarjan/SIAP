import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app as siap_app


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = siap_app.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        siap_app.DB_PATH = Path(self.temp_dir.name) / "siap-test.db"
        siap_app.init_db()
        siap_app.app.config["TESTING"] = True
        self.client = siap_app.app.test_client()
        self.set_user("plp01")
        response = self.client.post(
            "/api/follow-up/periods",
            json={
                "nama": "Ganjil 2026/2027",
                "tanggal_mulai": "2026-11-01",
                "tanggal_selesai": "2026-12-31",
            },
        )
        self.assertEqual(response.status_code, 201)

    def tearDown(self):
        siap_app.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def set_user(self, identifier):
        with self.client.session_transaction() as state:
            state["identifier"] = identifier

    def add_attendance(self, index, failed_items, arrival_time):
        session_date = date(2026, 11, 10) + timedelta(days=index)
        conn = siap_app.get_db()
        staff_id = conn.execute(
            "SELECT id FROM pengguna WHERE identifier = 'dosen01'"
        ).fetchone()["id"]
        session_cursor = conn.execute(
            """
            INSERT INTO sesi
            (lab, mata_kuliah, kelas, tanggal, jam_mulai, jam_selesai,
             aktif, dibuat_oleh, dosen, ruang)
            VALUES ('Manufaktur', 'Praktik Uji', '3AEC1', ?, '08:00',
                    '10:00', 1, ?, 'Dosen Uji', 'Lab. CNC')
            """,
            (session_date.isoformat(), staff_id),
        )
        values = {
            "helm": int("helm" not in failed_items),
            "baju": int("baju" not in failed_items),
            "jeans": int("jeans" not in failed_items),
            "sepatu": int("sepatu" not in failed_items),
        }
        status = siap_app.attendance_status(values, ["helm", "baju", "jeans", "sepatu"])
        cursor = conn.execute(
            """
            INSERT INTO absensi
            (nim, sesi_id, waktu, helm, baju, jeans, sepatu, status,
             confidence, foto_path, catatan)
            VALUES ('224443012', ?, ?, ?, ?, ?, ?, ?, '{}', NULL, NULL)
            """,
            (
                session_cursor.lastrowid,
                f"{session_date.isoformat()}T{arrival_time}:00",
                values["helm"],
                values["baju"],
                values["jeans"],
                values["sepatu"],
                status,
            ),
        )
        conn.commit()
        conn.close()
        return cursor.lastrowid

    def test_tardiness_rounds_up_and_multiplies_by_five(self):
        self.assertEqual(
            siap_app.attendance_tardiness(
                "2026-11-01", "08:00", "2026-11-01T08:00:01"
            ),
            (1, 5),
        )
        self.assertEqual(
            siap_app.attendance_tardiness(
                "2026-11-01", "08:00", "2026-11-01T08:00:00"
            ),
            (0, 0),
        )
        self.assertEqual(
            siap_app.attendance_tardiness(
                "2026-11-01", "08:00", "2026-11-01T08:01:00.100"
            ),
            (2, 10),
        )
        self.assertEqual(
            siap_app.attendance_tardiness(
                "2026-11-01", "08:00", "2026-11-02T09:00:00"
            ),
            (None, None),
        )

    def test_progressive_warning_levels_and_post_sp3_persistence(self):
        first_case_id = None
        for index in range(3):
            attendance_id = self.add_attendance(index, {"helm"}, "08:00")
            response = self.client.post(f"/api/follow-up/{attendance_id}/confirm")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["case"]["sp_level"], 1)
            if index == 0:
                first_case_id = response.get_json()["case"]["id"]
        issued = self.client.post(f"/api/follow-up/cases/{first_case_id}/issue")
        self.assertEqual(issued.status_code, 200)

        fourth_id = self.add_attendance(3, {"helm"}, "08:00")
        fourth = self.client.post(f"/api/follow-up/{fourth_id}/confirm")
        self.assertEqual(fourth.get_json()["case"]["sp_level"], 2)

        fifth_id = self.add_attendance(
            4, {"helm", "baju", "jeans", "sepatu"}, "08:02"
        )
        fifth = self.client.post(f"/api/follow-up/{fifth_id}/confirm")
        self.assertEqual(fifth.get_json()["case"]["sp_level"], 3)
        self.assertEqual(fifth.get_json()["case"]["status"], "draf")

        sixth_id = self.add_attendance(5, {"helm"}, "08:02")
        sixth = self.client.post(f"/api/follow-up/{sixth_id}/confirm")
        self.assertEqual(sixth.get_json()["case"]["sp_level"], 3)

    def test_followup_list_calculates_late_compensation(self):
        attendance_id = self.add_attendance(0, set(), "08:02")
        response = self.client.get("/api/follow-up")
        self.assertEqual(response.status_code, 200)
        attendance = next(
            item for item in response.get_json()["attendance"]
            if item["id"] == attendance_id
        )
        self.assertEqual(attendance["terlambat_menit"], 2)
        self.assertEqual(attendance["kompensasi_menit"], 10)

    def test_late_over_two_hours_triggers_sp1(self):
        on_threshold = self.add_attendance(0, set(), "10:00")
        threshold_response = self.client.post(
            f"/api/follow-up/{on_threshold}/confirm"
        )
        self.assertEqual(threshold_response.status_code, 409)

        over_threshold = self.add_attendance(1, set(), "10:01")
        response = self.client.post(
            f"/api/follow-up/{over_threshold}/confirm"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["case"]["sp_level"], 1)

    def test_long_lateness_counts_toward_progressive_warnings(self):
        levels = []
        for index in range(4):
            attendance_id = self.add_attendance(index, set(), "10:01")
            response = self.client.post(f"/api/follow-up/{attendance_id}/confirm")
            self.assertEqual(response.status_code, 200)
            levels.append(response.get_json()["case"]["sp_level"])
        self.assertEqual(levels, [1, 1, 1, 2])

    def test_date_mismatch_is_not_counted_as_compensation(self):
        attendance_id = self.add_attendance(0, set(), "08:02")
        conn = siap_app.get_db()
        conn.execute(
            "UPDATE absensi SET waktu = '2026-11-12T08:02:00' WHERE id = ?",
            (attendance_id,),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/api/follow-up")
        item = next(
            row for row in response.get_json()["attendance"]
            if row["id"] == attendance_id
        )
        self.assertFalse(item["tanggal_absensi_cocok"])
        self.assertIsNone(item["terlambat_menit"])
        self.assertIsNone(item["kompensasi_menit"])

    def test_kiosk_rejects_sessions_outside_today(self):
        conn = siap_app.get_db()
        staff_id = conn.execute(
            "SELECT id FROM pengguna WHERE identifier = 'dosen01'"
        ).fetchone()["id"]
        session_id = conn.execute(
            """
            INSERT INTO sesi
            (lab, mata_kuliah, kelas, tanggal, jam_mulai, jam_selesai,
             aktif, dibuat_oleh, dosen, ruang)
            VALUES ('Manufaktur', 'Sesi Lama', '3AEC1', ?, '08:00',
                    '10:00', 1, ?, 'Dosen Uji', 'Lab. CNC')
            """,
            ((date.today() - timedelta(days=1)).isoformat(), staff_id),
        ).lastrowid
        conn.commit()
        conn.close()

        with siap_app.app.test_request_context():
            row, rule, error = siap_app.kiosk_session({"kelas": "3AEC1"}, session_id)
        self.assertIsNone(row)
        self.assertIsNone(rule)
        self.assertEqual(error[1], 404)

    def test_unresolved_required_attribute_blocks_confirmation(self):
        attendance_id = self.add_attendance(0, {"helm"}, "08:02")
        conn = siap_app.get_db()
        conn.execute(
            "UPDATE absensi SET jeans = NULL, status = 'menunggu_validasi' WHERE id = ?",
            (attendance_id,),
        )
        conn.commit()
        conn.close()

        response = self.client.post(f"/api/follow-up/{attendance_id}/confirm")
        self.assertEqual(response.status_code, 409)

        updated = self.client.patch(
            f"/api/absensi/{attendance_id}/jeans", json={"jeans": 1}
        )
        self.assertEqual(updated.status_code, 200)
        confirmed = self.client.post(f"/api/follow-up/{attendance_id}/confirm")
        self.assertEqual(confirmed.status_code, 200)
        locked = self.client.patch(
            f"/api/absensi/{attendance_id}/jeans", json={"jeans": 0}
        )
        self.assertEqual(locked.status_code, 409)

        conn = siap_app.get_db()
        audit_count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE aksi = 'verifikasi_jeans_manual'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(audit_count, 1)

    def test_operator_can_read_but_cannot_manage_followup(self):
        self.set_user("admin")
        self.assertEqual(self.client.get("/api/follow-up").status_code, 200)
        response = self.client.post(
            "/api/follow-up/periods",
            json={
                "nama": "Semester berikutnya",
                "tanggal_mulai": "2027-01-01",
                "tanggal_selesai": "2027-06-30",
            },
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
