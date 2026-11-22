/**
 * POLMAN SMART ATTENDANCE — INTERACTIVE ADMIN PORTAL
 * Handles tab switching, search filtering, modals, and actions with zero icons
 */

function showToast(message) {
  let toast = document.getElementById('admGlobalToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'admGlobalToast';
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #0F172A;
      color: #FFFFFF;
      padding: 12px 20px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 600;
      box-shadow: 0 10px 25px rgba(0,0,0,0.25);
      z-index: 9999;
      opacity: 0;
      transform: translateY(12px);
      transition: all 0.2s ease;
      pointer-events: none;
    `;
    document.body.appendChild(toast);
  }
  toast.innerText = message;
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(12px)';
  }, 3200);
}

// Tab switcher
function switchAdmTab(tabContainerId, activeIndex, btnElement) {
  const container = document.getElementById(tabContainerId);
  if (!container) return;

  // Toggle buttons
  const buttons = btnElement.parentElement.querySelectorAll('.adm-tab-btn');
  buttons.forEach(b => b.classList.remove('active'));
  btnElement.classList.add('active');

  // Toggle tab contents
  const contents = container.querySelectorAll('.adm-tab-content');
  contents.forEach((c, idx) => {
    if (idx === activeIndex) {
      c.style.display = 'block';
    } else {
      c.style.display = 'none';
    }
  });
}

// Live table filter
function filterAdmTable(tableId, searchInputId, classSelectId, statusSelectId) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const searchVal = searchInputId ? (document.getElementById(searchInputId)?.value.toLowerCase().trim() || '') : '';
  const classVal = classSelectId ? (document.getElementById(classSelectId)?.value.toLowerCase().trim() || 'semua') : 'semua';
  const statusVal = statusSelectId ? (document.getElementById(statusSelectId)?.value.toLowerCase().trim() || 'semua') : 'semua';

  const rows = table.querySelectorAll('tbody tr');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    const rowClass = (row.getAttribute('data-kelas') || '').toLowerCase();
    const rowStatus = (row.getAttribute('data-status') || '').toLowerCase();

    const matchSearch = !searchVal || text.includes(searchVal);
    const matchClass = classVal === 'semua' || rowClass.includes(classVal) || text.includes(classVal);
    const matchStatus = statusVal === 'semua' || rowStatus.includes(statusVal) || text.includes(statusVal);

    if (matchSearch && matchClass && matchStatus) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}

// Modal management
function openAdmModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.add('show');
}

function closeAdmModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.remove('show');
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.adm-modal-backdrop.show').forEach(m => m.classList.remove('show'));
  }
});

// ── ATTENDANCE MONITORING & AI APD INSPECTION DATA STORE ──
const attendanceDataStore = {
  'abs-1': {
    id: 'abs-1',
    nim: '224201020',
    nama: 'Fajar Ramadhan',
    kelas: '2MEA',
    matkul: 'Praktik Proses Manufaktur',
    waktu: '07.31 WIB',
    kiosk: 'Kiosk 01 · Lab CNC',
    timeFooter: '07.31:14 WIB',
    status: 'pelanggaran',
    invalidParam: 'Sepatu safety tidak sesuai standar K3 bengkel',
    tags: {
      head: { text: 'Helm: Sesuai (Standar Putih)', valid: true },
      body: { text: 'Wearpack: Sesuai Resmi POLMAN', valid: true },
      feet: { text: 'Sepatu: Anomali (Confidence 74%)', valid: false }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '99.1%', status: 'Sesuai', note: 'Biometrik wajah cocok dengan basis data mahasiswa.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '96.5%', status: 'Sesuai', note: 'Helm putih terdeteksi di kepala dengan tali pengikat terpasang rapi.', isCompliant: true },
      { name: 'Baju Praktik (Wearpack)', conf: '98.2%', status: 'Sesuai', note: 'Wearpack resmi POLMAN lengan panjang terdeteksi rapi dan dikancingkan.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '97.0%', status: 'Sesuai', note: 'Celana panjang bahan denim tebal tanpa robekan.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '74.0%', status: 'Tidak Sesuai / Anomali', note: 'Ujung pelindung sepatu tertutup kain wearpack bagian bawah; sensor kamera tidak mendeteksi toe cap baja standar bengkel mesin.', isCompliant: false }
    ],
    aiSummary: 'AI mendeteksi anomali pada Sepatu Safety (Confidence 74%). Admin dapat memverifikasi visual: jika memang melanggar tandai SP, atau jika hanya kesalahan sudut kamera klik Konfirmasi Sesuai.'
  },
  'abs-2': {
    id: 'abs-2',
    nim: '223104021',
    nama: 'Dinda Larasati',
    kelas: '3FEA',
    matkul: 'Teknologi Pengecoran',
    waktu: '08.04 WIB',
    kiosk: 'Kiosk Lab Pengecoran Logam',
    timeFooter: '08.04:22 WIB',
    status: 'pelanggaran',
    invalidParam: 'Tidak mengenakan helm keselamatan di area zona bahaya',
    tags: {
      head: { text: 'Helm: Tidak Terdeteksi (68%)', valid: false },
      body: { text: 'Wearpack: Sesuai Tahan Panas', valid: true },
      feet: { text: 'Sepatu: Sesuai Standar', valid: true }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '98.7%', status: 'Sesuai', note: 'Biometrik terverifikasi.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '68.0%', status: 'Tidak Sesuai / Anomali', note: 'Mahasiswa tidak mengenakan helm keselamatan saat memasuki area zona merah pengecoran logam cair.', isCompliant: false },
      { name: 'Baju Praktik', conf: '95.4%', status: 'Sesuai', note: 'Wearpack tahan panas terpakai dengan standar bengkel cor.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '96.2%', status: 'Sesuai', note: 'Celana jeans tebal terverifikasi.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '94.8%', status: 'Sesuai', note: 'Sepatu boot keselamatan standar terdeteksi aman.', isCompliant: true }
    ],
    aiSummary: 'AI mendeteksi pelanggaran APD wajib: Helm keselamatan tidak terdeteksi pada area zona merah pengecoran (Confidence 68%). Memerlukan keputusan admin.'
  },
  'abs-3': {
    id: 'abs-3',
    nim: '224302008',
    nama: 'Rafi Maulana',
    kelas: '2AEB',
    matkul: 'Sistem Kendali',
    waktu: 'Kemarin 13.02 WIB',
    kiosk: 'Kiosk Lab Otomasi Industri',
    timeFooter: '13.02:40 WIB',
    status: 'pelanggaran',
    invalidParam: 'Lengan baju wearpack digulung pada area praktikum panel kelistrikan',
    tags: {
      head: { text: 'Helm: Nonaktif (Lab Komputer)', valid: true },
      body: { text: 'Wearpack: Lengan Tergulung (71%)', valid: false },
      feet: { text: 'Sepatu: Sesuai Standar ESD', valid: true }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '97.5%', status: 'Sesuai', note: 'Biometrik terverifikasi.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: 'N/A', status: 'Tidak Diperiksa', note: 'Aturan sesi tidak mewajibkan helm keselamatan.', isCompliant: true },
      { name: 'Baju Praktik (Wearpack)', conf: '71.0%', status: 'Tidak Sesuai / Anomali', note: 'Lengan baju wearpack digulung melebihi siku saat berinteraksi dengan panel kontrol kelistrikan.', isCompliant: false },
      { name: 'Celana Jeans Standar', conf: '98.1%', status: 'Sesuai', note: 'Celana panjang rapi.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '95.0%', status: 'Sesuai', note: 'Sepatu antistatis ESD terdeteksi.', isCompliant: true }
    ],
    aiSummary: 'AI mendeteksi posisi wearpack melanggar SOP lab: Lengan baju digulung saat praktikum panel kelistrikan. Perlu keputusan admin.'
  },
  'abs-4': {
    id: 'abs-4',
    nim: '224443012',
    nama: 'Muhammad Basit Rozak Akbar S.P',
    kelas: '3AEC1',
    matkul: 'Praktik Proses Manufaktur',
    waktu: '07.27 WIB',
    kiosk: 'Kiosk 01 · Lab CNC',
    timeFooter: '07.27:08 WIB',
    status: 'sesuai',
    invalidParam: '',
    tags: {
      head: { text: 'Helm: Sesuai (100%)', valid: true },
      body: { text: 'Wearpack: Sesuai (100%)', valid: true },
      feet: { text: 'Sepatu: Sesuai (100%)', valid: true }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '99.8%', status: 'Sesuai', note: 'Biometrik terverifikasi akurat.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '99.2%', status: 'Sesuai', note: 'Helm putih terpasang standar K3.', isCompliant: true },
      { name: 'Baju Praktik', conf: '98.9%', status: 'Sesuai', note: 'Wearpack lengkap dan kancing tertutup rapi.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '98.5%', status: 'Sesuai', note: 'Celana jeans tebal standar industri.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '99.0%', status: 'Sesuai', note: 'Sepatu safety baja terdeteksi sempurna.', isCompliant: true }
    ],
    aiSummary: 'Seluruh parameter APD (Helm, Wearpack, Celana jeans, Sepatu safety) lengkap dan terverifikasi sesuai standar K3.'
  },
  'abs-5': {
    id: 'abs-5',
    nim: '224201014',
    nama: 'Nadia Fitriani',
    kelas: '2MEA',
    matkul: 'Praktik Proses Manufaktur',
    waktu: '07.34 WIB',
    kiosk: 'Kiosk 01 · Lab CNC',
    timeFooter: '07.34:11 WIB',
    status: 'sesuai',
    invalidParam: '',
    tags: {
      head: { text: 'Helm: Sesuai', valid: true },
      body: { text: 'Wearpack: Sesuai', valid: true },
      feet: { text: 'Sepatu: Sesuai', valid: true }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '99.5%', status: 'Sesuai', note: 'Biometrik terverifikasi.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '98.1%', status: 'Sesuai', note: 'Helm putih standar K3 terpakai.', isCompliant: true },
      { name: 'Baju Praktik', conf: '97.8%', status: 'Sesuai', note: 'Wearpack terpasang rapi.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '98.0%', status: 'Sesuai', note: 'Celana jeans standar.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '97.5%', status: 'Sesuai', note: 'Sepatu safety terdeteksi.', isCompliant: true }
    ],
    aiSummary: 'Pemeriksaan APD lengkap tanpa pelanggaran.'
  },
  'abs-6': {
    id: 'abs-6',
    nim: '224201035',
    nama: 'Rizki Kurniawan',
    kelas: '2MEA',
    matkul: 'Praktik Proses Manufaktur',
    waktu: 'Kemarin 07.25 WIB',
    kiosk: 'Kiosk 01 · Lab CNC',
    timeFooter: '07.25:50 WIB',
    status: 'pelanggaran',
    invalidParam: 'Tidak menggunakan safety shoes (memakai sepatu kets kanvas)',
    tags: {
      head: { text: 'Helm: Sesuai', valid: true },
      body: { text: 'Wearpack: Sesuai', valid: true },
      feet: { text: 'Sepatu: Pelanggaran Ditetapkan', valid: false }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '99.0%', status: 'Sesuai', note: 'Biometrik cocok.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '98.0%', status: 'Sesuai', note: 'Helm keselamatan terdeteksi.', isCompliant: true },
      { name: 'Baju Praktik', conf: '96.5%', status: 'Sesuai', note: 'Wearpack lengkap.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '97.0%', status: 'Sesuai', note: 'Sesuai standar.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '42.0%', status: 'Pelanggaran Ditetapkan', note: 'Mahasiswa menggunakan sepatu kets kanvas biasa bukan safety shoes.', isCompliant: false }
    ],
    aiSummary: 'Status Pelanggaran telah ditetapkan oleh admin. Surat Peringatan (SP) telah diterbitkan untuk mahasiswa.'
  },
  'abs-7': {
    id: 'abs-7',
    nim: '224201042',
    nama: 'Hendra Setiawan',
    kelas: '2MEA',
    matkul: 'Praktik Proses Manufaktur',
    waktu: '07.29 WIB',
    kiosk: 'Kiosk 01 · Lab CNC',
    timeFooter: '07.29:45 WIB',
    status: 'sesuai',
    invalidParam: '',
    tags: {
      head: { text: 'Helm: Sesuai (Standar Putih)', valid: true },
      body: { text: 'Wearpack: Sesuai Standar', valid: true },
      feet: { text: 'Sepatu: Sesuai Standar K3', valid: true }
    },
    parameters: [
      { name: 'Verifikasi Wajah', conf: '99.4%', status: 'Sesuai', note: 'Biometrik terverifikasi.', isCompliant: true },
      { name: 'Helm Keselamatan', conf: '98.5%', status: 'Sesuai', note: 'Helm terpasang rapi.', isCompliant: true },
      { name: 'Baju Praktik', conf: '98.0%', status: 'Sesuai', note: 'Wearpack lengkap.', isCompliant: true },
      { name: 'Celana Jeans Standar', conf: '97.5%', status: 'Sesuai', note: 'Celana jeans standar.', isCompliant: true },
      { name: 'Sepatu Safety', conf: '98.8%', status: 'Sesuai', note: 'Sepatu safety terdeteksi.', isCompliant: true }
    ],
    aiSummary: 'Seluruh APD memenuhi standar keselamatan kerja praktikum.'
  }
};

let currentActiveAbsId = null;

// Open Detail Absensi Modal
function openDetailAbsensi(absId) {
  const item = attendanceDataStore[absId];
  if (!item) return;

  currentActiveAbsId = absId;

  // Header & Identity
  document.getElementById('modalStudentTitle').innerText = `Detail Absensi — ${item.nama}`;
  document.getElementById('detNama').innerText = item.nama;
  document.getElementById('detNIMKelas').innerText = `NIM: ${item.nim} · Kelas: ${item.kelas}`;
  document.getElementById('detMatkul').innerText = item.matkul;
  document.getElementById('detWaktu').innerText = item.waktu;
  document.getElementById('kioskNameBadge').innerText = item.kiosk;
  document.getElementById('captureTimeFooter').innerText = item.timeFooter;

  // Badge Status & Visibility of Admin Action Buttons
  const badgeEl = document.getElementById('detStatusBadge');
  const validationButtons = document.getElementById('validationButtonsGroup');

  if (item.status === 'sesuai') {
    badgeEl.className = 'adm-badge adm-badge-green';
    badgeEl.innerText = 'Sesuai';
    
    // KALO SESUAI: Sembunyikan tombol validasi pelanggaran & konfirmasi, hanya tampil tombol Tutup
    if (validationButtons) {
      validationButtons.style.display = 'none';
    }
  } else {
    badgeEl.className = 'adm-badge adm-badge-red';
    badgeEl.innerText = 'Tidak Sesuai';

    // KALO TIDAK SESUAI: Tampilkan tombol tambahan (Tandai Pelanggaran SP & Konfirmasi Sesuai)
    if (validationButtons) {
      validationButtons.style.display = 'flex';
    }
  }

  // Visual Overlay Tags on Camera Capture
  const tagHead = document.getElementById('tagHead');
  const tagBody = document.getElementById('tagBody');
  const tagFeet = document.getElementById('tagFeet');

  tagHead.innerText = item.tags.head.text;
  tagHead.className = `kiosk-overlay-tag tag-head ${item.tags.head.valid ? 'valid' : 'invalid'}`;

  tagBody.innerText = item.tags.body.text;
  tagBody.className = `kiosk-overlay-tag tag-body ${item.tags.body.valid ? 'valid' : 'invalid'}`;

  tagFeet.innerText = item.tags.feet.text;
  tagFeet.className = `kiosk-overlay-tag tag-feet ${item.tags.feet.valid ? 'valid' : 'invalid'}`;

  // Populate Parameter Checklist
  const checkListEl = document.getElementById('parameterChecklist');
  checkListEl.innerHTML = item.parameters.map(param => {
    const badgeClass = param.isCompliant ? 'adm-badge-green' : 'adm-badge-red';
    return `
      <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
        <div>
          <div style="font-size: 13px; font-weight: 700; color: #0F172A;">${param.name}</div>
          <div style="font-size: 11.5px; color: #64748B; margin-top: 2px;">${param.note}</div>
        </div>
        <div style="text-align: right; white-space: nowrap;">
          <span class="adm-badge ${badgeClass}" style="font-size: 10px;">${param.status}</span>
          <div style="font-size: 10.5px; font-weight: 700; color: #64748B; margin-top: 2px;">Skor: ${param.conf}</div>
        </div>
      </div>
    `;
  }).join('');

  // AI Summary Box
  const summaryBox = document.getElementById('aiSummaryBox');
  const hasViolationOrAnomaly = item.parameters.some(p => !p.isCompliant);

  if (hasViolationOrAnomaly) {
    summaryBox.style.background = '#FEF2F2';
    summaryBox.style.borderColor = '#FCA5A5';
    summaryBox.style.color = '#991B1B';
    summaryBox.innerHTML = `
      <div style="font-weight: 800; margin-bottom: 2px;">Deteksi Anomali Kamera Kiosk</div>
      <div>${item.aiSummary}</div>
    `;
  } else {
    summaryBox.style.background = '#F0FDF4';
    summaryBox.style.borderColor = '#86EFAC';
    summaryBox.style.color = '#166534';
    summaryBox.innerHTML = `
      <div style="font-weight: 800; margin-bottom: 2px;">Kepatuhan APD Sempurna</div>
      <div>${item.aiSummary}</div>
    `;
  }

  openAdmModal('modalDetailAbsensi');
}

// Execute Admin Decision: Tandai Pelanggaran SP vs Konfirmasi Sesuai (Koreksi salah scanning)
function executeValidationAction(actionType) {
  if (!currentActiveAbsId) return;
  const item = attendanceDataStore[currentActiveAbsId];
  if (!item) return;

  const rowEl = document.querySelector(`tr[data-id="${currentActiveAbsId}"]`);

  if (actionType === 'pelanggaran') {
    item.status = 'pelanggaran';
    if (rowEl) {
      rowEl.setAttribute('data-status', 'pelanggaran');
      const badge = rowEl.querySelector('.status-badge');
      if (badge) {
        badge.className = 'adm-badge adm-badge-red status-badge';
        badge.innerText = 'Pelanggaran (SP)';
      }
    }

    // Buat objek notifikasi resmi pelanggaran untuk dikirimkan ke mahasiswa
    const newNotif = {
      id: 'sp-' + Date.now(),
      title: 'Pemberitahuan Pelanggaran APD Praktikum',
      desc: `Pemeriksaan AI pada sesi ${item.matkul} mendeteksi ketidaksesuaian: ${item.invalidParam || 'Pelanggaran kelengkapan APD'}. Anda dinyatakan melakukan pelanggaran K3. Silakan untuk mengambil surat peringatan di administrasi jurusannya.`,
      date: 'Hari ini · Baru saja',
      isNew: true,
      isViolation: true,
      badgeText: 'Surat Peringatan',
      nim: item.nim,
      nama: item.nama,
      matkul: item.matkul
    };

    // Simpan ke localStorage agar sinkron dengan Portal Mahasiswa
    let notifs = [];
    try {
      const stored = localStorage.getItem('siap_notifications');
      if (stored) notifs = JSON.parse(stored);
    } catch (e) {
      notifs = [];
    }
    notifs.unshift(newNotif);
    localStorage.setItem('siap_notifications', JSON.stringify(notifs));

    closeAdmModal('modalDetailAbsensi');
    showToast(`Pelanggaran telah ditetapkan! Surat Peringatan (SP) diterbitkan dan notifikasi dikirimkan ke mahasiswa (${item.nama}).`);

  } else if (actionType === 'sesuai') {
    // Koreksi kesalahan scanning AI oleh admin
    item.status = 'sesuai';
    if (rowEl) {
      rowEl.setAttribute('data-status', 'sesuai');
      const badge = rowEl.querySelector('.status-badge');
      if (badge) {
        badge.className = 'adm-badge adm-badge-green status-badge';
        badge.innerText = 'Sesuai';
      }
    }

    closeAdmModal('modalDetailAbsensi');
    showToast(`Hasil scanning dikoreksi & divalidasi sebagai Sesuai oleh admin.`);
  }
}

// Filtering for Monitoring Absensi (Search + Dropdown Kelas + Dropdown Status APD: All, Sesuai, Pelanggaran)
function applyAbsensiFilters() {
  const searchInput = document.getElementById('searchAbsensi');
  const classSelect = document.getElementById('filterKelasAbsensi');
  const statusSelect = document.getElementById('filterStatusAPD');
  const table = document.getElementById('tableMonitoringAbsensi');
  if (!table) return;

  const searchKeyword = searchInput ? searchInput.value.toLowerCase().trim() : '';
  const classFilter = classSelect ? classSelect.value.toLowerCase().trim() : 'all';
  const statusFilter = statusSelect ? statusSelect.value.toLowerCase().trim() : 'all';

  const rows = table.querySelectorAll('tbody tr');
  rows.forEach(row => {
    const textContent = row.textContent.toLowerCase();
    const rowClass = (row.getAttribute('data-kelas') || '').toLowerCase();
    const rowStatus = (row.getAttribute('data-status') || '').toLowerCase();

    const matchSearch = !searchKeyword || textContent.includes(searchKeyword);
    const matchClass = classFilter === 'all' || rowClass.includes(classFilter) || textContent.includes(classFilter);
    const matchStatus = statusFilter === 'all' || rowStatus === statusFilter;

    if (matchSearch && matchClass && matchStatus) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
}
