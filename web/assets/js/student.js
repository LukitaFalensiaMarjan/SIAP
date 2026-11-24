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

// Compensation Calculator Simulator
function simulateCompensation(minutes) {
  const totalLate = parseInt(minutes, 10) || 0;
  const compMinutes = totalLate * 5;
  const jp = Math.floor(compMinutes / 50);
  const remainingMins = compMinutes % 50;

  const lateEl = document.getElementById('calcLateMinutes');
  const compEl = document.getElementById('calcCompMinutes');
  const jpEl = document.getElementById('calcCompJP');

  if (lateEl) lateEl.innerText = `${totalLate} menit`;
  if (compEl) compEl.innerText = `${compMinutes} menit`;
  if (jpEl) jpEl.innerText = `${jp} JP ${remainingMins} menit`;
}

function renderStudentCompensation(result) {
  const summary = result.summary || {};
  const attendance = result.attendance || [];

  const totalLate = summary.total_terlambat_menit || 0;
  const totalComp = summary.total_kompensasi_menit || 0;
  const totalResolved = summary.total_diselesaikan_menit || 0;
  const remainComp = summary.sisa_kompensasi_menit != null ? summary.sisa_kompensasi_menit : Math.max(0, totalComp - totalResolved);

  const lateEl = document.getElementById('calcLateMinutes');
  const compEl = document.getElementById('calcCompMinutes');
  const jpEl = document.getElementById('calcCompJP');
  const remainDebtEl = document.getElementById('calcRemainDebt');

  if (lateEl) lateEl.innerText = `${totalLate} menit`;
  if (compEl) compEl.innerText = `${totalComp} menit`;
  if (jpEl) {
    const jp = Math.floor(totalComp / 50);
    const rem = totalComp % 50;
    jpEl.innerText = `${jp} JP ${rem} menit`;
  }
  if (remainDebtEl) {
    remainDebtEl.innerText = `${remainComp} menit`;
    const remainJpEl = remainDebtEl.nextElementSibling;
    if (remainJpEl) {
      const rJp = Math.floor(remainComp / 50);
      const rRem = remainComp % 50;
      remainJpEl.innerText = `${rJp} JP ${rRem} menit`;
    }
  }

  // Progress Bar
  const percent = totalComp > 0 ? Math.min(100, Math.round((totalResolved / totalComp) * 100)) : 100;
  const progFill = document.querySelector('.mhs-progress-fill');
  if (progFill) progFill.style.width = `${percent}%`;
  const progHead = document.querySelector('.mhs-progress-head span:last-child');
  if (progHead) progHead.innerText = `${percent}%`;

  // Render Tabel Rincian Per Sesi Kompensasi
  const tableBody = document.querySelector('.mhs-table-clean tbody');
  const selectSesi = document.querySelector('#modalSubmitKompensasi select');
  if (tableBody) {
    tableBody.replaceChildren();
    if (selectSesi) selectSesi.replaceChildren();

    const lateSessions = attendance.filter(a => a.terlambat_menit > 0);
    if (!lateSessions.length) {
      const row = tableBody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 6;
      cell.style.color = '#64748B';
      cell.style.padding = '18px';
      cell.innerText = 'Tidak ada catatan keterlambatan atau kewajiban kompensasi.';

      if (selectSesi) {
        const opt = document.createElement('option');
        opt.innerText = 'Tidak ada sesi yang memerlukan kompensasi';
        selectSesi.appendChild(opt);
      }
    } else {
      lateSessions.forEach(item => {
        const row = tableBody.insertRow();
        const dateCell = row.insertCell();
        dateCell.style.color = '#64748B';
        dateCell.innerText = studentDate(item.tanggal);

        const mkCell = row.insertCell();
        mkCell.style.fontWeight = '700';
        mkCell.innerText = item.mata_kuliah;

        const lateCell = row.insertCell();
        lateCell.style.color = '#D97706';
        lateCell.style.fontWeight = '600';
        lateCell.innerText = `${item.terlambat_menit} menit`;

        const compCell = row.insertCell();
        compCell.innerText = `${item.kompensasi_menit} menit`;

        const resolvedCell = row.insertCell();
        if (item.diselesaikan_menit > 0) {
          resolvedCell.style.color = '#059669';
          resolvedCell.style.fontWeight = '700';
          resolvedCell.innerText = `${item.diselesaikan_menit} menit`;
        } else {
          resolvedCell.style.color = '#94A3B8';
          resolvedCell.innerText = '—';
        }

        const statusCell = row.insertCell();
        const badge = document.createElement('span');
        if (item.diselesaikan_menit >= item.kompensasi_menit) {
          badge.className = 'mhs-badge mhs-badge-green';
          badge.innerText = 'Selesai';
        } else if (item.pelunasan && item.pelunasan.status === 'menunggu_validasi') {
          badge.className = 'mhs-badge mhs-badge-amber';
          badge.innerText = 'Menunggu Validasi';
        } else {
          badge.className = 'mhs-badge mhs-badge-amber';
          badge.innerText = 'Belum diselesaikan';
        }
        statusCell.appendChild(badge);

        if (selectSesi && (!item.diselesaikan_menit || item.diselesaikan_menit < item.kompensasi_menit)) {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.innerText = `${item.mata_kuliah} (${studentDate(item.tanggal)} - ${item.kompensasi_menit} menit)`;
          selectSesi.appendChild(opt);
        }
      });
    }
  }

  // Handle Form Submit Bukti Pelunasan
  const formSubmit = document.querySelector('#modalSubmitKompensasi form');
  if (formSubmit && !formSubmit.dataset.bound) {
    formSubmit.dataset.bound = 'true';
    formSubmit.onsubmit = async (e) => {
      e.preventDefault();
      const sId = selectSesi ? selectSesi.value : null;
      const taskInput = formSubmit.querySelector('input[type=\"text\"]');
      const taskVal = taskInput ? taskInput.value.trim() : '';

      if (!sId || !taskVal) {
        showToast('Pilih sesi dan isi bentuk tugas pengganti.');
        return;
      }

      try {
        const res = await fetch('/api/student/compensation/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ absensi_id: sId, uraian_tugas: taskVal })
        });
        const resJson = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(resJson.error || 'Gagal mengirim pengajuan.');
        closeMhsModal('modalSubmitKompensasi');
        showToast(resJson.message || 'Bukti kompensasi berhasil diajukan untuk diverifikasi!');
        loadStudentOverview();
      } catch (err) {
        showToast(err.message);
      }
    };
  }
}

function renderStudentNotifications(notifications) {
  const dropdown = document.getElementById('mhsNotifDropdown');
  const list = document.getElementById('mhsNotifCardsList');
  const notifs = notifications || [];

  // Update badge count
  const bellBtns = document.querySelectorAll('.mhs-bell-btn');
  bellBtns.forEach(btn => {
    let badge = btn.querySelector('.mhs-bell-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'mhs-bell-badge';
      btn.appendChild(badge);
    }
    badge.style.display = notifs.length > 0 ? 'inline-block' : 'none';
  });

  // Render in dropdown
  if (dropdown) {
    const listWrap = dropdown.querySelector('div[style*=\"max-height: 280px\"]') || dropdown.children[1];
    if (listWrap) {
      listWrap.replaceChildren();
      if (!notifs.length) {
        const p = document.createElement('p');
        p.style.cssText = 'font-size:12px;color:#64748B;margin:0;padding:8px;';
        p.innerText = 'Belum ada notifikasi baru.';
        listWrap.appendChild(p);
      } else {
        notifs.forEach(n => {
          const item = document.createElement('div');
          item.style.cssText = `background:${n.is_violation ? '#FEF2F2' : '#F8FAFC'};padding:10px;border-radius:8px;border:1px solid ${n.is_violation ? '#FCA5A5' : '#E2E8F0'};cursor:pointer;margin-bottom:6px;`;
          item.onclick = () => { window.location.href = 'notifikasi.html'; };
          item.innerHTML = `
            <div style=\"display:flex;align-items:center;justify-content:space-between;margin-bottom:2px;\">
              <span style=\"font-size:12px;font-weight:700;color:${n.is_violation ? '#991B1B' : '#0F172A'};\">${n.title}</span>
              <span class=\"mhs-badge ${n.badge_class || 'mhs-badge-blue'}\" style=\"font-size:9.5px;\">${n.badge || 'Baru'}</span>
            </div>
            <p style=\"font-size:11px;color:${n.is_violation ? '#7F1D1D' : '#64748B'};margin:0 0 4px;line-height:1.4;\">${n.desc}</p>
            <span style=\"font-size:10px;color:#94A3B8;\">${n.date}</span>
          `;
          listWrap.appendChild(item);
        });
      }
    }
  }

  // Render in notifikasi.html
  if (list) {
    list.replaceChildren();
    if (!notifs.length) {
      const emptyCard = document.createElement('div');
      emptyCard.className = 'mhs-card-white';
      emptyCard.style.cssText = 'padding:24px;color:#64748B;font-size:13px;';
      emptyCard.innerText = 'Belum ada pemberitahuan atau catatan absensi.';
      list.appendChild(emptyCard);
    } else {
      notifs.forEach(n => {
        const card = document.createElement('div');
        card.className = 'mhs-notif-card';
        if (n.is_violation) {
          card.style.cssText = 'border-left:4px solid #DC2626;background:#FEF2F2;cursor:pointer;';
          card.onclick = () => showToast('Silakan menuju Administrasi Jurusan untuk pengambilan fisik Surat Peringatan (SP).');
        } else {
          card.style.cursor = 'pointer';
          card.onclick = () => showToast(n.title);
        }
        card.innerHTML = `
          <div class=\"mhs-notif-body\">
            <div class=\"mhs-notif-title-row\">
              <span class=\"mhs-notif-title\" style=\"${n.is_violation ? 'color:#991B1B;' : ''}\">${n.title}</span>
              <span class=\"mhs-badge ${n.badge_class || 'mhs-badge-blue'}\">${n.badge || 'Baru'}</span>
            </div>
            <div class=\"mhs-notif-desc\" style=\"${n.is_violation ? 'color:#7F1D1D;font-weight:500;' : ''}\">${n.desc}</div>
            <div class=\"mhs-notif-date\">${n.date}</div>
          </div>
        `;
        list.appendChild(card);
      });
    }
  }
}

async function loadStudentOverview() {
  try {
    const response = await fetch('/api/student/overview');
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Data mahasiswa gagal dimuat.');
    renderStudentProfile(result.student);
    renderStudentAttendance(result);
    renderStudentSessions(result.sessions_today || []);
    renderStudentCompensation(result);
    renderStudentNotifications(result.notifications || []);
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
  const badges = document.querySelectorAll('.mhs-bell-badge');
  badges.forEach(b => b.style.display = 'none');
  showToast('Semua notifikasi telah ditandai dibaca.');
}

document.addEventListener('DOMContentLoaded', loadStudentOverview);
