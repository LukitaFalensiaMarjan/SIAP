/**
 * POLMAN SMART ATTENDANCE — INTERACTIVE STUDENT PORTAL
 * Handles student data views, attendance filters, profile modals, and toast feedback
 */

// Toast notification helper
function showToast(message) {
  let toast = document.getElementById('mhsGlobalToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'mhsGlobalToast';
    toast.className = 'mhs-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 3200);
}

// Copy to clipboard with toast
function copyText(text, label = 'Data') {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`${label} berhasil disalin ke clipboard.`);
  }).catch(() => {
    showToast(`Gagal menyalin ${label}.`);
  });
}

// Notification Drawer Toggle
function toggleNotificationDropdown(e) {
  if (e) e.stopPropagation();
  let dropdown = document.getElementById('mhsNotifDropdown');
  if (!dropdown) return;
  const isShow = dropdown.classList.contains('show');
  if (isShow) {
    dropdown.classList.remove('show');
  } else {
    dropdown.classList.add('show');
  }
}

// Close dropdown on outside click
document.addEventListener('click', function (e) {
  const dropdown = document.getElementById('mhsNotifDropdown');
  const btn = document.querySelector('.mhs-bell-btn');
  if (dropdown && !dropdown.contains(e.target) && btn && !btn.contains(e.target)) {
    dropdown.classList.remove('show');
  }
});

// Interactive Filter for Riwayat Absensi
function filterRiwayatTable() {
  const searchInput = document.getElementById('searchMataKuliah');
  const statusSelect = document.getElementById('filterStatus');
  const table = document.getElementById('tableRiwayatAbsensi');
  if (!table) return;

  const searchKeyword = searchInput ? searchInput.value.toLowerCase().trim() : '';
  const statusFilter = statusSelect ? statusSelect.value.toLowerCase().trim() : 'semua';

  const rows = table.querySelectorAll('tbody tr');
  let visibleCount = 0;

  rows.forEach(row => {
    const textContent = row.textContent.toLowerCase();
    const rowStatus = row.getAttribute('data-status') || '';

    const matchesSearch = !searchKeyword || textContent.includes(searchKeyword);
    const matchesStatus = statusFilter === 'semua' || rowStatus === statusFilter || textContent.includes(statusFilter);

    if (matchesSearch && matchesStatus) {
      row.style.display = '';
      visibleCount++;
    } else {
      row.style.display = 'none';
    }
  });

  const emptyMsg = document.getElementById('tableEmptyMessage');
  if (emptyMsg) {
    emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
  }
}

// Modal open & close helpers
function openMhsModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('show');
  }
}

function closeMhsModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('show');
  }
}

// Close modal on escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.mhs-modal-backdrop.show').forEach(m => m.classList.remove('show'));
  }
});

async function initSiapSession() {
  try {
    const response = await fetch('/api/auth/me');
    if (!response.ok) {
      if (!window.location.pathname.endsWith('/login.html')) {
        window.location.href = '/login.html';
      }
      return;
    }
    const result = await response.json();
    if (result.user && String(result.user.peran).toLowerCase() !== 'mahasiswa') {
      window.location.href = '/admin/dashboard.html';
      return;
    }
    sessionStorage.setItem('siap_user', JSON.stringify(result.user));
  } catch (error) {
    console.warn('Sesi pengguna belum dapat dimuat:', error);
  }
}

document.addEventListener('DOMContentLoaded', initSiapSession);

async function logoutSiap() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } finally {
    sessionStorage.removeItem('siap_user');
    window.location.href = '/';
  }
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('a[href="../login.html"], a[href="/login.html"]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      logoutSiap();
    });
  });
});

function studentInitials(name) {
  return String(name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join('')
    .toUpperCase();
}

function studentDate(value) {
  if (!value) return '—';
  return new Date(`${value}T00:00:00`).toLocaleDateString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
}

function studentTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
}

function setStudentText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value == null || value === '' ? '—' : value;
}

function apdStatusLabel(value, item, required) {
  if (!required) return 'Tidak wajib';
  if (value == null) return item === 'jeans' ? 'Menunggu pemeriksaan manual' : 'Belum diperiksa';
  return Number(value) === 1 ? 'Sesuai' : 'Tidak sesuai';
}

function attendanceStatusLabel(status) {
  if (status === 'lengkap') return 'Lengkap';
  if (status === 'kurang') return 'Tidak lengkap';
  if (status === 'menunggu_validasi') return 'Menunggu validasi';
  return 'Belum diketahui';
}

function attendanceBadgeClass(status) {
  if (status === 'lengkap') return 'mhs-badge mhs-badge-green';
  if (status === 'menunggu_validasi') return 'mhs-badge mhs-badge-amber';
  return 'mhs-badge mhs-badge-red';
}

function renderStudentAttendanceRow(item) {
  const row = document.createElement('tr');
  row.dataset.status = item.status;
  if (document.getElementById('modalDetailAbsensi')) {
    row.addEventListener('click', () => openStudentAttendanceDetail(item));
  }
  const values = [studentDate(item.tanggal), item.mata_kuliah, studentTime(item.waktu), item.lab, 'Hadir'];
  values.forEach((value, index) => {
    const cell = row.insertCell();
    cell.textContent = value || '—';
    if (index === 1) cell.style.fontWeight = '700';
    if (index === 0 || index === 3) cell.style.color = '#64748B';
  });
  const statusCell = row.insertCell();
  const badge = document.createElement('span');
  badge.className = attendanceBadgeClass(item.status);
  badge.textContent = attendanceStatusLabel(item.status);
  statusCell.appendChild(badge);
  return row;
}

function renderStudentAttendance(data) {
  const historyBody = document.getElementById('studentAttendanceHistory');
  const recentBody = document.getElementById('studentRecentAttendance');
  const attendance = data.attendance || [];
  if (historyBody) {
    historyBody.replaceChildren();
    attendance.forEach(item => historyBody.appendChild(renderStudentAttendanceRow(item)));
    filterRiwayatTable();
  }
  if (recentBody) {
    recentBody.replaceChildren();
    const recent = attendance.slice(0, 3);
    if (!recent.length) {
      const row = recentBody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 6;
      cell.textContent = 'Belum ada catatan absensi tersimpan.';
    } else {
      recent.forEach(item => recentBody.appendChild(renderStudentAttendanceRow(item)));
    }
  }
  setStudentText('studentAttendanceCount', `${attendance.length} catatan tersimpan`);
  setStudentText('studentAttendanceTotal', data.summary.total);
  setStudentText('studentAttendanceComplete', data.summary.lengkap);
  setStudentText('studentAttendanceIncomplete', data.summary.kurang);
  setStudentText('studentAttendancePending', data.summary.menunggu_validasi);
}

function openStudentAttendanceDetail(item) {
  setStudentText('mdMatkul', item.mata_kuliah);
  setStudentText('mdTanggal', studentDate(item.tanggal));
  setStudentText('mdJam', `${studentTime(item.waktu)} WIB`);
  setStudentText('mdLab', item.lab);
  setStudentText('mdStatus', attendanceStatusLabel(item.status));
  document.querySelectorAll('[data-attendance-apd]').forEach(element => {
    const itemName = element.dataset.attendanceApd;
    const labels = { helm: 'Helm', baju: 'Baju praktik', jeans: 'Jeans', sepatu: 'Sepatu safety' };
    const required = (item.wajib || []).includes(itemName);
    element.textContent = `${labels[itemName]}: ${apdStatusLabel(item[itemName], itemName, required)}`;
  });
  openMhsModal('modalDetailAbsensi');
}

function renderStudentSessions(sessions) {
  const session = sessions[0];
  if (!session) {
    setStudentText('studentTodayCourse', 'Tidak ada sesi aktif hari ini');
    setStudentText('studentTodayStart', '—');
    setStudentText('studentTodayEnd', '—');
    setStudentText('studentTodayLecturer', '—');
    setStudentText('studentTodayRoom', '—');
    setStudentText('studentTodayRequiredItems', 'Belum ada aturan sesi hari ini');
    setStudentText('studentTodaySessionStatus', 'Tidak ada sesi');
    setStudentText('studentTodaySessionCount', '');
    ['helm', 'baju', 'jeans', 'sepatu'].forEach(item => {
      const rule = document.querySelector(`[data-student-apd-rule="${item}"]`);
      const state = document.querySelector(`[data-student-apd-state="${item}"]`);
      if (rule) rule.textContent = 'Tidak ada sesi';
      if (state) state.textContent = '—';
    });
    return;
  }

  const labels = { helm: 'Helm', baju: 'Baju praktik', jeans: 'Jeans', sepatu: 'Sepatu safety' };
  setStudentText('studentTodayCourse', session.mata_kuliah);
  setStudentText('studentTodayStart', session.jam_mulai);
  setStudentText('studentTodayEnd', session.jam_selesai);
  setStudentText('studentTodayLecturer', session.dosen);
  setStudentText('studentTodayRoom', session.ruang || session.lab);
  setStudentText('studentTodayRequiredItems', (session.wajib || []).map(item => labels[item]).join(', ') || 'Tidak ada APD wajib');
  setStudentText('studentTodaySessionStatus', 'Sesi tersedia hari ini');
  setStudentText('studentTodaySessionCount', `${sessions.length} sesi terjadwal hari ini`);
  ['helm', 'baju', 'jeans', 'sepatu'].forEach(item => {
    const required = (session.wajib || []).includes(item);
    const rule = document.querySelector(`[data-student-apd-rule="${item}"]`);
    const state = document.querySelector(`[data-student-apd-state="${item}"]`);
    if (rule) rule.textContent = required ? 'Wajib sesuai aturan sesi' : 'Tidak diwajibkan sesi ini';
    if (state) state.textContent = required ? 'Wajib' : 'Opsional';
  });
}

function renderStudentProfile(student) {
  const initials = studentInitials(student.nama);
  document.querySelectorAll('.mhs-user-name').forEach(element => {
    element.textContent = student.nama;
  });
  document.querySelectorAll('.mhs-user-sub').forEach(element => {
    element.textContent = `Mahasiswa · ${student.kelas}`;
  });
  document.querySelectorAll('.mhs-avatar-circle').forEach(element => {
    element.textContent = initials;
  });
  setStudentText('studentWelcome', `Selamat datang, ${student.nama}.`);
  setStudentText('studentDashboardName', student.nama);
  setStudentText('studentDashboardClass', student.kelas);
  setStudentText('studentDashboardAvatar', initials);
  const nim = document.getElementById('studentDashboardNim');
  if (nim) {
    nim.textContent = student.nim;
    nim.onclick = () => copyText(student.nim, 'NIM');
  }
  setStudentText('studentProfileName', student.nama);
  setStudentText('studentProfileRole', `Mahasiswa · Kelas ${student.kelas}`);
  setStudentText('studentProfileAvatar', initials);
  const profileNim = document.getElementById('studentProfileNim');
  if (profileNim) {
    profileNim.replaceChildren();
    const value = document.createElement('span');
    value.style.cssText = 'font-size:16px;font-weight:700;';
    value.textContent = student.nim;
    profileNim.appendChild(value);
    profileNim.onclick = () => copyText(student.nim, 'NIM');
  }
  setStudentText('studentProfileClass', student.kelas);
}

function renderUnavailableStudentPage() {
  const title = document.querySelector('.mhs-page-title');
  const main = document.querySelector('.mhs-container');
  if (!title || !main || !title.textContent.includes('Kompensasi')) return;
  const header = main.querySelector('.mhs-page-header');
  const card = document.createElement('section');
  card.className = 'mhs-card-white';
  card.style.cssText = 'padding:24px;margin-top:18px;';
  const heading = document.createElement('h2');
  heading.textContent = 'Fitur belum tersedia';
  heading.style.cssText = 'font-size:18px;font-weight:800;color:#0F172A;margin:0 0 8px;';
  const message = document.createElement('p');
  message.textContent = 'Data evaluasi dan kompensasi belum dapat ditampilkan karena belum ada tabel penyimpanan atau ketentuan perhitungan yang disepakati.';
  message.style.cssText = 'font-size:13px;line-height:1.6;color:#64748B;margin:0;';
  card.append(heading, message);
  main.replaceChildren();
  if (header) main.appendChild(header);
  main.appendChild(card);
}

async function loadStudentOverview() {
  renderUnavailableStudentPage();
  try {
    const response = await fetch('/api/student/overview');
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Data mahasiswa gagal dimuat.');
    renderStudentProfile(result.student);
    renderStudentAttendance(result);
    renderStudentSessions(result.sessions_today || []);
    setStudentText('studentTodayDate', new Date().toLocaleDateString('id-ID', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric'
    }));
  } catch (error) {
    showToast(error.message);
    ['studentDashboardName', 'studentProfileName', 'studentAttendanceHistory', 'studentRecentAttendance'].forEach(id => {
      const element = document.getElementById(id);
      if (element) element.textContent = error.message;
    });
  }
}

function markAllNotificationsRead() {
  showToast('Fitur notifikasi belum tersedia karena belum ada data notifikasi tersimpan.');
}

function initStudentNotifications() {
  const unavailableMessage = 'Notifikasi belum tersedia karena data notifikasi belum disimpan di database.';
  const dropdown = document.getElementById('mhsNotifDropdown');
  if (dropdown) {
    dropdown.replaceChildren();
    const message = document.createElement('p');
    message.textContent = unavailableMessage;
    message.style.cssText = 'font-size:12px;line-height:1.5;color:#64748B;margin:0;';
    dropdown.appendChild(message);
  }
  const list = document.getElementById('mhsNotifCardsList');
  if (list) {
    list.replaceChildren();
    const message = document.createElement('div');
    message.className = 'mhs-card-white';
    message.style.cssText = 'padding:24px;color:#64748B;font-size:13px;';
    message.textContent = unavailableMessage;
    list.appendChild(message);
  }
  document.querySelectorAll('.mhs-bell-badge').forEach(badge => badge.remove());
}

document.addEventListener('DOMContentLoaded', initStudentNotifications);
document.addEventListener('DOMContentLoaded', loadStudentOverview);
