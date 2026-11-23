const KIOSK_APD_SCAN_FRAME_COUNT = 8;
const KIOSK_APD_SCAN_INTERVAL_MS = 150;
const KIOSK_APD_VERIFY_DURATION_MS = 5000;
const KIOSK_APD_LIVE_INTERVAL_MS = 160;
const KIOSK_FACE_PROBABILITY_WINDOW = 4;
const KIOSK_FACE_VERIFY_DURATION_MS = 1500;
const KIOSK_FACE_SCAN_INTERVAL_MS = 100;
const KIOSK_FACE_MAX_ATTEMPTS = 300;

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
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }
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
  if (event && event.preventDefault) event.preventDefault();
  if (kioskState.busy) return;

  const submitButton = document.getElementById('btnKioskIdentitySubmit');
  const message = document.getElementById('kioskIdentityMessage');
  const nim = document.getElementById('kioskInputNim').value.trim();
  const password = document.getElementById('kioskInputPassword').value.trim();

  if (!nim || !password) {
    message.textContent = 'NIM dan kata sandi wajib diisi.';
    return;
  }

  submitButton.disabled = true;
  message.textContent = 'Memeriksa identitas mahasiswa...';

  try {
    const response = await fetch('/api/kiosk/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nim, password })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'NIM atau kata sandi tidak sesuai.');

    kioskState.student = result.student;
    kioskState.sessions = result.sessions;

    document.getElementById('kioskInputNim').disabled = true;
    document.getElementById('kioskInputPassword').disabled = true;
    document.getElementById('btnKioskIdentitySubmit').hidden = true;
    document.getElementById('btnKioskIdentityReset').hidden = false;

    // Sembunyikan panel quick select saat sudah login
    const quickSection = document.getElementById('kioskQuickSelectSection');
    if (quickSection) quickSection.style.display = 'none';

    // Tampilkan profil terverifikasi
    const card = document.getElementById('kioskStudentProfileCard');
    if (card) {
      document.getElementById('kioskProfileName').textContent = result.student.nama;
      document.getElementById('kioskProfileDetail').textContent = `NIM: ${result.student.nim} · Kelas: ${result.student.kelas}`;
      card.style.display = 'block';
    }

    document.getElementById('kioskStudentStatus').textContent = 'Identitas terdaftar';
    message.textContent = `Selamat datang, ${result.student.nama}. Sesi aktif ditampilkan.`;
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

function quickSelectStudent(nim) {
  if (kioskState.busy) return;
  const nimInput = document.getElementById('kioskInputNim');
  const passwordInput = document.getElementById('kioskInputPassword');
  if (nimInput && passwordInput) {
    nimInput.value = nim;
    passwordInput.value = 'mahasiswa123';
    handleKioskIdentitySubmit(new Event('submit'));
  }
}
window.quickSelectStudent = quickSelectStudent;

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
  drawDetectionBoxes([]);

  document.getElementById('kioskInputNim').disabled = false;
  document.getElementById('kioskInputPassword').disabled = false;
  document.getElementById('kioskIdentityForm').reset();
  document.getElementById('btnKioskIdentitySubmit').hidden = false;
  document.getElementById('btnKioskIdentityReset').hidden = true;

  const quickSection = document.getElementById('kioskQuickSelectSection');
  if (quickSection) quickSection.style.display = 'block';

  const card = document.getElementById('kioskStudentProfileCard');
  if (card) card.style.display = 'none';

  document.getElementById('kioskStudentStatus').textContent = 'Kiosk siap';
  document.getElementById('kioskIdentityMessage').textContent = 'Masukkan NIM dan kata sandi Anda.';
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

  if (sessions.length > 0) {
    // Otomatis pilih sesi aktif yang ada agar tombol verifikasi langsung siap
    select.value = String(sessions[0].id);
    kioskState.sessionId = sessions[0].id;
    document.getElementById('btnKioskAction').disabled = !kioskState.student || kioskState.busy;
    message.textContent = `Sesi aktif otomatis terpilih: ${sessions[0].mata_kuliah} (${sessions[0].lab})`;
  } else {
    kioskState.sessionId = null;
    document.getElementById('btnKioskAction').disabled = true;
    message.textContent = kioskState.student
      ? 'Belum ada sesi aktif untuk kelas Anda.'
      : 'Sesi akan ditampilkan setelah identitas diverifikasi.';
  }

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
  drawDetectionBoxes([]);
}

function drawDetectionBoxes(boxes) {
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

  if (!boxes || boxes.length === 0) return;

  boxes.forEach(item => {
    if (!item.box || item.box.length !== 4) return;
    const [x0, y0, x1, y1] = item.box;
    const [origW, origH] = item.dimensions || [640, 480];

    // Skala dengan mempertimbangkan object-fit cover
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

    // Kotak deteksi objek (garis 3px)
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.strokeRect(dx, dy, dw, dh);

    // Label tag di atas kotak objek
    const labelText = item.label || '';
    ctx.font = 'bold 12px "JetBrains Mono", monospace, sans-serif';
    const textWidth = ctx.measureText(labelText).width;
    const badgeW = Math.max(textWidth + 14, 70);
    const badgeH = 22;
    const badgeY = Math.max(0, dy - badgeH);

    ctx.fillStyle = color;
    ctx.fillRect(dx, badgeY, Math.min(dw, badgeW), badgeH);

    ctx.fillStyle = '#0F172A';
    ctx.fillText(labelText, dx + 6, badgeY + 15);
  });
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

async function postKioskScan(phase, image, sessionId, cropMode, prevEma, prevDetected) {
  const payload = { ...kioskState.student, phase, sesi_id: sessionId };
  if (phase === 'apd' && Array.isArray(image)) {
    payload.images = image;
  } else {
    payload.image = image;
    payload.crop_mode = cropMode;
    if (prevEma) payload.previous_ema = prevEma;
    if (prevDetected) payload.previous_detected = prevDetected;
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
      const guideTitle = document.getElementById('guideTitle');

      if (!face.detected) {
        probabilityHistory.length = 0;
        kioskState.faceImages = [];
        stableLabel = null;
        stableSince = null;
        drawDetectionBoxes([]);
        if (guideTitle) guideTitle.style.display = 'block';
        setKioskStatus(
          'Mencari wajah...',
          cropMode === 'hog'
            ? 'Posisikan wajah menghadap kamera.'
            : 'Posisikan wajah di dalam kotak panduan tengah.',
          false
        );
      } else {
        if (guideTitle) guideTitle.style.display = 'none';
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
        const targetLabel = label.toLowerCase();
        const matchesStudent = Array.from(studentTokens).some(
          token => token.includes(targetLabel) || targetLabel.includes(token)
        );

        // Gambar kotak deteksi objek wajah secara dinamis mengikuti pergerakan mahasiswa
        if (face.box) {
          drawDetectionBoxes([{
            box: face.box,
            dimensions: face.dimensions,
            label: `${label} ${Math.round(confidence * 100)}%`,
            color: (confidence >= face.threshold && matchesStudent) ? '#10B981' : '#F59E0B'
          }]);
        }

        if (confidence >= face.threshold && matchesStudent) {
          if (stableLabel !== label) {
            stableLabel = label;
            stableSince = Date.now();
          }
          const elapsed = Date.now() - stableSince;
          const remainingSec = Math.max(0, (KIOSK_FACE_VERIFY_DURATION_MS - elapsed) / 1000).toFixed(1);
          setKioskStatus(
            `Wajah Terdeteksi: ${label} (${Math.round(confidence * 100)}%)`,
            `Tahan posisi wajah ${remainingSec} dtk lagi...`,
            false
          );
          verified = elapsed >= KIOSK_FACE_VERIFY_DURATION_MS;
        } else {
          stableLabel = null;
          stableSince = null;
          setKioskStatus(
            'Menyesuaikan wajah...',
            matchesStudent
              ? `Tingkat kecocokan ${Math.round(confidence * 100)}% (butuh >= ${Math.round(face.threshold * 100)}%).`
              : `Wajah ${label} tidak cocok dengan akun mahasiswa ini.`,
            !matchesStudent
          );
        }
      }
      if (!verified && attempt + 1 < KIOSK_FACE_MAX_ATTEMPTS) {
        await new Promise(resolve => setTimeout(resolve, KIOSK_FACE_SCAN_INTERVAL_MS));
      }
    }

    laser.style.display = 'none';
    if (!verified) {
      drawDetectionBoxes([]);
      throw new Error('Wajah belum terverifikasi stabil selama 1,5 detik. Posisikan wajah tegak lalu coba lagi.');
    }

    kioskState.faceVerified = true;
    document.getElementById('kioskSession').disabled = true;
    const sil = document.getElementById('faceSilhouette');
    if (sil) sil.classList.add('matched');

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

    // Suara sambutan & instruksi bersiap pemeriksaan APD
    const studentName = kioskState.student.nama;
    speakKioskText(`Hai ${studentName}, silakan bersiap untuk pemeriksaan APD.`);
    setKioskStatus(
      `Identitas Valid: ${studentName}`,
      'Silakan bersiap untuk pemeriksaan APD...',
      false
    );

    // Langsung menjalankan pemeriksaan APD secara otomatis
    await startAPDInspection();
  } catch (error) {
    kioskState.faceImages = [];
    document.getElementById('scanLaser').style.display = 'none';
    drawDetectionBoxes([]);
    setKioskStatus('Verifikasi wajah gagal', error.message, true);
    setKioskBusy(false, 'Coba Verifikasi Wajah Lagi');
  }
}

function renderKioskApd(results, faceResult) {
  kioskState.apd = results;
  let requiredMissing = false;
  const activeBoxes = [];

  // Tetap tampilkan kotak deteksi wajah jika terdeteksi
  if (faceResult && faceResult.detected && faceResult.box) {
    const faceLabel = faceResult.label || 'Wajah';
    const faceScore = Math.round((faceResult.confidence || 0) * 100);
    activeBoxes.push({
      box: faceResult.box,
      dimensions: faceResult.dimensions,
      label: `${faceLabel} ${faceScore}%`,
      color: faceResult.matched ? '#10B981' : '#F59E0B'
    });
  }

  if (results) {
    Object.entries(kioskApdItems).forEach(([key, item]) => {
      const result = results[key];
      if (!result) return;
      const tag = document.getElementById(item.element);
      if (!result.wajib) {
        if (tag) tag.style.display = 'none';
        return;
      }
      const detected = result.worn;
      if (key !== 'jeans' && !detected) requiredMissing = true;
      const score = Math.round(result.probability * 100);

      // Dynamic Object Detection bounding box seperti pada uji_kamera_apd.py
      if (detected && result.box) {
        activeBoxes.push({
          box: result.box,
          dimensions: result.dimensions,
          label: `${result.label || item.label} ${score}%`,
          color: result.color || '#22C55E'
        });
      }

      if (tag) {
        tag.textContent = result.validasi_manual
          ? `${item.label}: Validasi PLP (${detected ? 'Sesuai' : 'Kurang'}, ${score}%)`
          : `${item.label}: ${detected ? 'OK' : 'Kurang'} (${score}%)`;
        tag.style.display = 'block';
      }
    });
  }

  drawDetectionBoxes(activeBoxes);

  const completionMsg = requiredMissing
    ? 'Pemeriksaan APD selesai. Ada APD yang belum lengkap.'
    : 'Pemeriksaan APD selesai. Kelengkapan keselamatan Anda sesuai.';
  speakKioskText(completionMsg);

  setKioskStatus(
    requiredMissing ? 'Ada APD belum terdeteksi (5 dtk)' : 'Pemindaian APD & Wajah selesai (5 dtk stabil)',
    requiredMissing
      ? 'Hasil akan dicatat dan ditindaklanjuti sesuai aturan APD.'
      : 'Pemeriksaan 5 detik selesai stabil. Silakan simpan kehadiran.',
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
  drawDetectionBoxes([]);
  document.getElementById('btnKioskApdRetry').hidden = true;
  Object.values(kioskApdItems).forEach(item => {
    const tag = document.getElementById(item.element);
    if (tag) tag.style.display = 'none';
  });
  await startAPDInspection();
}

async function startAPDInspection() {
  if (!kioskState.faceVerified) return;
  setKioskBusy(true, 'Siapkan APD...');
  const laser = document.getElementById('scanLaser');
  laser.style.display = 'none';
  document.getElementById('btnKioskApdRetry').hidden = true;
  drawDetectionBoxes([]);

  try {
    for (let seconds = 3; seconds > 0; seconds -= 1) {
      setKioskStatus(
        'Siapkan APD',
        `Pemindaian dimulai dalam ${seconds} detik. Berdirilah tegak menghadap kamera.`,
        false
      );
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    document.getElementById('btnKioskAction').textContent = 'Memindai APD & Wajah...';
    laser.style.display = 'block';
    laser.style.animation = 'kioskLaserAnimation 2.2s infinite ease-in-out';

    const startTime = Date.now();
    const framesCollected = [];
    let prevEma = {};
    let prevDetected = {};
    let lastApdResult = null;
    let lastFaceResult = null;

    // Verifikasi APD & Wajah secara dinamis selama 5 detik penuh
    while (Date.now() - startTime < KIOSK_APD_VERIFY_DURATION_MS) {
      const frame = captureKioskFrame();
      framesCollected.push(frame);
      if (framesCollected.length > KIOSK_APD_SCAN_FRAME_COUNT) {
        framesCollected.shift();
      }

      const scanResult = await postKioskScan(
        'live_apd',
        frame,
        kioskState.sessionId,
        kioskState.faceCropMode,
        prevEma,
        prevDetected
      );

      if (scanResult.apd) {
        lastApdResult = scanResult.apd;
        Object.entries(scanResult.apd).forEach(([item, val]) => {
          prevEma[item] = val.probability;
          prevDetected[item] = val.worn;
        });
      }

      if (scanResult.face) {
        lastFaceResult = scanResult.face;
      }

      // Kumpulkan bounding box dinamis (Wajah + APD bergerak dinamis mengikuti posisi mahasiswa)
      const liveBoxes = [];

      // 1. Wajah Mahasiswa (tetap muncul & dinamis membingkai wajah)
      if (lastFaceResult && lastFaceResult.detected && lastFaceResult.box) {
        const faceLabel = lastFaceResult.label || 'Wajah';
        const faceConf = Math.round((lastFaceResult.confidence || 0) * 100);
        liveBoxes.push({
          box: lastFaceResult.box,
          dimensions: lastFaceResult.dimensions,
          label: `${faceLabel} ${faceConf}%`,
          color: lastFaceResult.matched ? '#10B981' : '#F59E0B'
        });
      }

      // 2. Komponen APD (Helm, Baju, Jeans, Sepatu - muncul jika terdeteksi)
      if (lastApdResult) {
        Object.entries(lastApdResult).forEach(([key, apdItem]) => {
          if (apdItem.wajib && apdItem.worn && apdItem.box) {
            liveBoxes.push({
              box: apdItem.box,
              dimensions: apdItem.dimensions,
              label: `${apdItem.label || key.toUpperCase()} ${Math.round(apdItem.probability * 100)}%`,
              color: apdItem.color || '#22C55E'
            });
          }

          // Perbarui badge tag status di kanan atas
          const tag = document.getElementById(kioskApdItems[key]?.element);
          if (tag) {
            if (!apdItem.wajib) {
              tag.style.display = 'none';
            } else {
              const score = Math.round(apdItem.probability * 100);
              tag.textContent = apdItem.validasi_manual
                ? `${kioskApdItems[key].label}: Validasi PLP (${apdItem.worn ? 'Sesuai' : 'Kurang'}, ${score}%)`
                : `${kioskApdItems[key].label}: ${apdItem.worn ? 'OK' : 'Kurang'} (${score}%)`;
              tag.style.borderColor = apdItem.color || (apdItem.worn ? '#22C55E' : '#EF4444');
              tag.style.color = apdItem.color || (apdItem.worn ? '#22C55E' : '#EF4444');
              tag.style.display = 'block';
            }
          }
        });
      }

      drawDetectionBoxes(liveBoxes);

      const elapsed = Date.now() - startTime;
      const remainingSec = Math.max(0, (KIOSK_APD_VERIFY_DURATION_MS - elapsed) / 1000).toFixed(1);
      setKioskStatus(
        'Memeriksa Kelengkapan APD & Wajah...',
        `Waktu pemindaian: ${remainingSec} dtk tersisa. Berdiri tegak menghadap kamera.`,
        false
      );

      await new Promise(resolve => setTimeout(resolve, KIOSK_APD_LIVE_INTERVAL_MS));
    }

    kioskState.apdImages = framesCollected.length >= KIOSK_APD_SCAN_FRAME_COUNT
      ? framesCollected
      : new Array(KIOSK_APD_SCAN_FRAME_COUNT).fill(framesCollected[framesCollected.length - 1]);

    renderKioskApd(lastApdResult, lastFaceResult);
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
