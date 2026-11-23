const KIOSK_APD_SCAN_FRAME_COUNT = 8;
const KIOSK_APD_SCAN_INTERVAL_MS = 150;
const KIOSK_FACE_PROBABILITY_WINDOW = 4;
const KIOSK_FACE_VERIFY_DURATION_MS = 1500;
const KIOSK_FACE_SCAN_INTERVAL_MS = 100;
const KIOSK_FACE_MAX_ATTEMPTS = 24;

const kioskState = {
  student: null,
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
  step: 1,
  busy: false
};

const kioskApdItems = {
  helm: { element: 'tagHelm', label: 'Helm' },
  baju: { element: 'tagWearpack', label: 'Baju praktik' },
  jeans: { element: 'tagCelana', label: 'Celana jeans' },
  sepatu: { element: 'tagSepatu', label: 'Sepatu safety' }
};

document.addEventListener('DOMContentLoaded', initKiosk);
window.addEventListener('pagehide', stopKioskCamera);

async function initKiosk() {
  const button = document.getElementById('btnKioskAction');
  button.addEventListener('click', handleKioskAction);
  document.getElementById('btnKioskApdRetry').addEventListener('click', retryAPDInspection);
  document.getElementById('kioskIdentityForm').addEventListener('submit', handleKioskIdentitySubmit);
  document.getElementById('btnKioskIdentityReset').addEventListener('click', resetKioskIdentity);
  const cameraSelect = document.getElementById('kioskCamera');
  cameraSelect.addEventListener('change', handleKioskCameraChange);
  button.disabled = true;
  await loadKioskCameras();
  populateKioskSessions([]);
}

async function handleKioskIdentitySubmit(event) {
  event.preventDefault();
  if (kioskState.busy) return;

  const submitButton = document.getElementById('btnKioskIdentitySubmit');
  const message = document.getElementById('kioskIdentityMessage');
  const identity = {
    nama: document.getElementById('kioskInputName').value.trim(),
    nim: document.getElementById('kioskInputNim').value.trim(),
    kelas: document.getElementById('kioskInputClass').value.trim()
  };
  submitButton.disabled = true;
  message.textContent = 'Memeriksa identitas mahasiswa...';

  try {
    const response = await fetch('/api/kiosk/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(identity)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Identitas mahasiswa gagal diverifikasi.');

    kioskState.student = result.student;
    kioskState.sessions = result.sessions;
    ['kioskInputName', 'kioskInputNim', 'kioskInputClass'].forEach(id => {
      document.getElementById(id).disabled = true;
    });
    document.getElementById('btnKioskIdentitySubmit').hidden = true;
    document.getElementById('btnKioskIdentityReset').hidden = false;
    document.getElementById('kioskStudentStatus').textContent = 'Identitas terdaftar';
    message.textContent = `Identitas cocok. Sesi ditampilkan untuk kelas ${result.student.kelas}.`;
    populateKioskSessions(result.sessions);
  } catch (error) {
    kioskState.student = null;
    kioskState.sessions = [];
    message.textContent = error.message;
    populateKioskSessions([]);
  } finally {
    submitButton.disabled = false;
  }
}

function resetKioskIdentity() {
  if (kioskState.busy || kioskState.step !== 1) return;
  kioskState.student = null;
  kioskState.sessions = [];
  kioskState.sessionId = null;
  kioskState.faceVerified = false;
  kioskState.faceImages = [];
  kioskState.apdImages = null;
  kioskState.apd = null;
  stopKioskCamera();
  ['kioskInputName', 'kioskInputNim', 'kioskInputClass'].forEach(id => {
    document.getElementById(id).disabled = false;
  });
  document.getElementById('kioskIdentityForm').reset();
  document.getElementById('btnKioskIdentitySubmit').hidden = false;
  document.getElementById('btnKioskIdentityReset').hidden = true;
  document.getElementById('kioskStudentStatus').textContent = 'Kiosk siap';
  document.getElementById('kioskIdentityMessage').textContent =
    'Masukkan nama, NIM, dan kelas sesuai data mahasiswa.';
  document.getElementById('btnKioskAction').textContent = 'Mulai Verifikasi Wajah';
  document.getElementById('btnKioskAction').disabled = true;
  document.getElementById('btnKioskApdRetry').hidden = true;
  populateKioskSessions([]);
  setKioskStatus('Menunggu kamera', 'Klik tombol di bawah untuk memulai.', false);
}

async function loadKioskCameras() {
  const select = document.getElementById('kioskCamera');
  const message = document.getElementById('kioskCameraMessage');
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    kioskState.cameraSelectionAvailable = false;
    select.replaceChildren(new Option('Pemilihan kamera tidak tersedia', ''));
    select.disabled = true;
    message.textContent = 'Browser tidak dapat menampilkan daftar kamera. Kamera browser akan digunakan.';
    return;
  }

  try {
    const cameras = (await navigator.mediaDevices.enumerateDevices())
      .filter(device => device.kind === 'videoinput');
    const selectedId = kioskState.cameraDeviceId;
    select.replaceChildren();
    cameras.forEach((camera, index) => {
      select.add(new Option(camera.label || `Kamera ${index + 1}`, camera.deviceId));
    });

    if (cameras.length === 0) {
      select.add(new Option('Kamera browser (otomatis)', ''));
      kioskState.cameraDeviceId = null;
      kioskState.cameraSelectionAvailable = false;
      select.disabled = true;
      message.textContent = 'Daftar kamera belum tersedia. Browser akan memilih kamera secara otomatis.';
      return;
    }

    kioskState.cameraSelectionAvailable = true;
    const selectedCameraExists = cameras.some(camera => camera.deviceId === selectedId);
    kioskState.cameraDeviceId = selectedCameraExists ? selectedId : cameras[0].deviceId;
    select.value = kioskState.cameraDeviceId;
    select.disabled = kioskState.busy || kioskState.cameraSwitching;
    message.textContent = cameras.length === 1
      ? '1 kamera terdeteksi.'
      : `${cameras.length} kamera terdeteksi. Pilih kamera yang ingin digunakan.`;
  } catch (error) {
    kioskState.cameraSelectionAvailable = false;
    select.replaceChildren(new Option('Kamera browser (otomatis)', ''));
    select.disabled = true;
    message.textContent = `Daftar kamera gagal dimuat: ${error.message}`;
  }
}

async function handleKioskCameraChange() {
  const select = document.getElementById('kioskCamera');
  const previousCameraId = kioskState.cameraDeviceId;
  const selectedCameraId = select.value || null;
  if (selectedCameraId === previousCameraId || kioskState.busy || kioskState.cameraSwitching) return;

  kioskState.cameraDeviceId = selectedCameraId;
  if (!kioskState.stream) return;

  kioskState.cameraSwitching = true;
  select.disabled = true;
  stopKioskCamera();
  try {
    await ensureKioskCamera();
  } catch (error) {
    kioskState.cameraDeviceId = previousCameraId;
    select.value = previousCameraId || '';
    try {
      await ensureKioskCamera();
      setKioskStatus('Kamera gagal diganti', `${error.message} Kamera sebelumnya digunakan kembali.`, true);
    } catch (restoreError) {
      setKioskStatus('Kamera gagal dibuka', `${error.message} Pemulihan kamera juga gagal: ${restoreError.message}`, true);
    }
  } finally {
    kioskState.cameraSwitching = false;
    select.disabled = kioskState.busy || !kioskState.cameraSelectionAvailable;
  }
}

function populateKioskSessions(sessions) {
  const select = document.getElementById('kioskSession');
  const message = document.getElementById('kioskSessionMessage');
  select.replaceChildren(new Option('Pilih sesi praktikum', ''));
  sessions.forEach(item => {
    const label = `${item.mata_kuliah} · ${item.lab} · ${item.tanggal} (${item.jam_mulai}–${item.jam_selesai})`;
    select.add(new Option(label, String(item.id)));
  });
  select.disabled = !kioskState.student || sessions.length === 0;
  kioskState.sessionId = null;
  document.getElementById('btnKioskAction').disabled = true;
  message.textContent = sessions.length
    ? 'Pilih sesi aktif yang akan diikuti.'
    : kioskState.student
      ? 'Belum ada sesi aktif untuk kelas Anda.'
      : 'Sesi akan ditampilkan setelah identitas diverifikasi.';
  select.onchange = () => {
    kioskState.sessionId = select.value ? Number(select.value) : null;
    document.getElementById('btnKioskAction').disabled =
      !kioskState.student || !kioskState.sessionId || kioskState.busy;
  };
}

function setKioskStatus(title, detail, isError) {
  const heading = document.getElementById('camStatusHeader');
  heading.textContent = title;
  heading.style.color = isError ? '#FCA5A5' : '#FFFFFF';
  document.getElementById('camStatusDetail').textContent = detail;
}

function setCameraStatus(active, detail) {
  document.getElementById('camStatusPill').classList.toggle('active', active);
  document.getElementById('camStatusDot').style.background = active ? '#10B981' : '#94A3B8';
  document.getElementById('camStatusText').textContent = active ? 'CAMERA ACTIVE' : 'CAMERA OFF';
  if (!active) setKioskStatus('Menunggu kamera', detail, false);
}

async function ensureKioskCamera() {
  if (kioskState.stream) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('Browser tidak mendukung akses kamera. Buka aplikasi melalui localhost atau HTTPS.');
  }
  const videoConstraints = kioskState.cameraDeviceId
    ? { deviceId: { exact: kioskState.cameraDeviceId } }
    : { facingMode: { ideal: 'user' } };
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { ...videoConstraints, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false
  });
  const video = document.getElementById('kioskVideo');
  try {
    video.srcObject = stream;
    video.style.display = 'block';
    await new Promise((resolve, reject) => {
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        resolve();
        return;
      }
      const timeout = setTimeout(() => reject(new Error('Kamera tidak mengirimkan gambar.')), 10000);
      video.addEventListener('loadeddata', () => {
        clearTimeout(timeout);
        resolve();
      }, { once: true });
      video.addEventListener('error', () => {
        clearTimeout(timeout);
        reject(new Error('Gagal membaca video kamera.'));
      }, { once: true });
    });
    await video.play();
    kioskState.stream = stream;
    await loadKioskCameras();
    setCameraStatus(true, '');
  } catch (error) {
    stream.getTracks().forEach(track => track.stop());
    video.srcObject = null;
    video.style.display = 'none';
    throw error;
  }
}

function stopKioskCamera() {
  if (!kioskState.stream) return;
  kioskState.stream.getTracks().forEach(track => track.stop());
  kioskState.stream = null;
  const video = document.getElementById('kioskVideo');
  if (video) {
    video.srcObject = null;
    video.style.display = 'none';
  }
}

function captureKioskFrame() {
  const video = document.getElementById('kioskVideo');
  if (!video.videoWidth || !video.videoHeight) {
    throw new Error('Kamera belum siap mengambil gambar.');
  }
  const scale = Math.min(1, 1280 / video.videoWidth, 720 / video.videoHeight);
  const canvas = document.getElementById('kioskCanvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.78);
}

async function postKioskScan(phase, image, sessionId, cropMode) {
  const payload = { ...kioskState.student, phase, sesi_id: sessionId };
  if (phase === 'apd') {
    payload.images = image;
  } else {
    payload.image = image;
    payload.crop_mode = cropMode;
  }
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
  const button = document.getElementById('btnKioskAction');
  button.disabled = busy || !kioskState.student || !kioskState.sessionId;
  document.getElementById('btnKioskIdentityReset').disabled =
    busy || kioskState.step !== 1;
  document.getElementById('kioskCamera').disabled =
    busy || kioskState.cameraSwitching || kioskState.step === 3 ||
    !kioskState.cameraSelectionAvailable;
  document.getElementById('kioskFaceCropMode').disabled = kioskState.step !== 1;
  if (label) button.textContent = label;
}

async function handleKioskAction() {
  if (kioskState.busy) return;
  if (!kioskState.sessionId) {
    setKioskStatus('Pilih sesi praktikum', 'Pilih sesi aktif sebelum memulai pemindaian.', true);
    return;
  }
  if (kioskState.step === 1) {
    await startFaceVerification();
  } else if (kioskState.step === 2) {
    await startAPDInspection();
  } else if (kioskState.step === 3) {
    await finishKioskAttendance();
  }
}

async function startFaceVerification() {
  setKioskBusy(true, 'Memulai kamera...');
  try {
    await ensureKioskCamera();
    const laser = document.getElementById('scanLaser');
    laser.style.display = 'block';
    laser.style.animation = 'kioskLaserAnimation 1.8s infinite ease-in-out';
    let cropMode = document.getElementById('kioskFaceCropMode').value;
    kioskState.faceCropMode = cropMode;
    const probabilityHistory = [];
    const studentTokens = new Set(
      String(kioskState.student.nama).toLowerCase().match(/[a-z0-9]+/g) || []
    );
    let stableLabel = null;
    let stableSince = null;
    let verified = false;

    kioskState.faceImages = [];
    for (let attempt = 0; attempt < KIOSK_FACE_MAX_ATTEMPTS && !verified; attempt += 1) {
      const selectedCropMode = document.getElementById('kioskFaceCropMode').value;
      if (selectedCropMode !== cropMode) {
        cropMode = selectedCropMode;
        kioskState.faceCropMode = cropMode;
        probabilityHistory.length = 0;
        kioskState.faceImages = [];
        stableLabel = null;
        stableSince = null;
      }
      setKioskStatus(
        'Memverifikasi wajah...',
        cropMode === 'hog'
          ? 'Posisikan wajah menghadap kamera. Jika tidak terbaca, coba kotak panduan tengah.'
          : 'Posisikan wajah di dalam kotak panduan tengah.',
        false
      );
      const image = captureKioskFrame();
      const result = await postKioskScan('wajah', image, null, cropMode);
      const face = result.face;
      if (!face.detected) {
        probabilityHistory.length = 0;
        kioskState.faceImages = [];
        stableLabel = null;
        stableSince = null;
        setKioskStatus(
          'Wajah tidak terdeteksi',
          cropMode === 'hog'
            ? 'Perbaiki pencahayaan/posisi atau pilih mode kotak panduan tengah.'
            : 'Posisikan wajah tepat di dalam kotak panduan.',
          true
        );
      } else {
        if (
          !Array.isArray(face.classes) ||
          !Array.isArray(face.probabilities) ||
          face.classes.length === 0 ||
          face.classes.length !== face.probabilities.length
        ) {
          throw new Error('Probabilitas model wajah tidak valid.');
        }
        probabilityHistory.push(face.probabilities);
        if (probabilityHistory.length > KIOSK_FACE_PROBABILITY_WINDOW) {
          probabilityHistory.shift();
        }
        kioskState.faceImages.push(image);
        if (kioskState.faceImages.length > KIOSK_FACE_PROBABILITY_WINDOW) {
          kioskState.faceImages.shift();
        }

        const averageProbabilities = face.classes.map((_, classIndex) =>
          probabilityHistory.reduce((total, sample) => total + sample[classIndex], 0) /
          probabilityHistory.length
        );
        const bestIndex = averageProbabilities.reduce(
          (best, probability, index) =>
            probability > averageProbabilities[best] ? index : best,
          0
        );
        const label = face.classes[bestIndex];
        const confidence = averageProbabilities[bestIndex];
        const matchesStudent = studentTokens.has(label.toLowerCase());
        if (confidence >= face.threshold && matchesStudent) {
          if (stableLabel !== label) {
            stableLabel = label;
            stableSince = Date.now();
          }
          const elapsed = Date.now() - stableSince;
          setKioskStatus(
            `Wajah dikenali: ${label} (${Math.round(confidence * 100)}%)`,
            `Memastikan identitas stabil ${(Math.min(elapsed, KIOSK_FACE_VERIFY_DURATION_MS) / 1000).toFixed(1)}/1,5 dtk...`,
            false
          );
          verified = elapsed >= KIOSK_FACE_VERIFY_DURATION_MS;
        } else {
          stableLabel = null;
          stableSince = null;
          setKioskStatus(
            'Identitas belum terverifikasi',
            matchesStudent
              ? `Rata-rata keyakinan ${Math.round(confidence * 100)}% belum mencapai ${Math.round(face.threshold * 100)}%.`
              : `Wajah ${label} tidak cocok dengan akun ini.`,
            true
          );
        }
      }
      if (!verified && attempt + 1 < KIOSK_FACE_MAX_ATTEMPTS) {
        await new Promise(resolve => setTimeout(resolve, KIOSK_FACE_SCAN_INTERVAL_MS));
      }
    }
    laser.style.display = 'none';
    if (!verified) {
      throw new Error('Wajah belum terverifikasi selama 1,5 detik. Atur posisi atau mode crop lalu coba lagi.');
    }
    kioskState.faceVerified = true;
    document.getElementById('kioskSession').disabled = true;
    document.getElementById('faceSilhouette').classList.add('matched');
    setKioskStatus('Identitas terverifikasi', 'Silakan lanjut ke pemeriksaan APD.', false);
    document.getElementById('stepMainTitle').textContent = 'APD Inspection';
    document.getElementById('stepSubTitle').textContent = 'Pemeriksaan kelengkapan keselamatan K3';
    document.getElementById('stepPillBadge').textContent = 'Step 2 of 2';
    document.getElementById('kioskEyebrow').textContent = 'SAFETY COMPLIANCE';
    document.getElementById('kioskPageTitle').textContent = 'Pemeriksaan Kelengkapan APD K3';
    document.getElementById('kioskPageDesc').textContent = 'Berdirilah tegak agar bagian kepala hingga kaki terlihat di kamera.';
    document.getElementById('viewportEyebrow').textContent = 'FULL BODY INSPECTION';
    document.getElementById('viewportTitle').textContent = 'Deteksi Visual APD';
    document.getElementById('step1ViewElements').style.display = 'none';
    document.getElementById('step2ViewElements').style.display = 'flex';
    kioskState.step = 2;
    setKioskBusy(false, 'Mulai Pemindaian APD');
  } catch (error) {
    kioskState.faceImages = [];
    document.getElementById('scanLaser').style.display = 'none';
    setKioskStatus('Verifikasi wajah gagal', error.message, true);
    setKioskBusy(false, 'Coba Verifikasi Wajah Lagi');
  }
}

function renderKioskApd(results) {
  kioskState.apd = results;
  let requiredMissing = false;
  Object.entries(kioskApdItems).forEach(([key, item]) => {
    const result = results[key];
    const tag = document.getElementById(item.element);
    if (!result.wajib) {
      tag.textContent = `${item.label}: Tidak wajib`;
      tag.classList.remove('not-detected', 'manual-review');
      tag.style.display = 'block';
      return;
    }
    const detected = result.worn;
    if (key !== 'jeans' && !detected) requiredMissing = true;
    tag.classList.toggle('not-detected', !detected && key !== 'jeans');
    tag.classList.toggle('manual-review', result.validasi_manual);
    const score = Math.round(result.probability * 100);
    tag.textContent = result.validasi_manual
      ? `${item.label}: Perlu validasi PLP (AI ${detected ? 'sesuai' : 'tidak sesuai'}, ${score}%)`
      : `${item.label}: ${detected ? 'Terdeteksi' : 'Belum terdeteksi'} (${score}%)`;
    tag.style.display = 'block';
  });
  setKioskStatus(
    requiredMissing ? 'Ada APD belum terdeteksi' : 'Pemindaian APD selesai',
    requiredMissing
      ? 'Hasil akan dicatat dan ditindaklanjuti sesuai aturan APD.'
      : 'Periksa hasil pemindaian, lalu simpan kehadiran.',
    requiredMissing
  );
  const button = document.getElementById('btnKioskAction');
  button.textContent = 'Simpan Kehadiran';
  kioskState.step = 3;
  document.getElementById('btnKioskApdRetry').hidden = false;
}

async function retryAPDInspection() {
  if (kioskState.busy || kioskState.step !== 3) return;

  kioskState.step = 2;
  kioskState.apd = null;
  kioskState.apdImages = null;
  document.getElementById('btnKioskApdRetry').hidden = true;
  Object.values(kioskApdItems).forEach(item => {
    const tag = document.getElementById(item.element);
    tag.textContent = '';
    tag.classList.remove('not-detected', 'manual-review');
    tag.style.display = 'none';
  });
  await startAPDInspection();
}

async function captureKioskApdFrames() {
  const frames = [];
  for (let index = 0; index < KIOSK_APD_SCAN_FRAME_COUNT; index += 1) {
    frames.push(captureKioskFrame());
    if (index + 1 < KIOSK_APD_SCAN_FRAME_COUNT) {
      await new Promise(resolve => setTimeout(resolve, KIOSK_APD_SCAN_INTERVAL_MS));
    }
  }
  return frames;
}

async function startAPDInspection() {
  if (!kioskState.faceVerified) return;
  setKioskBusy(true, 'Siapkan APD...');
  const laser = document.getElementById('scanLaser');
  laser.style.display = 'none';
  document.getElementById('btnKioskApdRetry').hidden = true;
  try {
    for (let seconds = 3; seconds > 0; seconds -= 1) {
      setKioskStatus(
        'Siapkan APD',
        `Pemindaian dimulai dalam ${seconds} detik. Pastikan perlengkapan terlihat di kamera.`,
        false
      );
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    document.getElementById('btnKioskAction').textContent = 'Menganalisis APD...';
    laser.style.display = 'block';
    laser.style.animation = 'kioskLaserAnimation 2.2s infinite ease-in-out';
    kioskState.apdImages = await captureKioskApdFrames();
    const result = await postKioskScan(
      'apd',
      kioskState.apdImages,
      kioskState.sessionId
    );
    renderKioskApd(result.apd);
  } catch (error) {
    setKioskStatus('Pemindaian APD gagal', error.message, true);
    setKioskBusy(false, 'Coba Pemindaian APD Lagi');
    return;
  } finally {
    laser.style.display = 'none';
  }
  setKioskBusy(false, 'Simpan Kehadiran');
}

function attendanceStatusLabel(status) {
  return {
    lengkap: 'Lengkap',
    kurang: 'Tidak lengkap',
    menunggu_validasi: 'Menunggu validasi jeans oleh PLP'
  }[status] || status;
}

async function finishKioskAttendance() {
  if (!kioskState.faceVerified || !kioskState.apd) return;
  setKioskBusy(true, 'Menyimpan kehadiran...');
  try {
    const response = await fetch('/api/kiosk/attendance', {
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
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Kehadiran gagal disimpan.');
    const attendance = result.attendance;
    const time = new Date(attendance.waktu.replace(' ', 'T'));
    document.getElementById('successTime').textContent = Number.isNaN(time.getTime())
      ? attendance.waktu
      : new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' }).format(time);
    document.getElementById('successApdStatus').textContent = attendanceStatusLabel(attendance.status);
    document.getElementById('successSession').textContent = attendance.mata_kuliah;
    document.getElementById('successOverlay').style.display = 'flex';
    setKioskStatus('Kehadiran berhasil disimpan', attendanceStatusLabel(attendance.status), false);
    kioskState.faceImages = [];
    kioskState.apdImages = null;
    stopKioskCamera();
  } catch (error) {
    setKioskStatus('Kehadiran gagal disimpan', error.message, true);
    setKioskBusy(false, 'Coba Simpan Lagi');
  }
}
