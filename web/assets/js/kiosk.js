const KIOSK_APD_SCAN_FRAME_COUNT = 8;
const KIOSK_UNIFIED_VERIFY_DURATION_MS = 5000;
const KIOSK_UNIFIED_SCAN_INTERVAL_MS = 150;
const KIOSK_FACE_PROBABILITY_WINDOW = 4;

const kioskState = {
  student: null,
  students: [],
  sessions: [],
  stream: null,
  cameraDeviceId: null,
  cameraSelectionAvailable: false,
  cameraSwitching: false,
  faceVerified: false,
  faceImages: [],
  faceCropMode: 'hog',
  apdImages: null,
  sessionId: null,
  apd: null,
  lastFace: null,
  busy: false,
  inspectionDone: false
};

const kioskApdItems = {
  helm: { element: 'tagHelm', label: 'Helm' },
  baju: { element: 'tagWearpack', label: 'Baju praktik' },
  jeans: { element: 'tagCelana', label: 'Celana jeans' },
  sepatu: { element: 'tagSepatu', label: 'Sepatu safety' }
};

function speakKioskText(text) {
  try {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'id-ID';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const idVoice = voices.find(v => v.lang && (v.lang === 'id-ID' || v.lang.startsWith('id')));
    if (idVoice) utterance.voice = idVoice;
    window.speechSynthesis.speak(utterance);
  } catch (err) {
    console.warn('Speech synthesis error:', err);
  }
}

document.addEventListener('DOMContentLoaded', initKiosk);
window.addEventListener('pagehide', stopKioskCamera);

async function initKiosk() {
  // 0. Proteksi Kiosk: Wajib login akun Kiosk atau Operator/Admin
  try {
    const authRes = await fetch('/api/auth/me');
    if (!authRes.ok) {
      window.location.href = '/login.html';
      return;
    }
    const authData = await authRes.json();
    const userRole = String(authData.user?.peran || '').toLowerCase();
    if (!['kiosk', 'operator', 'admin'].includes(userRole)) {
      window.location.href = '/login.html';
      return;
    }
  } catch (_) {
    window.location.href = '/login.html';
    return;
  }

  // Pasang filter anti-huruf pada seluruh input NIM di Kiosk
  const nimInput = document.getElementById('kioskInputNim');
  if (nimInput) {
    nimInput.setAttribute('inputmode', 'numeric');
    nimInput.setAttribute('pattern', '[0-9]*');
    nimInput.addEventListener('input', function() {
      this.value = this.value.replace(/[^0-9]/g, '');
    });
    nimInput.addEventListener('keypress', function(e) {
      if (e.charCode < 48 || e.charCode > 57) {
        if (e.charCode !== 13) e.preventDefault();
      }
    });
  }

  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }

  const actionButton = document.getElementById('btnKioskAction');
  actionButton.addEventListener('click', handleKioskAction);
  const retryButton = document.getElementById('btnKioskApdRetry');
  if (retryButton) retryButton.addEventListener('click', retryInspection);

  const cameraSelect = document.getElementById('kioskCamera');
  if (cameraSelect) cameraSelect.addEventListener('change', handleKioskCameraChange);

  const cropSelect = document.getElementById('kioskFaceCropMode');
  if (cropSelect) {
    cropSelect.addEventListener('change', () => {
      kioskState.faceCropMode = cropSelect.value;
    });
  }

  actionButton.disabled = true;

  // 1. Muat konteks Kiosk dari server (Mahasiswa & Sesi Aktif) tanpa perlu login
  await loadKioskContext();

  // 2. Muat daftar kamera dan langsung nyalakan kamera agar siluet manusia terlihat
  await loadKioskCameras();
  try {
    await ensureKioskCamera();
    drawDetectionBoxes([]);
  } catch (err) {
    console.warn('Auto start camera notice:', err.message);
    setKioskStatus('Kamera Siap', 'Klik tombol di bawah untuk mengaktifkan kamera dan mulai.', false);
  }
}

async function loadKioskContext(targetNim = null, targetKelas = null) {
  try {
    const payload = {};
    if (targetNim) payload.nim = targetNim;
    if (targetKelas) payload.kelas = targetKelas;

    const res = await fetch('/api/kiosk/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(result.error || 'Data mahasiswa atau jadwal tidak ditemukan.');

    kioskState.students = result.students || [];
    kioskState.sessions = result.sessions || [];

    // Jika data mahasiswa ditemukan dan cocok
    if (result.student) {
      setActiveStudent(result.student);
      showStudentProfileSection(result.student);
    } else {
      kioskState.student = null;
      showStudentLoginSection();
    }

    // Tampilkan daftar sesi aktif
    populateKioskSessions(kioskState.sessions);
  } catch (err) {
    console.error('Error loadKioskContext:', err);
    throw err;
  }
}

function showStudentLoginSection() {
  const loginBox = document.getElementById('kioskLoginFormBox');
  const profileCard = document.getElementById('kioskStudentProfileCard');
  const authPill = document.getElementById('kioskAuthStatusPill');
  const authTitle = document.getElementById('kioskAuthTitle');
  const actionBtn = document.getElementById('btnKioskAction');

  if (loginBox) loginBox.style.display = 'block';
  if (profileCard) profileCard.style.display = 'none';
  if (authPill) {
    authPill.textContent = 'Siap Input';
    authPill.style.background = '#F1F5F9';
    authPill.style.color = '#64748B';
  }
  if (authTitle) authTitle.textContent = 'Input Presensi';
  if (actionBtn) {
    actionBtn.disabled = true;
    actionBtn.textContent = 'Masukkan NIM & Kelas Terlebih Dahulu';
  }
}

function showStudentProfileSection(student) {
  const loginBox = document.getElementById('kioskLoginFormBox');
  const profileCard = document.getElementById('kioskStudentProfileCard');
  const authPill = document.getElementById('kioskAuthStatusPill');
  const authTitle = document.getElementById('kioskAuthTitle');
  const actionBtn = document.getElementById('btnKioskAction');

  if (loginBox) loginBox.style.display = 'none';
  if (profileCard) profileCard.style.display = 'block';
  if (authPill) {
    authPill.textContent = 'Terkonfirmasi';
    authPill.style.background = '#DCFCE7';
    authPill.style.color = '#15803D';
  }
  if (authTitle) authTitle.textContent = 'Profil Mahasiswa';
  if (actionBtn) {
    actionBtn.disabled = !kioskState.sessionId || kioskState.busy;
    actionBtn.textContent = 'Mulai Pemeriksaan Wajah & APD';
  }
}

async function handleKioskStudentLogin(event) {
  event.preventDefault();
  const nimInput = document.getElementById('kioskInputNim');
  const kelasInput = document.getElementById('kioskInputKelas');
  const errEl = document.getElementById('kioskLoginError');
  const btn = document.getElementById('btnKioskStudentLogin');

  const rawNim = nimInput ? nimInput.value.trim() : '';
  const kelas = kelasInput ? kelasInput.value.trim().toUpperCase() : '';

  if (/[a-zA-Z]/.test(rawNim)) {
    if (errEl) {
      errEl.textContent = 'NIM hanya boleh berisi angka (tidak boleh huruf).';
      errEl.style.display = 'block';
    }
    return;
  }
  const nim = rawNim.replace(/[^0-9]/g, '');

  if (!nim || !kelas) {
    if (errEl) {
      errEl.textContent = 'NIM dan Kelas wajib diisi.';
      errEl.style.display = 'block';
    }
    return;
  }

  if (errEl) errEl.style.display = 'none';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Memverifikasi data...';
  }

  try {
    await loadKioskContext(nim, kelas);
    setKioskStatus('Identitas Terverifikasi', 'Posisikan tubuh dalam siluet lalu tekan tombol periksa.', false);
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || 'Data mahasiswa tidak ditemukan.';
      errEl.style.display = 'block';
    }
    setKioskStatus('Gagal Verifikasi', err.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Cari & Konfirmasi Mahasiswa →';
    }
  }
}
window.handleKioskStudentLogin = handleKioskStudentLogin;

function resetKioskSessionForNextQueue() {
  kioskState.student = null;
  kioskState.sessionId = null;
  kioskState.session = null;
  kioskState.inspectionDone = false;
  kioskState.apdImages = null;
  kioskState.faceImages = [];

  const nimInput = document.getElementById('kioskInputNim');
  const kelasInput = document.getElementById('kioskInputKelas');
  const errEl = document.getElementById('kioskLoginError');
  if (nimInput) {
    nimInput.value = '';
    nimInput.focus();
  }
  if (kelasInput) kelasInput.value = '';
  if (errEl) errEl.style.display = 'none';

  showStudentLoginSection();
  populateKioskSessions([]);
  drawDetectionBoxes([]);
  setKioskStatus('Kamera Siap', 'Silakan mahasiswa berikutnya memasukkan NIM dan Kelas.', false);
}
window.resetKioskSessionForNextQueue = resetKioskSessionForNextQueue;

function renderStudentSelector(students) {
  const container = document.getElementById('studentCardsContainer');
  if (!container) return;
  container.innerHTML = '';

  students.forEach(st => {
    const isSelected = kioskState.student && kioskState.student.nim === st.nim;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `kiosk-student-card-btn ${isSelected ? 'selected' : ''}`;
    btn.onclick = () => selectStudent(st.nim);
    btn.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px;">
        <div class="kiosk-mhs-avatar ${isSelected ? 'active' : ''}">
          ${st.nama.charAt(0)}
        </div>
        <div>
          <div style="font-weight: 800; font-size: 12.5px; color: ${isSelected ? '#0369A1' : '#0F172A'};">${st.nama}</div>
          <div style="font-size: 10.5px; color: #64748B;">NIM: ${st.nim} · Kelas: ${st.kelas}</div>
        </div>
      </div>
      <span class="kiosk-mhs-badge ${isSelected ? 'active' : ''}">${isSelected ? 'Aktif' : 'Pilih'}</span>
    `;
    container.appendChild(btn);
  });
}

function selectStudent(nim) {
  if (kioskState.busy) return;
  const found = kioskState.students.find(s => s.nim === nim);
  if (found) {
    setActiveStudent(found);
    renderStudentSelector(kioskState.students);
    // Reload sesi untuk kelas mahasiswa tersebut jika perlu
    loadKioskContext(nim);
  }
}
window.selectStudent = selectStudent;

function setActiveStudent(student) {
  kioskState.student = student;
  const nameEl = document.getElementById('kioskProfileName');
  const detailEl = document.getElementById('kioskProfileDetail');
  if (nameEl) nameEl.textContent = student.nama;
  if (detailEl) detailEl.textContent = `NIM: ${student.nim} · Kelas: ${student.kelas}`;

  const statusPill = document.getElementById('kioskStudentStatus');
  if (statusPill) statusPill.textContent = `Mahasiswa: ${student.nama.split(' ')[0]}`;

  const actionBtn = document.getElementById('btnKioskAction');
  if (actionBtn && !kioskState.inspectionDone) {
    actionBtn.disabled = !kioskState.sessionId || kioskState.busy;
    actionBtn.textContent = 'Mulai Pemeriksaan Wajah & APD';
  }
}

function updateSessionApdChecklist(wajibList) {
  const reqs = new Set(wajibList || ['helm', 'baju', 'jeans', 'sepatu']);
  const map = {
    helm: document.getElementById('badgeHelmReq'),
    baju: document.getElementById('badgeBajuReq'),
    jeans: document.getElementById('badgeJeansReq'),
    sepatu: document.getElementById('badgeSepatuReq'),
  };

  Object.entries(map).forEach(([key, el]) => {
    if (!el) return;
    const isWajib = reqs.has(key);
    const span = el.querySelector('.badge-status');
    if (span) {
      if (isWajib) {
        span.textContent = 'WAJIB';
        span.style.color = '#16A34A';
        span.style.background = '#DCFCE7';
        span.style.padding = '2px 6px';
        span.style.borderRadius = '4px';
      } else {
        span.textContent = 'OPSIONAL';
        span.style.color = '#64748B';
        span.style.background = '#F1F5F9';
        span.style.padding = '2px 6px';
        span.style.borderRadius = '4px';
      }
    }
  });
}

function showNoSessionPopup(student) {
  const overlay = document.getElementById('noSessionOverlay');
  if (!overlay) return;
  const nameEl = document.getElementById('noSessionStudentName');
  const nimEl = document.getElementById('noSessionStudentNim');
  const kelasEl = document.getElementById('noSessionStudentKelas');
  if (nameEl) nameEl.textContent = student ? student.nama : '—';
  if (nimEl) nimEl.textContent = student ? student.nim : '—';
  if (kelasEl) kelasEl.textContent = student ? student.kelas : '—';
  overlay.style.display = 'flex';
}

function dismissNoSessionPopup() {
  const overlay = document.getElementById('noSessionOverlay');
  if (overlay) overlay.style.display = 'none';
}
window.dismissNoSessionPopup = dismissNoSessionPopup;

function dismissSuccessPopup() {
  const overlay = document.getElementById('successOverlay');
  if (overlay) overlay.style.display = 'none';
  resetKioskSessionForNextQueue();
}
window.dismissSuccessPopup = dismissSuccessPopup;

function populateKioskSessions(sessions) {
  const select = document.getElementById('kioskSession');
  const message = document.getElementById('kioskSessionMessage');
  const cardTitle = document.getElementById('kioskSessionTitle');
  const cardSub = document.getElementById('kioskSessionSubtitle');
  const cardBadge = document.getElementById('kioskSessionBadge');
  const actionBtn = document.getElementById('btnKioskAction');

  if (select) select.replaceChildren();

  if (!sessions || sessions.length === 0) {
    if (select) {
      select.add(new Option('Tidak ada sesi praktikum aktif hari ini', ''));
      select.disabled = true;
    }
    kioskState.sessionId = null;
    kioskState.session = null;
    if (message) message.textContent = 'Tidak ada sesi praktikum aktif untuk kelas ini.';
    if (cardTitle) cardTitle.textContent = 'Tidak Ada Sesi Praktikum Hari Ini';
    if (cardSub) cardSub.textContent = kioskState.student ? `Kelas ${kioskState.student.kelas} tidak memiliki jadwal aktif hari ini.` : 'Jadwal praktikum kosong.';
    if (cardBadge) {
      cardBadge.textContent = 'Tidak Ada Sesi';
      cardBadge.style.background = '#FEE2E2';
      cardBadge.style.color = '#B91C1C';
    }
    if (actionBtn) actionBtn.disabled = true;

    // Tampilkan popup informasi jika mahasiswa aktif terpilih
    if (kioskState.student) {
      showNoSessionPopup(kioskState.student);
    }
    updateSessionApdChecklist([]);
    return;
  }

  // Tutup overlay no-session jika sebelumnya sempat terbuka
  dismissNoSessionPopup();

  sessions.forEach(item => {
    const label = `${item.mata_kuliah} · ${item.lab} (${item.jam_mulai}–${item.jam_selesai})`;
    if (select) select.add(new Option(label, String(item.id)));
  });

  // Otomatis pilih sesi aktif yang pertama
  const activeSession = sessions[0];
  if (select) {
    select.value = String(activeSession.id);
    select.disabled = false;
  }
  kioskState.sessionId = activeSession.id;
  kioskState.session = activeSession;

  if (cardTitle) {
    cardTitle.textContent = `${activeSession.mata_kuliah}`;
  }
  if (cardSub) {
    cardSub.textContent = `Lab: ${activeSession.lab} | Ruang: ${activeSession.ruang || '—'} | Pukul ${activeSession.jam_mulai}–${activeSession.jam_selesai} WIB`;
  }
  if (cardBadge) {
    cardBadge.textContent = `Aktif (${activeSession.kelas})`;
    cardBadge.style.background = '#DCFCE7';
    cardBadge.style.color = '#15803D';
  }

  if (message) {
    message.textContent = `Sesi aktif terpilih otomatis: ${activeSession.mata_kuliah} (${activeSession.lab})`;
  }

  // Update daftar APD Wajib sesuai mata kuliah sesi ini
  updateSessionApdChecklist(activeSession.wajib);

  if (actionBtn && !kioskState.inspectionDone) {
    actionBtn.disabled = !kioskState.student || kioskState.busy;
  }

  if (select) {
    select.onchange = () => {
      kioskState.sessionId = select.value ? Number(select.value) : null;
      const cur = sessions.find(s => s.id === kioskState.sessionId);
      if (cur) {
        kioskState.session = cur;
        if (cardTitle) cardTitle.textContent = cur.mata_kuliah;
        if (cardSub) cardSub.textContent = `Lab: ${cur.lab} | Ruang: ${cur.ruang || '—'} | Pukul ${cur.jam_mulai}–${cur.jam_selesai} WIB`;
        updateSessionApdChecklist(cur.wajib);
      }
      if (actionBtn && !kioskState.inspectionDone) {
        actionBtn.disabled = !kioskState.student || !kioskState.sessionId || kioskState.busy;
      }
    };
  }
}

function setKioskStatus(title, detail, isError) {
  const heading = document.getElementById('camStatusHeader');
  if (heading) {
    heading.textContent = title;
    heading.style.color = isError ? '#FCA5A5' : '#FFFFFF';
  }
  const detailEl = document.getElementById('camStatusDetail');
  if (detailEl) detailEl.textContent = detail;
}

function setCameraStatus(active, detail) {
  const pill = document.getElementById('camStatusPill');
  if (pill) pill.classList.toggle('active', active);
  const dot = document.getElementById('camStatusDot');
  if (dot) dot.style.background = active ? '#10B981' : '#94A3B8';
  const text = document.getElementById('camStatusText');
  if (text) text.textContent = active ? 'CAMERA ACTIVE' : 'CAMERA OFF';
  if (!active) setKioskStatus('Menunggu kamera', detail || 'Kamera sedang dinonaktifkan.', false);
}

async function loadKioskCameras() {
  const select = document.getElementById('kioskCamera');
  const message = document.getElementById('kioskCameraMessage');
  if (!select) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    kioskState.cameraSelectionAvailable = false;
    select.replaceChildren(new Option('Kamera otomatis', ''));
    select.disabled = true;
    return;
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter(d => d.kind === 'videoinput');
    select.replaceChildren();

    cameras.forEach((camera, idx) => {
      select.add(new Option(camera.label || `Kamera ${idx + 1}`, camera.deviceId));
    });

    if (cameras.length === 0) {
      select.add(new Option('Kamera browser default', ''));
      kioskState.cameraDeviceId = null;
      kioskState.cameraSelectionAvailable = false;
      select.disabled = true;
      return;
    }

    kioskState.cameraSelectionAvailable = true;
    const selectedExists = cameras.some(c => c.deviceId === kioskState.cameraDeviceId);
    kioskState.cameraDeviceId = selectedExists ? kioskState.cameraDeviceId : cameras[0].deviceId;
    select.value = kioskState.cameraDeviceId;
    select.disabled = kioskState.busy || kioskState.cameraSwitching;
    if (message) {
      message.textContent = `${cameras.length} kamera terdeteksi. Silakan pilih kamera yang menghadap lurus.`;
    }
  } catch (err) {
    select.replaceChildren(new Option('Kamera browser default', ''));
    select.disabled = true;
  }
}

async function handleKioskCameraChange() {
  const select = document.getElementById('kioskCamera');
  if (!select || kioskState.busy || kioskState.cameraSwitching) return;

  const previousId = kioskState.cameraDeviceId;
  const newId = select.value || null;
  if (newId === previousId) return;

  kioskState.cameraDeviceId = newId;
  kioskState.cameraSwitching = true;
  select.disabled = true;
  stopKioskCamera();

  try {
    await ensureKioskCamera();
    drawDetectionBoxes([]);
  } catch (err) {
    kioskState.cameraDeviceId = previousId;
    select.value = previousId || '';
    try {
      await ensureKioskCamera();
    } catch (_) {}
    setKioskStatus('Kamera gagal diganti', err.message, true);
  } finally {
    kioskState.cameraSwitching = false;
    select.disabled = kioskState.busy || !kioskState.cameraSelectionAvailable;
  }
}

async function ensureKioskCamera() {
  if (kioskState.stream) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('Browser tidak mendukung akses kamera.');
  }

  const videoConstraints = kioskState.cameraDeviceId
    ? { deviceId: { exact: kioskState.cameraDeviceId } }
    : { facingMode: { ideal: 'user' } };

  const stream = await navigator.mediaDevices.getUserMedia({
    video: { ...videoConstraints, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false
  });

  const video = document.getElementById('kioskVideo');
  video.srcObject = stream;
  video.style.display = 'block';

  await new Promise((resolve, reject) => {
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      resolve();
      return;
    }
    const timeout = setTimeout(() => reject(new Error('Kamera tidak mengirim gambar.')), 10000);
    video.addEventListener('loadeddata', () => {
      clearTimeout(timeout);
      resolve();
    }, { once: true });
    video.addEventListener('error', () => {
      clearTimeout(timeout);
      reject(new Error('Gagal membaca feed kamera.'));
    }, { once: true });
  });

  await video.play();
  kioskState.stream = stream;
  await loadKioskCameras();
  setCameraStatus(true, 'Kamera aktif.');
}

function stopKioskCamera() {
  if (!kioskState.stream) return;
  kioskState.stream.getTracks().forEach(t => t.stop());
  kioskState.stream = null;
  const video = document.getElementById('kioskVideo');
  if (video) {
    video.srcObject = null;
    video.style.display = 'none';
  }
  setCameraStatus(false, 'Kamera dinonaktifkan.');
  drawDetectionBoxes([], { hideGuide: true });
}

function captureKioskFrame() {
  const video = document.getElementById('kioskVideo');
  if (!video || !video.videoWidth || !video.videoHeight) {
    throw new Error('Kamera belum siap mengambil citra.');
  }
  const scale = Math.min(1, 1280 / video.videoWidth, 720 / video.videoHeight);
  const canvas = document.getElementById('kioskCanvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.80);
}

async function postKioskScan(phase, image, sessionId, cropMode, prevEma, prevDetected) {
  const payload = {
    ...(kioskState.student || {}),
    phase: phase || 'unified',
    sesi_id: sessionId,
    crop_mode: cropMode || 'hog',
    image
  };
  if (prevEma) payload.previous_ema = prevEma;
  if (prevDetected) payload.previous_detected = prevDetected;

  const response = await fetch('/api/kiosk/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || 'Pemindaian gagal diproses.');
  return result;
}

function setKioskBusy(busy, label) {
  kioskState.busy = busy;
  const btn = document.getElementById('btnKioskAction');
  if (btn) {
    btn.disabled = busy || !kioskState.student || !kioskState.sessionId;
    if (label) btn.textContent = label;
  }
  const retryBtn = document.getElementById('btnKioskApdRetry');
  if (retryBtn) retryBtn.disabled = busy;
  const camSelect = document.getElementById('kioskCamera');
  if (camSelect) camSelect.disabled = busy || !kioskState.cameraSelectionAvailable;
}

async function handleKioskAction() {
  if (kioskState.busy) return;
  if (!kioskState.sessionId) {
    setKioskStatus('Pilih Sesi Praktikum', 'Pilih sesi aktif sebelum memulai pemindaian.', true);
    return;
  }
  if (!kioskState.inspectionDone) {
    await startUnifiedInspection();
  } else {
    await finishKioskAttendance();
  }
}

/* ══════════════════════════════════════════════════════════════════════
   PEMERIKSAAN TERPADU WAJAH & APD SEKALIGUS (UNIFIED INSPECTION)
   ══════════════════════════════════════════════════════════════════════ */
async function startUnifiedInspection() {
  setKioskBusy(true, 'Menyiapkan pemeriksaan...');
  const laser = document.getElementById('scanLaser');
  if (laser) laser.style.display = 'none';

  const retryBtn = document.getElementById('btnKioskApdRetry');
  if (retryBtn) retryBtn.hidden = true;

  drawDetectionBoxes([]);

  try {
    await ensureKioskCamera();

    // Hitung mundur 3 detik dengan arahan suara
    speakKioskText('Silakan berdiri tegak di garis panduan.');
    for (let sec = 3; sec > 0; sec--) {
      setKioskStatus(
        'Bersiap untuk Pemeriksaan K3',
        `Pemindaian wajah dan APD dimulai dalam ${sec} detik. Posisikan seluruh tubuh di dalam garis panduan.`,
        false
      );
      await new Promise(r => setTimeout(r, 1000));
    }

    if (laser) {
      laser.style.display = 'block';
      laser.style.animation = 'kioskLaserAnimation 2.2s infinite ease-in-out';
    }

    const actionBtn = document.getElementById('btnKioskAction');
    if (actionBtn) actionBtn.textContent = 'Memindai Wajah & APD...';

    const startTime = Date.now();
    const framesCollected = [];
    const probabilityHistory = [];
    let prevEma = {};
    let prevDetected = {};
    let lastApdResult = null;
    let lastFaceResult = null;
    let faceMismatchCount = 0;
    let faceVerifiedFrames = 0;

    // Pemindaian terpadu dinamis selama 5 detik penuh
    while (Date.now() - startTime < KIOSK_UNIFIED_VERIFY_DURATION_MS) {
      const frame = captureKioskFrame();
      framesCollected.push(frame);
      if (framesCollected.length > KIOSK_APD_SCAN_FRAME_COUNT) {
        framesCollected.shift();
      }

      const scanResult = await postKioskScan(
        'unified',
        frame,
        kioskState.sessionId,
        kioskState.faceCropMode,
        prevEma,
        prevDetected
      );

      // 1. Tangkap hasil APD
      if (scanResult.apd) {
        lastApdResult = scanResult.apd;
        Object.entries(scanResult.apd).forEach(([item, val]) => {
          prevEma[item] = val.probability;
          prevDetected[item] = val.worn;
        });
      }

      // 2. Tangkap hasil Wajah & Validasi Kontinuitas (Anti-Joki & Batas Siluet)
      if (scanResult.face) {
        lastFaceResult = scanResult.face;

        // Auto-assign student jika belum dipilih manual
        if (!kioskState.student && scanResult.student) {
          setActiveStudent(scanResult.student);
          renderStudentSelector(kioskState.students);
        }

        const expectedName = kioskState.student?.nama || '';
        const detectedLabel = lastFaceResult.label || '';
        const conf = lastFaceResult.confidence || 0;

        // A. VALIDASI DETEKSI: HANYA DETEKSI JIKA BERADA DI DALAM GARIS SILUET
        if (!lastFaceResult.detected) {
          faceVerifiedFrames = 0;
          let guideNotice = 'Berdiri tegak menghadap kamera tepat di dalam garis panduan.';
          let guideHeader = 'Mencari Posisi di Garis Panduan...';

          if (lastFaceResult.reason === 'outside') {
            guideHeader = 'Wajah di Luar Garis Panduan';
            guideNotice = 'Wajah berada di luar garis. Posisikan diri tepat di dalam garis panduan.';
          } else if (lastFaceResult.reason === 'too_close') {
            guideHeader = 'Mundurlah Beberapa Langkah';
            guideNotice = 'Posisi Anda terlalu dekat dengan kamera. Mundurlah hingga seluruh tubuh terlihat di dalam garis panduan.';
          }

          setKioskStatus(guideHeader, guideNotice, false);
          // Sembunyikan tag APD karena tidak ada orang di dalam siluet
          Object.keys(kioskApdItems).forEach(k => {
            const el = document.getElementById(kioskApdItems[k]?.element);
            if (el) el.style.display = 'none';
          });

          drawDetectionBoxes([], { alertMismatch: false, faceMatched: false });
          await new Promise(r => setTimeout(r, KIOSK_UNIFIED_SCAN_INTERVAL_MS));
          continue;
        }

        // B. VALIDASI KECOCOKAN IDENTITAS DI DALAM SILUET (ANTI-JOKI)
        if (lastFaceResult.detected && lastFaceResult.matched) {
          faceVerifiedFrames++;
          faceMismatchCount = 0;
        } else if (lastFaceResult.detected && !lastFaceResult.matched && conf >= 0.65) {
          faceMismatchCount++;
          if (faceMismatchCount >= 2) {
            // TERDETEKSI KECURANGAN / WAJAH BERBEDA
            drawDetectionBoxes([{
              box: lastFaceResult.box,
              dimensions: lastFaceResult.dimensions,
              label: `DITOLAK: BUKAN ${expectedName.toUpperCase()} (${detectedLabel})`,
              color: '#EF4444'
            }], { alertMismatch: true, multiPerson: lastFaceResult.multi_person });

            speakKioskText(`Peringatan. Wajah terdeteksi adalah ${detectedLabel}, berbeda dengan identitas ${expectedName}. Pemeriksaan APD ditolak.`);

            setKioskStatus(
              'Pemeriksaan Ditolak!',
              `Wajah yang berdiri di depan kamera (${detectedLabel}) tidak sesuai dengan akun mahasiswa (${expectedName}). Mahasiswa yang bersangkutan wajib berdiri di dalam area garis panduan.`,
              true
            );

            // Sembunyikan tag APD
            Object.keys(kioskApdItems).forEach(k => {
              const el = document.getElementById(kioskApdItems[k]?.element);
              if (el) el.style.display = 'none';
            });

            setKioskBusy(false, 'Ulangi Pemeriksaan');
            if (actionBtn) actionBtn.disabled = false;
            kioskState.busy = false;
            return;
          }
        }
      }

      // Kumpulkan Bounding Box Dinamis (Wajah + 4 Komponen APD)
      const liveBoxes = [];

      // A. Kotak Deteksi Wajah
      if (lastFaceResult && lastFaceResult.detected && lastFaceResult.box) {
        const faceName = lastFaceResult.label || 'Wajah';
        const faceScore = Math.round((lastFaceResult.confidence || 0) * 100);
        liveBoxes.push({
          box: lastFaceResult.box,
          dimensions: lastFaceResult.dimensions,
          label: `${faceName} ${faceScore}%`,
          color: lastFaceResult.matched ? '#10B981' : '#F59E0B'
        });
      }

      // B. Kotak Deteksi APD (Helm, Kemeja, Jeans, Sepatu)
      if (lastApdResult) {
        Object.entries(lastApdResult).forEach(([key, item]) => {
          if (item.wajib && item.worn && item.box) {
            liveBoxes.push({
              box: item.box,
              dimensions: item.dimensions,
              label: `${item.label || key.toUpperCase()} ${Math.round(item.probability * 100)}%`,
              color: item.color || '#22C55E'
            });
          }

          // Perbarui badge status di pojok kanan atas dengan Ambang Batas 3 Tingkat:
          // >= 85%: OK (Hijau)
          // 75% - 84%: Verifikasi Admin (Amber)
          // < 75%: Kurang (Merah, tidak dianggap terpakai)
          const tag = document.getElementById(kioskApdItems[key]?.element);
          if (tag) {
            if (!item.wajib) {
              tag.style.display = 'none';
            } else if (item.reason === 'half_body') {
              tag.textContent = `${kioskApdItems[key].label}: Silakan Mundur / Berdiri`;
              tag.style.borderColor = '#F59E0B';
              tag.style.color = '#F59E0B';
              tag.style.display = 'block';
            } else {
              const score = Math.round((item.probability || 0) * 100);
              let statusLabel = '';
              let badgeColor = '';

              if (score >= 85) {
                statusLabel = `OK (${score}%)`;
                badgeColor = '#22C55E';
              } else if (score >= 75) {
                statusLabel = `Verifikasi Admin (${score}%)`;
                badgeColor = '#F59E0B';
              } else {
                statusLabel = `Kurang (${score}%)`;
                badgeColor = '#EF4444';
              }

              tag.textContent = `${kioskApdItems[key].label}: ${statusLabel}`;
              tag.style.borderColor = badgeColor;
              tag.style.color = badgeColor;
              tag.style.display = 'block';
            }
          }
        });
      }

      // Gambar Garis Panduan Siluet Manusia Berdiri + Bounding Box Dinamis
      drawDetectionBoxes(liveBoxes, {
        faceMatched: lastFaceResult?.matched,
        multiPerson: lastFaceResult?.multi_person,
        apdResult: lastApdResult
      });

      const elapsed = Date.now() - startTime;
      const remainingSec = Math.max(0, (KIOSK_UNIFIED_VERIFY_DURATION_MS - elapsed) / 1000).toFixed(1);
      const isHalfBody = Object.values(lastApdResult || {}).some(x => x.reason === 'half_body');
      let subNotice = `Waktu pemindaian: ${remainingSec} dtk tersisa. Berdiri tegak di garis panduan.`;
      if (lastFaceResult?.multi_person) {
        subNotice = `Memeriksa 1 orang di dalam garis panduan (${remainingSec} dtk). Orang lain di luar garis diabaikan.`;
      } else if (isHalfBody) {
        subNotice = `⚠️ Terdeteksi duduk/setengah badan (${remainingSec} dtk). Mundur & berdirilah agar celana & sepatu masuk garis panduan.`;
      }
      setKioskStatus(
        isHalfBody ? 'Posisikan Seluruh Tubuh di Garis Panduan' : 'Memeriksa Wajah & Kelengkapan APD...',
        subNotice,
        false
      );

      await new Promise(r => setTimeout(r, KIOSK_UNIFIED_SCAN_INTERVAL_MS));
    }

    if (laser) laser.style.display = 'none';

    // Verifikasi final wajah
    if (faceVerifiedFrames < 3 || !lastFaceResult || !lastFaceResult.detected || !lastFaceResult.matched) {
      throw new Error('Wajah belum berada stabil di dalam garis panduan. Berdirilah tegak tepat di dalam garis panduan dan coba lagi.');
    }

    // Evaluasi kelengkapan APD (Semua item wajib dievaluasi tanpa pengecualian)
    // 1. Ada item wajib < 75%: STATUS KURANG (tidak dianggap terpakai)
    // 2. Tidak ada yang < 75%, tapi ada yang 75% - 84%: STATUS PERLU VERIFIKASI ADMIN
    // 3. Hanya jika semua item wajib >= 85%: STATUS LENGKAP & SESUAI
    kioskState.faceVerified = true;
    kioskState.apd = lastApdResult;
    kioskState.lastFace = lastFaceResult;
    kioskState.faceImages = framesCollected.slice(0, 4);
    kioskState.apdImages = framesCollected;
    kioskState.inspectionDone = true;

    let missingList = [];
    let needVerifyList = [];
    if (lastApdResult) {
      Object.entries(lastApdResult).forEach(([k, it]) => {
        if (it.wajib) {
          const score = Math.round((it.probability || 0) * 100);
          const labelName = kioskApdItems[k]?.label || k;
          if (score < 75) {
            missingList.push(`${labelName} (${score}%)`);
          } else if (score < 85) {
            needVerifyList.push(`${labelName} (${score}%)`);
          }
        }
      });
    }

    const hasMissing = missingList.length > 0;
    const hasVerify = needVerifyList.length > 0;
    const stName = kioskState.student?.nama?.split(' ')[0] || 'Mahasiswa';

    let completionMsg = '';
    let statusHeader = '';
    let statusDesc = '';

    if (hasMissing) {
      statusHeader = 'Pemeriksaan Selesai (Ada APD Kurang)';
      statusDesc = `APD belum sesuai (< 75%): ${missingList.join(', ')}. Hasil dicatat dan ditindaklanjuti.`;
      completionMsg = `Pemeriksaan selesai, ${stName}. Ada kelengkapan APD yang belum lengkap.`;
    } else if (hasVerify) {
      statusHeader = 'Pemeriksaan Selesai (Perlu Verifikasi Admin)';
      statusDesc = `APD ${needVerifyList.join(', ')} (75% - 84%) membutuhkan verifikasi oleh Admin atau PLP laboratorium.`;
      completionMsg = `Pemeriksaan selesai. Kelengkapan keselamatan Anda memerlukan verifikasi oleh admin.`;
    } else {
      statusHeader = 'Pemeriksaan Selesai (Lengkap & Sesuai)';
      statusDesc = 'Identitas wajah dan seluruh APD K3 terverifikasi valid (>= 85%). Silakan simpan kehadiran.';
      completionMsg = `Pemeriksaan selesai. Kelengkapan keselamatan Anda sesuai. Silakan simpan kehadiran.`;
    }

    speakKioskText(completionMsg);

    setKioskStatus(statusHeader, statusDesc, hasMissing);

    if (actionBtn) {
      actionBtn.textContent = 'Simpan Kehadiran';
      actionBtn.disabled = false;
    }
    if (retryBtn) retryBtn.hidden = false;
  } catch (error) {
    if (laser) laser.style.display = 'none';
    drawDetectionBoxes([]);
    setKioskStatus('Pemeriksaan Gagal', error.message, true);
    setKioskBusy(false, 'Coba Pemeriksaan Lagi');
    if (retryBtn) retryBtn.hidden = false;
    return;
  }

  setKioskBusy(false, 'Simpan Kehadiran');
}

async function retryInspection() {
  if (kioskState.busy) return;
  kioskState.inspectionDone = false;
  kioskState.apd = null;
  kioskState.lastFace = null;
  kioskState.apdImages = null;
  kioskState.faceImages = [];

  drawDetectionBoxes([]);
  const retryBtn = document.getElementById('btnKioskApdRetry');
  if (retryBtn) retryBtn.hidden = true;

  Object.values(kioskApdItems).forEach(it => {
    const el = document.getElementById(it.element);
    if (el) el.style.display = 'none';
  });

  await startUnifiedInspection();
}

/* ══════════════════════════════════════════════════════════════════════
   SIMPAN KEHADIRAN KE SERVER
   ══════════════════════════════════════════════════════════════════════ */
async function finishKioskAttendance() {
  if (!kioskState.inspectionDone || !kioskState.student || !kioskState.sessionId) return;
  setKioskBusy(true, 'Menyimpan kehadiran...');

  try {
    const res = await fetch('/api/kiosk/attendance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...kioskState.student,
        sesi_id: kioskState.sessionId,
        images: kioskState.apdImages,
        face_images: kioskState.faceImages,
        face_crop_mode: kioskState.faceCropMode
      })
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(result.error || 'Kehadiran gagal disimpan.');

    const attendance = result.attendance;
    const time = new Date(attendance.waktu.replace(' ', 'T'));
    
    // 1. Data Mahasiswa & Sesi di Popup
    const nameEl = document.getElementById('successStudentName');
    if (nameEl) nameEl.textContent = kioskState.student.nama;
    const nimKelasEl = document.getElementById('successStudentNimKelas');
    if (nimKelasEl) nimKelasEl.textContent = `NIM: ${kioskState.student.nim} · Kelas: ${kioskState.student.kelas}`;

    const sessEl = document.getElementById('successSession');
    if (sessEl) sessEl.textContent = `${attendance.mata_kuliah} (${attendance.lab || 'Lab'})`;

    const successTimeEl = document.getElementById('successTime');
    if (successTimeEl) {
      successTimeEl.textContent = Number.isNaN(time.getTime())
        ? attendance.waktu
        : new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'medium' }).format(time);
    }

    // 2. Status Keterlambatan
    const lateBadge = document.getElementById('successLateBadge');
    if (lateBadge) {
      if (attendance.terlambat_menit && attendance.terlambat_menit > 0) {
        lateBadge.textContent = `Terlambat ${attendance.terlambat_menit} Menit (Denda ${attendance.kompensasi_menit || 0} Menit)`;
        lateBadge.style.background = '#FEE2E2';
        lateBadge.style.color = '#B91C1C';
      } else {
        lateBadge.textContent = 'Tepat Waktu';
        lateBadge.style.background = '#DCFCE7';
        lateBadge.style.color = '#15803D';
      }
    }

    // 3. Status Keseluruhan APD & Rincian per Atribut
    const overallBadge = document.getElementById('successApdOverallBadge');
    if (overallBadge) {
      if (attendance.status === 'lengkap') {
        overallBadge.textContent = 'LENGKAP';
        overallBadge.style.background = '#059669';
      } else if (attendance.status === 'menunggu_validasi') {
        overallBadge.textContent = 'MENUNGGU VALIDASI';
        overallBadge.style.background = '#D97706';
      } else {
        overallBadge.textContent = 'TIDAK LENGKAP';
        overallBadge.style.background = '#DC2626';
      }
    }

    const itemsContainer = document.getElementById('successApdItemsList');
    const notesContainer = document.getElementById('successApdNotes');
    const incompleteList = [];

    if (itemsContainer) {
      itemsContainer.innerHTML = '';
      const apdConfig = [
        { key: 'helm', name: 'Helm K3', icon: '🪖' },
        { key: 'baju', name: 'Baju Praktik', icon: '👔' },
        { key: 'jeans', name: 'Celana Jeans', icon: '👖' },
        { key: 'sepatu', name: 'Sepatu Safety', icon: '👞' },
      ];

      const wajibList = new Set(result.wajib || []);

      apdConfig.forEach(item => {
        const isWajib = wajibList.has(item.key);
        const val = attendance[item.key];
        
        let statusText = '';
        let statusColor = '';
        let bgColor = 'rgba(255,255,255,0.05)';

        if (!isWajib) {
          statusText = 'Tidak Wajib';
          statusColor = '#94A3B8';
        } else if (val === 1 || val === true) {
          statusText = 'Terpakai';
          statusColor = '#34D399';
          bgColor = 'rgba(16, 185, 129, 0.12)';
        } else if (val === 0 || val === false) {
          statusText = 'Tidak Terpakai';
          statusColor = '#F87171';
          bgColor = 'rgba(239, 68, 68, 0.15)';
          incompleteList.push(item.name);
        } else {
          statusText = 'Perlu Validasi';
          statusColor = '#FBBF24';
          bgColor = 'rgba(245, 158, 11, 0.15)';
        }

        const div = document.createElement('div');
        div.style.cssText = `background: ${bgColor}; padding: 6px 10px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.06);`;
        div.innerHTML = `
          <span>${item.icon} ${item.name}</span>
          <span style="font-weight: 800; font-size: 10px; color: ${statusColor};">${statusText}</span>
        `;
        itemsContainer.appendChild(div);
      });
    }

    if (notesContainer) {
      if (incompleteList.length > 0) {
        notesContainer.textContent = `Perhatian: ${incompleteList.join(', ')} wajib digunakan selama kegiatan praktikum.`;
        notesContainer.style.display = 'block';
      } else {
        notesContainer.style.display = 'none';
      }
    }

    const overlay = document.getElementById('successOverlay');
    if (overlay) overlay.style.display = 'flex';

    speakKioskText(`Presensi ${kioskState.student.nama} berhasil dicatat.`);
    setKioskStatus('Kehadiran Berhasil Disimpan', 'Data presensi dan hasil APD telah tercatat.', false);

    stopKioskCamera();
  } catch (error) {
    setKioskStatus('Gagal Menyimpan Kehadiran', error.message, true);
    setKioskBusy(false, 'Coba Simpan Lagi');
  }
}

/* ══════════════════════════════════════════════════════════════════════
   VISUAL OVERLAY: SILUET MANUSIA BERDIRI LENGKAP & BOUNDING BOX DINAMIS
   ══════════════════════════════════════════════════════════════════════ */
function drawDetectionBoxes(boxes, options = {}) {
  const canvas = document.getElementById('kioskOverlayCanvas');
  const video = document.getElementById('kioskVideo');
  if (!canvas || !video) return;

  const rect = video.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return;

  if (canvas.width !== Math.round(rect.width) || canvas.height !== Math.round(rect.height)) {
    canvas.width = Math.round(rect.width);
    canvas.height = Math.round(rect.height);
  }
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const cw = canvas.width;
  const ch = canvas.height;

  // 1. GAMBAR GARIS SILUET MANUSIA BERDIRI LENGKAP DENGAN 4 ZONA APD
  if (!options.hideGuide) {
    drawStandingHumanSilhouette(ctx, cw, ch, options);
  }

  // 2. GAMBAR BOUNDING BOX OBJEK DINAMIS (Wajah & APD yang Terdeteksi)
  if (!boxes || boxes.length === 0) return;

  boxes.forEach(item => {
    if (!item.box || item.box.length !== 4) return;
    const [x0, y0, x1, y1] = item.box;
    const [origW, origH] = item.dimensions || [640, 480];

    const scale = Math.max(canvas.width / origW, canvas.height / origH);
    const renderW = origW * scale;
    const renderH = origH * scale;
    const offsetX = (canvas.width - renderW) / 2;
    const offsetY = (canvas.height - renderH) / 2;

    const dx = Math.round(offsetX + x0 * scale);
    const dy = Math.round(offsetY + y0 * scale);
    const dw = Math.round((x1 - x0) * scale);
    const dh = Math.round((y1 - y0) * scale);

    const color = item.color || '#22C55E';

    ctx.save();
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
    ctx.strokeRect(dx, dy, dw, dh);

    // Label tag di atas bounding box
    const labelText = item.label || '';
    ctx.font = 'bold 11.5px "JetBrains Mono", monospace, sans-serif';
    const textWidth = ctx.measureText(labelText).width;
    const badgeW = Math.max(textWidth + 14, 74);
    const badgeH = 22;
    const badgeY = Math.max(0, dy - badgeH);

    ctx.fillStyle = color;
    ctx.fillRect(dx, badgeY, Math.min(dw, badgeW), badgeH);

    ctx.fillStyle = '#FFFFFF';
    ctx.shadowBlur = 0;
    ctx.fillText(labelText, dx + 7, badgeY + 15);
    ctx.restore();
  });
}

function drawStandingHumanSilhouette(ctx, cw, ch, options) {
  const alertMode = Boolean(options.alertMismatch);
  const matchedMode = Boolean(options.faceMatched);

  const mainColor = alertMode
    ? 'rgba(239, 68, 68, 0.95)'
    : (matchedMode ? 'rgba(34, 197, 94, 0.85)' : 'rgba(56, 189, 248, 0.70)');

  const glowColor = alertMode
    ? 'rgba(239, 68, 68, 0.35)'
    : (matchedMode ? 'rgba(34, 197, 94, 0.28)' : 'rgba(56, 189, 248, 0.18)');

  const cx = Math.round(cw * 0.5);
  const topY = Math.round(ch * 0.05);
  const botY = Math.round(ch * 0.95);
  const H = botY - topY;
  // Proporsi lebar tubuh manusia berdiri (rasio lebar bahu thd tinggi total ~ 1 : 2.5)
  const W = Math.round(Math.min(cw * 0.44, H * 0.38));

  // Tingkat koordinat Y vertikal anatomi manusia
  const yHelmTop = topY + Math.round(H * 0.01);
  const yHeadCenter = topY + Math.round(H * 0.085);
  const yChin = topY + Math.round(H * 0.165);
  const yNeck = topY + Math.round(H * 0.195);
  const yShoulder = topY + Math.round(H * 0.235);
  const yChest = topY + Math.round(H * 0.33);
  const yWaist = topY + Math.round(H * 0.49);
  const yCrotch = topY + Math.round(H * 0.56);
  const yKnee = topY + Math.round(H * 0.71);
  const yAnkle = topY + Math.round(H * 0.85);
  const yFeet = botY - Math.round(H * 0.01);

  // Lebar masing-masing bagian tubuh
  const rHead = Math.round(W * 0.20);
  const wBrim = Math.round(W * 0.52);
  const wNeck = Math.round(W * 0.20);
  const wShoulder = Math.round(W * 0.92);
  const wChest = Math.round(W * 0.80);
  const wWaist = Math.round(W * 0.66);
  const wHips = Math.round(W * 0.74);
  const wKnee = Math.round(W * 0.23);
  const wAnkle = Math.round(W * 0.20);

  ctx.save();
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  // ── A. SILUET LUAR KORIDOR KANVAS (CORNER BRACKETS TEGAS) ──
  const corridorW = Math.round(W * 1.25);
  const corridorX = cx - Math.round(corridorW * 0.5);
  const bLen = 20;

  ctx.strokeStyle = alertMode ? '#EF4444' : (matchedMode ? '#22C55E' : 'rgba(56, 189, 248, 0.45)');
  ctx.lineWidth = 2.5;
  // Siku Kiri Atas
  ctx.beginPath(); ctx.moveTo(corridorX, topY + bLen); ctx.lineTo(corridorX, topY); ctx.lineTo(corridorX + bLen, topY); ctx.stroke();
  // Siku Kanan Atas
  ctx.beginPath(); ctx.moveTo(corridorX + corridorW - bLen, topY); ctx.lineTo(corridorX + corridorW, topY); ctx.lineTo(corridorX + corridorW, topY + bLen); ctx.stroke();
  // Siku Kiri Bawah
  ctx.beginPath(); ctx.moveTo(corridorX, botY - bLen); ctx.lineTo(corridorX, botY); ctx.lineTo(corridorX + bLen, botY); ctx.stroke();
  // Siku Kanan Bawah
  ctx.beginPath(); ctx.moveTo(corridorX + corridorW - bLen, botY); ctx.lineTo(corridorX + corridorW, botY); ctx.lineTo(corridorX + corridorW, botY - bLen); ctx.stroke();

  // ── B. GAMBAR KONTUR BADAN MANUSIA BERDIRI (STANDING HUMAN WIREFRAME) ──
  ctx.strokeStyle = mainColor;
  ctx.shadowColor = glowColor;
  ctx.shadowBlur = 10;
  ctx.lineWidth = 2.5;

  // 1. ZONA HELM K3 & WAJAH (Head, Safety Helmet Dome, Visor & Chin)
  // Kubah Helm K3
  ctx.beginPath();
  ctx.arc(cx, yHeadCenter - 2, Math.round(rHead * 1.15), Math.PI, 0, false);
  ctx.stroke();

  // Pinggiran Helm K3 (Helmet Brim Visor Line)
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wBrim * 0.5), yHeadCenter + Math.round(rHead * 0.1));
  ctx.quadraticCurveTo(cx, yHeadCenter - 4, cx + Math.round(wBrim * 0.5), yHeadCenter + Math.round(rHead * 0.1));
  ctx.stroke();

  // Garis Tulang Helm (Crest Ridge)
  ctx.beginPath();
  ctx.moveTo(cx, yHelmTop);
  ctx.lineTo(cx, yHeadCenter - Math.round(rHead * 0.4));
  ctx.stroke();

  // Garis Rahang & Dagu Wajah
  ctx.beginPath();
  ctx.moveTo(cx - rHead, yHeadCenter + Math.round(rHead * 0.1));
  ctx.lineTo(cx - Math.round(rHead * 0.75), yChin);
  ctx.lineTo(cx + Math.round(rHead * 0.75), yChin);
  ctx.lineTo(cx + rHead, yHeadCenter + Math.round(rHead * 0.1));
  ctx.stroke();

  // Crosshair Penempatan Wajah
  ctx.setLineDash([4, 4]);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx - 12, yHeadCenter + 4); ctx.lineTo(cx + 12, yHeadCenter + 4);
  ctx.moveTo(cx, yHeadCenter - 8); ctx.lineTo(cx, yHeadCenter + 16);
  ctx.stroke();
  ctx.setLineDash([]);

  // 2. ZONA LEHER & BAHU
  ctx.lineWidth = 2.5;
  // Leher Kiri & Bahu Kiri
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wNeck * 0.5), yChin);
  ctx.lineTo(cx - Math.round(wNeck * 0.5), yNeck);
  ctx.lineTo(cx - Math.round(wShoulder * 0.5), yShoulder);
  ctx.stroke();

  // Leher Kanan & Bahu Kanan
  ctx.beginPath();
  ctx.moveTo(cx + Math.round(wNeck * 0.5), yChin);
  ctx.lineTo(cx + Math.round(wNeck * 0.5), yNeck);
  ctx.lineTo(cx + Math.round(wShoulder * 0.5), yShoulder);
  ctx.stroke();

  // 3. ZONA BADAN / WEARPACK / KEMEJA
  // Sisi Badan & Lengan Kiri
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wShoulder * 0.5), yShoulder);
  ctx.lineTo(cx - Math.round(wShoulder * 0.52), yChest);
  ctx.lineTo(cx - Math.round(wWaist * 0.5), yWaist);
  ctx.stroke();

  // Sisi Badan & Lengan Kanan
  ctx.beginPath();
  ctx.moveTo(cx + Math.round(wShoulder * 0.5), yShoulder);
  ctx.lineTo(cx + Math.round(wShoulder * 0.52), yChest);
  ctx.lineTo(cx + Math.round(wWaist * 0.5), yWaist);
  ctx.stroke();

  // Kerah V Kemeja & Resleting / Kancing Tengah
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wNeck * 0.4), yNeck);
  ctx.lineTo(cx, yNeck + Math.round(H * 0.05));
  ctx.lineTo(cx + Math.round(wNeck * 0.4), yNeck);
  ctx.moveTo(cx, yNeck + Math.round(H * 0.05));
  ctx.lineTo(cx, yWaist);
  ctx.stroke();

  // Saku Kemeja Kiri & Kanan
  const pSize = Math.round(W * 0.12);
  ctx.setLineDash([3, 3]);
  ctx.strokeRect(cx - Math.round(wChest * 0.38), yChest - Math.round(pSize * 0.5), pSize, pSize);
  ctx.strokeRect(cx + Math.round(wChest * 0.38) - pSize, yChest - Math.round(pSize * 0.5), pSize, pSize);
  ctx.setLineDash([]);

  // 4. ZONA PINGGANG & CELANA JEANS
  // Garis Ikat Pinggang
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wWaist * 0.5), yWaist);
  ctx.lineTo(cx + Math.round(wWaist * 0.5), yWaist);
  ctx.stroke();

  // Kaki Luar Kiri
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wWaist * 0.5), yWaist);
  ctx.lineTo(cx - Math.round(wHips * 0.48), yWaist + Math.round(H * 0.06));
  ctx.lineTo(cx - Math.round(wHips * 0.42), yKnee);
  ctx.lineTo(cx - Math.round(wHips * 0.38), yAnkle);
  ctx.stroke();

  // Kaki Luar Kanan
  ctx.beginPath();
  ctx.moveTo(cx + Math.round(wWaist * 0.5), yWaist);
  ctx.lineTo(cx + Math.round(wHips * 0.48), yWaist + Math.round(H * 0.06));
  ctx.lineTo(cx + Math.round(wHips * 0.42), yKnee);
  ctx.lineTo(cx + Math.round(wHips * 0.38), yAnkle);
  ctx.stroke();

  // Pangkal Paha & Selangkangan (Inseam)
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(W * 0.08), yAnkle);
  ctx.lineTo(cx - Math.round(W * 0.08), yKnee);
  ctx.lineTo(cx, yCrotch);
  ctx.lineTo(cx + Math.round(W * 0.08), yKnee);
  ctx.lineTo(cx + Math.round(W * 0.08), yAnkle);
  ctx.stroke();

  // Garis Lutut
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wHips * 0.40), yKnee); ctx.lineTo(cx - Math.round(W * 0.10), yKnee);
  ctx.moveTo(cx + Math.round(W * 0.10), yKnee); ctx.lineTo(cx + Math.round(wHips * 0.40), yKnee);
  ctx.stroke();
  ctx.setLineDash([]);

  // 5. ZONA SEPATU SAFETY
  // Sepatu Kiri (Safety Boot Outline)
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wHips * 0.38), yAnkle);
  ctx.lineTo(cx - Math.round(wHips * 0.48), yFeet);
  ctx.lineTo(cx - Math.round(W * 0.06), yFeet);
  ctx.lineTo(cx - Math.round(W * 0.08), yAnkle);
  ctx.stroke();

  // Sepatu Kanan (Safety Boot Outline)
  ctx.beginPath();
  ctx.moveTo(cx + Math.round(wHips * 0.38), yAnkle);
  ctx.lineTo(cx + Math.round(wHips * 0.48), yFeet);
  ctx.lineTo(cx + Math.round(W * 0.06), yFeet);
  ctx.lineTo(cx + Math.round(W * 0.08), yAnkle);
  ctx.stroke();

  // Garis Sol Sepatu
  ctx.lineWidth = 3.5;
  ctx.beginPath();
  ctx.moveTo(cx - Math.round(wHips * 0.48), yFeet); ctx.lineTo(cx - Math.round(W * 0.06), yFeet);
  ctx.moveTo(cx + Math.round(W * 0.06), yFeet); ctx.lineTo(cx + Math.round(wHips * 0.48), yFeet);
  ctx.stroke();

  // ── C. HUD BADGES PENANDA MASING-MASING APD (LABELED ANATOMICAL ZONES) ──
  ctx.shadowBlur = 0;
  ctx.font = 'bold 9.5px "JetBrains Mono", monospace, sans-serif';

  function renderHudBadge(label, badgeX, badgeY, isWorn) {
    const textW = ctx.measureText(label).width;
    const bW = textW + 12;
    const bH = 16;
    ctx.fillStyle = isWorn ? 'rgba(16, 185, 129, 0.90)' : (alertMode ? 'rgba(239, 68, 68, 0.88)' : 'rgba(15, 23, 42, 0.82)');
    ctx.fillRect(badgeX - Math.round(bW * 0.5), badgeY, bW, bH);
    ctx.strokeStyle = isWorn ? '#34D399' : (alertMode ? '#EF4444' : 'rgba(56, 189, 248, 0.6)');
    ctx.lineWidth = 1;
    ctx.strokeRect(badgeX - Math.round(bW * 0.5), badgeY, bW, bH);
    ctx.fillStyle = '#FFFFFF';
    ctx.fillText(label, badgeX - Math.round(bW * 0.5) + 6, badgeY + 11.5);
  }

  const apdRes = options.apdResult || {};
  renderHudBadge(
    options.multiPerson ? 'WAJAH & HELM (ORANG LAIN DIABAIKAN)' : '🪖 HELM & WAJAH',
    cx,
    topY - 14,
    apdRes.helm?.worn || matchedMode
  );

  renderHudBadge(
    '👔 KEMEJA / BAJU',
    corridorX + corridorW + 2,
    yChest - 8,
    apdRes.baju?.worn
  );

  renderHudBadge(
    '👖 CELANA JEANS',
    corridorX - 2,
    yKnee - 8,
    apdRes.jeans?.worn
  );

  renderHudBadge(
    '👞 SEPATU SAFETY',
    cx,
    botY + 3,
    apdRes.sepatu?.worn
  );

  ctx.restore();
}

// ── KIOSK MONITORING HEARTBEAT & LIVE SNAPSHOT STREAM ──
function initKioskHeartbeat() {
  async function sendHeartbeat() {
    const video = document.getElementById('kioskVideo');
    let snapshotBase64 = null;
    let cameraStatus = 'standby';

    if (video && video.videoWidth > 0 && !video.paused && !video.ended) {
      cameraStatus = 'aktif';
      try {
        const offCanvas = document.createElement('canvas');
        offCanvas.width = 360;
        offCanvas.height = 270;
        const offCtx = offCanvas.getContext('2d');
        offCtx.drawImage(video, 0, 0, offCanvas.width, offCanvas.height);
        snapshotBase64 = offCanvas.toDataURL('image/jpeg', 0.55);
      } catch (e) {
        // canvas cors / drawing error ignored
      }
    }

    let aktivitas = 'Siaga mendeteksi';
    if (kioskState.activeStudent) {
      aktivitas = `Presensi: ${kioskState.activeStudent.nama}`;
    }

    try {
      const res = await fetch('/api/kiosk/heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kode: 'KSK-AE-01',
          nama: 'PC Kiosk Jurusan AE',
          lokasi: 'Laboratorium AE',
          status_kamera: cameraStatus,
          aktivitas: aktivitas,
          frame_snapshot: snapshotBase64
        })
      });
      if (res.ok) {
        // Heartbeat terkirim sukses
      }
    } catch (err) {
      console.warn('Heartbeat kiosk gagal dikirim:', err);
    }
  }

  // Kirim heartbeat pertama segera dan ulangi tiap 3 detik
  setTimeout(sendHeartbeat, 500);
  setInterval(sendHeartbeat, 3000);
}

// ── KIOSK DEVICE LOGOUT ──
async function logoutKioskDevice(event) {
  if (event && event.preventDefault) event.preventDefault();
  stopKioskCamera();
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (_) {}
  window.location.href = '/login.html';
}
window.logoutKioskDevice = logoutKioskDevice;

document.addEventListener('DOMContentLoaded', initKioskHeartbeat);
