/**
 * POLMAN SMART ATTENDANCE — INTERACTIVE ADMIN PORTAL
 * Handles tab switching, search filtering, modals, and actions with zero icons
 */

async function initSiapAdminSession() {
  renderUnavailableAdminPage();
  try {
    const response = await fetch('/api/auth/me');
    if (!response.ok) {
      window.location.href = '/login.html';
      return;
    }
    const result = await response.json();
    if (!result.user || String(result.user.peran).toLowerCase() === 'mahasiswa') {
      window.location.href = '/mahasiswa/dashboard.html';
      return;
    }
    updateAdminIdentity(result.user);
    sessionStorage.setItem('siap_user', JSON.stringify(result.user));
  } catch (error) {
    console.warn('Sesi administrator belum dapat dimuat:', error);
  }
}

document.addEventListener('DOMContentLoaded', initSiapAdminSession);

function renderUnavailableAdminPage() {
  const path = window.location.pathname;
  if (!path.endsWith('/perangkat.html')) return;
  loadKioskDevicesAdmin();
}

async function loadKioskDevicesAdmin() {
  const table = document.getElementById('tableKiosk');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/kiosk/devices');
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Gagal memuat perangkat.');

    const devices = data.devices || [];
    tbody.replaceChildren();

    if (!devices.length) {
      const row = tbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 7;
      cell.style.color = '#64748B';
      cell.style.padding = '18px';
      cell.textContent = 'Belum ada perangkat kiosk yang terhubung.';
      return;
    }

    devices.forEach(d => {
      const row = tbody.insertRow();
      const nameCell = row.insertCell();
      nameCell.style.fontWeight = '700';
      nameCell.textContent = d.nama;

      const codeCell = row.insertCell();
      codeCell.style.fontWeight = '700';
      codeCell.textContent = d.kode;

      const locCell = row.insertCell();
      locCell.textContent = d.lokasi;

      const statusCell = row.insertCell();
      const badge = document.createElement('span');
      badge.className = `adm-badge ${d.online ? 'adm-badge-green' : 'adm-badge-gray'}`;
      badge.textContent = d.online ? 'Online' : 'Offline';
      statusCell.appendChild(badge);

      const timeCell = row.insertCell();
      timeCell.style.color = d.online ? '#64748B' : '#DC2626';
      timeCell.textContent = d.online ? 'Baru saja' : (d.last_heartbeat ? d.last_heartbeat.replace('T', ' ') : '—');

      const verCell = row.insertCell();
      verCell.style.color = '#64748B';
      verCell.textContent = d.versi || '1.0.4';

      const actCell = row.insertCell();
      const btn = document.createElement('button');
      btn.className = 'adm-btn-action-edit';
      btn.textContent = d.online ? 'Pantau Feed' : 'Ping Terminal';
      btn.onclick = () => {
        if (d.online) {
          window.location.href = 'dashboard.html';
        } else {
          showToast(`Mencoba ping ke terminal ${d.kode}...`);
        }
      };
      actCell.appendChild(btn);
    });
  } catch (err) {
    console.warn('Gagal memuat perangkat:', err);
  }
}

async function loadAdminModelStatus() {
  const list = document.getElementById('adminModelStatus');
  if (!list) return;
  try {
    const response = await fetch('/api/models/status');
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Status model AI gagal dimuat.');
    list.replaceChildren();
    const labels = {
      baju: 'Baju praktik',
      helm: 'Helm keselamatan',
      jeans: 'Celana jeans',
      sepatu: 'Sepatu safety',
      wajah: 'Verifikasi wajah'
    };
    Object.entries(result.items || {}).forEach(([name, item]) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #E2E8F0;';
      const label = document.createElement('span');
      label.textContent = labels[name] || name;
      const status = document.createElement('strong');
      status.textContent = item.ready ? 'Siap' : 'Belum tersedia';
      row.append(label, status);
      list.appendChild(row);
    });
    if (!list.childElementCount) list.textContent = 'Belum ada model AI terdaftar.';
  } catch (error) {
    list.textContent = error.message;
    showToast(error.message);
  }
}

const followupApdLabels = {
  helm: 'Helm',
  baju: 'Baju praktik',
  jeans: 'Celana jeans',
  sepatu: 'Sepatu safety'
};

async function followupRequest(url, options) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || 'Data tindak lanjut gagal diproses.');
  return result;
}

function followupDateText(value) {
  if (!value) return '—';
  return new Date(`${value}T00:00:00`).toLocaleDateString('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
}

function followupTimeText(value) {
  const time = String(value || '').replace('.', ':');
  return time.length >= 5 ? time.slice(0, 5) : '—';
}

function followupMinutesText(value) {
  return value == null ? 'Belum dihitung' : `${Number(value) || 0} menit`;
}

function followupCell(row, value) {
  const cell = document.createElement('td');
  cell.textContent = value;
  row.appendChild(cell);
  return cell;
}

function followupActionButton(label, action, callback) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.dataset.action = action;
  button.style.cssText = 'display:block;width:100%;margin:3px 0;padding:7px 10px;border:0;border-radius:7px;background:#143E6B;color:#FFF;font-size:11px;font-weight:700;cursor:pointer;';
  button.addEventListener('click', callback);
  return button;
}

function followupCaseStatus(item, hasPeriod) {
  const caseRecord = item.kasus;
  if (caseRecord) {
    if (caseRecord.status === 'draf') return `Draf SP${caseRecord.sp_level} · kejadian ke-${caseRecord.urutan_pelanggaran}`;
    if (caseRecord.status === 'diterbitkan') return `SP${caseRecord.sp_level} diterbitkan · kejadian ke-${caseRecord.urutan_pelanggaran}`;
    if (caseRecord.status === 'ditolak') return `Tidak terbukti${caseRecord.catatan ? `: ${caseRecord.catatan}` : ''}`;
  }
  if (item.atribut_belum_diperiksa.length) {
    return `Menunggu pemeriksaan: ${item.atribut_belum_diperiksa.map(name => followupApdLabels[name] || name).join(', ')}`;
  }
  if (item.atribut_tidak_sesuai.length || item.terlambat_menit > 120) {
    if (!hasPeriod) return 'Menunggu periode semester untuk menentukan SP';
    return item.terlambat_menit > 120 && !item.atribut_tidak_sesuai.length
      ? 'Menunggu konfirmasi · telat lebih dari 2 jam'
      : 'Menunggu konfirmasi petugas';
  }
  if (!item.tanggal_absensi_cocok) {
    return 'Tanggal sesi dan absensi berbeda; kompensasi perlu dikoreksi';
  }
  return 'Tidak ada pelanggaran APD';
}

function appendFollowupLetterText(parent, tagName, text) {
  const element = parent.ownerDocument.createElement(tagName);
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

function printFollowupLetter(item) {
  const caseRecord = item.kasus;
  if (!caseRecord) return;
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    showToast('Izinkan pop-up browser untuk mencetak surat peringatan.');
    return;
  }

  const doc = printWindow.document;
  doc.open();
  doc.write('<!doctype html><html lang="id"><head><meta charset="utf-8"><title>Surat Peringatan</title></head><body></body></html>');
  doc.close();
  const style = doc.createElement('style');
  style.textContent = 'body{font-family:Arial,sans-serif;color:#111;max-width:780px;margin:40px auto;line-height:1.55}header{text-align:center;white-space:pre-line;border-bottom:3px double #111;padding-bottom:14px}h1{text-align:center;font-size:20px;margin:24px 0 4px}table{width:100%;border-collapse:collapse;margin:18px 0}td{padding:7px 9px;border:1px solid #bbb;vertical-align:top}td:first-child{width:190px;font-weight:700}.draft{text-align:center;color:#b91c1c;font-weight:800;font-size:18px;border:2px solid #b91c1c;padding:8px;margin:16px 0}.signatures{display:flex;justify-content:space-between;margin-top:55px;text-align:center}.signatures div{width:42%;white-space:pre-line}@media print{body{margin:18mm auto}.draft{print-color-adjust:exact}}';
  doc.head.appendChild(style);

  const content = doc.createElement('main');
  doc.body.appendChild(content);
  appendFollowupLetterText(content, 'header', 'POLITEKNIK MANUFAKTUR BANDUNG\nSISTEM ABSENSI PRAKTIKUM');
  if (caseRecord.status === 'draf') {
    appendFollowupLetterText(content, 'div', 'DRAF — BELUM DITERBITKAN').className = 'draft';
  }
  appendFollowupLetterText(content, 'h1', `SURAT PERINGATAN SP${caseRecord.sp_level}`);
  appendFollowupLetterText(content, 'p', `Nomor: ____________________`);
  appendFollowupLetterText(content, 'p', `Periode: ${item.periode_nama || '—'} · Kejadian pelanggaran ke-${caseRecord.urutan_pelanggaran}`);
  const details = doc.createElement('table');
  content.appendChild(details);
  const addDetail = (label, value) => {
    const row = doc.createElement('tr');
    const labelCell = doc.createElement('td');
    labelCell.textContent = label;
    const valueCell = doc.createElement('td');
    valueCell.textContent = value;
    row.append(labelCell, valueCell);
    details.appendChild(row);
  };
  addDetail('Nama mahasiswa', item.nama);
  addDetail('NIM / Kelas', `${item.nim} / ${item.kelas}`);
  addDetail('Praktikum', `${item.mata_kuliah} · ${item.lab}`);
  addDetail('Tanggal sesi', followupDateText(item.tanggal));
  addDetail('Waktu masuk', `${followupDateText(item.tanggal)} ${followupTimeText(item.jam_mulai)} (jadwal), ${followupDateText(String(item.waktu).slice(0, 10))} ${String(item.waktu).slice(11, 16)} (tercatat)`);
  addDetail('APD wajib tidak sesuai', caseRecord.atribut_tidak_sesuai.map(name => followupApdLabels[name] || name).join(', '));
  if (!item.tanggal_absensi_cocok) {
    addDetail('Kompensasi', 'Tidak dihitung karena tanggal absensi berbeda dari tanggal sesi; perlu koreksi manual.');
  } else if (caseRecord.terlambat_menit > 0) {
    addDetail('Keterlambatan', `${caseRecord.terlambat_menit} menit`);
    addDetail('Kompensasi', `${caseRecord.kompensasi_menit} menit`);
  }
  appendFollowupLetterText(content, 'p', 'Mahasiswa yang bersangkutan diminta memperhatikan ketentuan keselamatan dan tata tertib praktikum yang berlaku.');
  const signatures = doc.createElement('div');
  signatures.className = 'signatures';
  appendFollowupLetterText(signatures, 'div', 'Mahasiswa\n\n\n(____________________)');
  appendFollowupLetterText(signatures, 'div', 'Petugas PLP / Dosen\n\n\n(____________________)');
  content.appendChild(signatures);
  printWindow.focus();
  setTimeout(() => printWindow.print(), 250);
}

async function handleFollowupAction(action, item) {
  try {
    if (action === 'print') {
      printFollowupLetter(item);
      return;
    }
    if (action === 'confirm') {
      const result = await followupRequest(`/api/follow-up/${item.id}/confirm`, { method: 'POST' });
      showToast(`Draf SP${result.case.sp_level} berhasil dibuat.`);
    } else if (action === 'dismiss') {
      const note = window.prompt('Tuliskan alasan pelanggaran tidak terbukti:');
      if (note === null) return;
      await followupRequest(`/api/follow-up/${item.id}/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ catatan: note })
      });
      showToast('Pemeriksaan disimpan sebagai tidak terbukti.');
    } else if (action === 'issue') {
      if (!window.confirm(`Terbitkan SP${item.kasus.sp_level} untuk ${item.nama}?`)) return;
      await followupRequest(`/api/follow-up/cases/${item.kasus.id}/issue`, { method: 'POST' });
      showToast('Surat peringatan diterbitkan.');
    }
    await loadFollowupPage();
  } catch (error) {
    showToast(error.message);
  }
}

function renderFollowupSummary(attendance, hasPeriod) {
  const container = document.getElementById('followupSummary');
  if (!container) return;
  const lateCount = attendance.filter(item => item.terlambat_menit > 0).length;
  const compensation = attendance.reduce((sum, item) => sum + (item.kompensasi_menit || 0), 0);
  const dateMismatch = attendance.filter(item => !item.tanggal_absensi_cocok).length;
  const isPendingViolation = item => !item.kasus && !item.atribut_belum_diperiksa.length
    && (item.atribut_tidak_sesuai.length || item.terlambat_menit > 120);
  const waiting = hasPeriod ? attendance.filter(isPendingViolation).length : 0;
  const pendingPeriod = hasPeriod ? 0 : attendance.filter(isPendingViolation).length;
  const drafts = attendance.filter(item => item.kasus && item.kasus.status === 'draf').length;
  const issued = attendance.filter(item => item.kasus && item.kasus.status === 'diterbitkan').length;
  const values = [
    ['Absensi terlambat', lateCount],
    ['Total kompensasi', followupMinutesText(compensation)],
    ['Perlu koreksi tanggal', dateMismatch],
    ['Menunggu konfirmasi SP', waiting],
    ['Menunggu periode semester', pendingPeriod],
    ['Draf / diterbitkan', `${drafts} / ${issued}`]
  ];
  container.replaceChildren();
  values.forEach(([label, value]) => {
    const card = document.createElement('section');
    card.className = 'adm-card-white';
    card.style.cssText = 'padding:16px 18px;';
    const title = document.createElement('div');
    title.style.cssText = 'color:#64748B;font-size:11px;font-weight:700;';
    title.textContent = label;
    const amount = document.createElement('div');
    amount.style.cssText = 'margin-top:7px;color:#0F172A;font-size:21px;font-weight:800;';
    amount.textContent = value;
    card.append(title, amount);
    container.appendChild(card);
  });
}

function renderFollowupAttendance(attendance, canManage, hasPeriod) {
  const body = document.getElementById('followupTableBody');
  if (!body) return;
  body.replaceChildren();
  if (!attendance.length) {
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 8;
    cell.textContent = hasPeriod
      ? 'Belum ada absensi pada periode semester ini.'
      : 'Belum ada data absensi tersimpan.';
    return;
  }

  attendance.forEach(item => {
    const row = body.insertRow();
    const sessionCell = followupCell(row, `${followupDateText(item.tanggal)} · ${item.mata_kuliah}`);
    sessionCell.style.fontWeight = '700';
    const studentCell = followupCell(row, `${item.nama} · ${item.nim} · ${item.kelas}`);
    const timeCell = followupCell(row, `${followupTimeText(item.jam_mulai)} / ${followupDateText(String(item.waktu).slice(0, 10))} ${String(item.waktu).slice(11, 16)}`);
    timeCell.style.whiteSpace = 'nowrap';
    followupCell(row, item.tanggal_absensi_cocok
      ? followupMinutesText(item.terlambat_menit)
      : 'Perlu koreksi tanggal');
    followupCell(row, item.tanggal_absensi_cocok
      ? followupMinutesText(item.kompensasi_menit)
      : 'Tidak dihitung');

    const apdItems = [];
    if (item.atribut_tidak_sesuai.length) {
      apdItems.push(`Tidak sesuai: ${item.atribut_tidak_sesuai.map(name => followupApdLabels[name] || name).join(', ')}`);
    }
    if (item.atribut_belum_diperiksa.length) {
      apdItems.push(`Belum diperiksa: ${item.atribut_belum_diperiksa.map(name => followupApdLabels[name] || name).join(', ')}`);
    }
    if (!item.tanggal_absensi_cocok) {
      apdItems.push('Tanggal sesi/absensi berbeda; perlu koreksi manual');
    }
    followupCell(row, apdItems.join(' · ') || 'Semua atribut wajib sesuai');
    followupCell(row, followupCaseStatus(item, hasPeriod));
    const actions = document.createElement('td');
    actions.style.minWidth = '150px';
    if (canManage) {
      if (hasPeriod && !item.kasus && !item.atribut_belum_diperiksa.length
        && (item.atribut_tidak_sesuai.length || item.terlambat_menit > 120)) {
        actions.append(
          followupActionButton('Konfirmasi & buat draf SP', 'confirm', () => handleFollowupAction('confirm', item)),
          followupActionButton('Tandai tidak terbukti', 'dismiss', () => handleFollowupAction('dismiss', item))
        );
      } else if (item.kasus && item.kasus.status === 'draf') {
        actions.append(
          followupActionButton('Cetak draf', 'print', () => handleFollowupAction('print', item)),
          followupActionButton('Setujui & terbitkan', 'issue', () => handleFollowupAction('issue', item))
        );
      } else if (item.kasus && item.kasus.status === 'diterbitkan') {
        actions.append(followupActionButton('Cetak surat', 'print', () => handleFollowupAction('print', item)));
      }
    }
    if (!actions.childElementCount) actions.textContent = '—';
    row.appendChild(actions);
  });
}

async function loadFollowupPage() {
  const result = await followupRequest('/api/follow-up');
  const periodInfo = document.getElementById('followupPeriodInfo');
  const form = document.getElementById('followupPeriodForm');
  const newPeriodButton = document.getElementById('followupNewPeriodButton');
  const hasPeriod = Boolean(result.period);
  if (periodInfo) {
    periodInfo.textContent = hasPeriod
      ? `${result.period.nama} · ${followupDateText(result.period.tanggal_mulai)} – ${followupDateText(result.period.tanggal_selesai)}`
      : 'Belum ada periode semester aktif.';
  }
  if (form) {
    form.hidden = hasPeriod || !result.can_manage;
    form.style.display = form.hidden ? 'none' : 'grid';
  }
  if (newPeriodButton) {
    newPeriodButton.hidden = !hasPeriod || !result.can_manage;
    newPeriodButton.onclick = () => {
      if (!form) return;
      form.hidden = !form.hidden;
      form.style.display = form.hidden ? 'none' : 'grid';
    };
  }
  renderFollowupSummary(result.attendance || [], hasPeriod);
  renderFollowupAttendance(result.attendance || [], result.can_manage, hasPeriod);
}

function initFollowupPage() {
  const form = document.getElementById('followupPeriodForm');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const values = new FormData(form);
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
      await followupRequest('/api/follow-up/periods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nama: values.get('nama'),
          tanggal_mulai: values.get('tanggal_mulai'),
          tanggal_selesai: values.get('tanggal_selesai')
        })
      });
      form.reset();
      showToast('Periode semester berhasil diaktifkan.');
      await loadFollowupPage();
    } catch (error) {
      showToast(error.message);
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
  loadFollowupPage().catch(error => {
    const info = document.getElementById('followupPeriodInfo');
    if (info) info.textContent = error.message;
    showToast(error.message);
  });
}

document.addEventListener('DOMContentLoaded', initFollowupPage);

function updateAdminIdentity(user) {
  const role = String(user.peran || '').toLowerCase();
  const roleLabels = { operator: 'Operator Pos', dosen: 'Dosen', plp: 'PLP' };
  const name = document.querySelector('.adm-user-name');
  const subtitle = document.querySelector('.adm-user-sub');
  const avatar = document.querySelector('.adm-avatar-circle');
  if (name) name.textContent = user.nama;
  if (subtitle) subtitle.textContent = roleLabels[role] || user.peran;
  if (avatar) {
    avatar.textContent = String(user.nama || '')
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0])
      .join('')
      .toUpperCase();
  }

  document.querySelectorAll('.adm-nav-counter').forEach(counter => counter.remove());
  const notificationButton = document.querySelector('.adm-notif-btn');
  if (notificationButton) {
    notificationButton.onclick = () => showToast('Notifikasi belum tersedia karena belum ada data notifikasi tersimpan.');
    notificationButton.title = 'Notifikasi belum tersedia';
    const dot = notificationButton.querySelector('.adm-notif-dot');
    if (dot) dot.remove();
  }
  if (role === 'operator') {
    document.querySelectorAll('.adm-nav-list a[href="laporan.html"]').forEach(link => {
      link.hidden = true;
    });
  }
}

function dashboardText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function dashboardDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('id-ID', {
    weekday: 'short',
    day: '2-digit',
    month: 'short'
  });
}

function renderDashboardRows(container, items, renderRow, emptyMessage) {
  if (!container) return;
  container.replaceChildren();
  if (!items.length) {
    const row = document.createElement('div');
    row.style.cssText = 'color:#64748B;font-size:12px;padding:8px 0;';
    row.textContent = emptyMessage;
    container.appendChild(row);
    return;
  }
  items.forEach(item => container.appendChild(renderRow(item)));
}

async function loadAdminDashboard() {
  const recentBody = document.getElementById('dashboardRecentAttendance');
  if (!recentBody) return;
  recentBody.replaceChildren();
  const periodSelect = document.getElementById('dashboardPeriod');
  const period = periodSelect ? periodSelect.value : 'today';
  try {
    const response = await fetch(`/api/dashboard/summary?period=${encodeURIComponent(period)}`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Ringkasan dashboard gagal dimuat.');

    dashboardText('dashboardDate', new Date().toLocaleDateString('id-ID', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric'
    }));
    dashboardText(
      'dashboardStatusLabel',
      periodSelect.options[periodSelect.selectedIndex].text
    );
    dashboardText('dashboardStudentCount', result.mahasiswa);
    dashboardText('dashboardSessionCount', result.total_sesi);
    dashboardText('dashboardPendingCount', result.menunggu_validasi);
    dashboardText('dashboardAttendanceCount', result.total_absensi);
    dashboardText('dashboardStatusTotal', result.total_absensi);
    dashboardText('dashboardStatusComplete', result.lengkap);
    dashboardText('dashboardStatusPending', result.menunggu_validasi);
    dashboardText('dashboardStatusIncomplete', result.kurang);
    dashboardText('sessionsTodayCount', `${result.sessions_today.length} sesi praktikum`);

    // Update Live Monitoring Kiosk Feed & Status
    const kioskDevices = result.kiosk_devices || [];
    const activeKiosk = kioskDevices.find(d => d.online) || kioskDevices[0];
    const badgeEl = document.getElementById('kioskStatusBadge');
    const feedImg = document.getElementById('kioskLiveFeedImg');
    const deviceLabel = document.getElementById('kioskDeviceLabel');
    const actText = document.getElementById('kioskActivityText');

    if (activeKiosk) {
      if (deviceLabel) deviceLabel.textContent = `${activeKiosk.kode} · ${activeKiosk.nama} (${activeKiosk.lokasi})`;
      if (badgeEl) {
        if (activeKiosk.online) {
          badgeEl.className = 'adm-badge adm-badge-green';
          badgeEl.textContent = '● Kiosk Online · Kamera Aktif';
        } else {
          badgeEl.className = 'adm-badge adm-badge-gray';
          badgeEl.textContent = '○ Kiosk Offline';
        }
      }
      if (actText) {
        actText.textContent = activeKiosk.aktivitas_terakhir || (activeKiosk.online ? 'Siaga mendeteksi' : 'Terminal offline');
      }
      if (feedImg && activeKiosk.frame_snapshot) {
        feedImg.src = activeKiosk.frame_snapshot;
      }
    } else {
      if (badgeEl) {
        badgeEl.className = 'adm-badge adm-badge-gray';
        badgeEl.textContent = 'Belum terhubung';
      }
      if (actText) {
        actText.textContent = 'Menunggu koneksi dari terminal PC Kiosk di lab.';
      }
    }
    dashboardText('sessionsTodayActive', result.sessions_today.filter(item => item.aktif).length);
    dashboardText('sessionsTodayInactive', result.sessions_today.filter(item => !item.aktif).length);
    dashboardText(
      'sessionsTodayList',
      new Set(result.sessions_today.map(item => item.kelas)).size
    );

    recentBody.replaceChildren();
    if (!result.recent.length) {
      const row = recentBody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 7;
      cell.textContent = 'Belum ada catatan absensi pada rentang ini.';
    } else {
      result.recent.forEach(item => {
        const row = recentBody.insertRow();
        const time = new Date(item.waktu);
        [
          time.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }),
          item.nim,
          item.nama,
          item.kelas,
          item.mata_kuliah,
          'Hadir'
        ].forEach(value => {
          const cell = row.insertCell();
          cell.textContent = value || '—';
        });
        const statusCell = row.insertCell();
        const badge = document.createElement('span');
        badge.className = `adm-badge ${item.status === 'lengkap' ? 'adm-badge-green' : item.status === 'kurang' ? 'adm-badge-red' : 'adm-badge-amber'}`;
        badge.textContent = item.status === 'lengkap' ? 'Lengkap' : item.status === 'kurang' ? 'Tidak lengkap' : 'Menunggu validasi';
        statusCell.appendChild(badge);
      });
    }

    renderDashboardRows(
      document.getElementById('validationQueue'),
      result.validation_queue,
      item => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:#F8FAFC;border-radius:8px;';
        const details = document.createElement('div');
        const name = document.createElement('div');
        name.style.cssText = 'font-weight:700;font-size:13px;';
        name.textContent = `${item.nama} (${item.kelas})`;
        const session = document.createElement('div');
        session.style.cssText = 'font-size:11.5px;color:#D97706;';
        session.textContent = item.mata_kuliah;
        details.append(name, session);
        const link = document.createElement('a');
        link.className = 'adm-btn-action-edit';
        link.href = 'absensi.html';
        link.textContent = 'Tinjau';
        row.append(details, link);
        return row;
      },
      'Tidak ada absensi yang menunggu validasi.'
    );

    const trend = new Map(result.trend.map(item => [item.tanggal, item]));
    const trendRows = [];
    for (let offset = 5; offset >= 0; offset--) {
      const day = new Date();
      day.setDate(day.getDate() - offset);
      const key = new Date(day.getTime() - day.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
      trendRows.push(trend.get(key) || { tanggal: key, lengkap: 0, kurang: 0, menunggu: 0 });
    }
    renderDashboardRows(
      document.getElementById('attendanceTrend'),
      trendRows,
      item => {
        const total = item.lengkap + item.kurang + item.menunggu;
        const line = document.createElement('div');
        line.style.cssText = 'display:grid;grid-template-columns:52px 1fr 30px;align-items:center;gap:8px;font-size:11px;color:#64748B;';
        const label = document.createElement('span');
        label.textContent = dashboardDate(item.tanggal);
        const bar = document.createElement('div');
        bar.style.cssText = 'display:flex;height:10px;background:#E2E8F0;border-radius:5px;overflow:hidden;';
        const max = Math.max(1, ...trendRows.map(entry => entry.lengkap + entry.kurang + entry.menunggu));
        [
          [item.lengkap, '#0284C7'],
          [item.kurang, '#DC2626'],
          [item.menunggu, '#D97706']
        ].forEach(([count, color]) => {
          const segment = document.createElement('span');
          segment.style.cssText = `width:${(count / max) * 100}%;background:${color};`;
          bar.appendChild(segment);
        });
        const count = document.createElement('span');
        count.textContent = total;
        line.append(label, bar, count);
        return line;
      },
      'Belum ada data tren.'
    );
  } catch (error) {
    const row = recentBody.insertRow();
    const cell = row.insertCell();
    cell.colSpan = 7;
    cell.textContent = error.message;
    showToast(error.message);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadAdminDashboard();
  // Polling otomatis setiap 3 detik untuk memperbarui live feed monitoring kiosk & data absensi
  if (document.getElementById('kioskMonitoringCard')) {
    setInterval(loadAdminDashboard, 3000);
  }
});

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

// Filtering for Monitoring Absensi by search text, class, and APD status.
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

let canReviewJeans = false;

function setAttendanceTableMessage(message) {
  const body = document.getElementById('attendanceTableBody');
  if (!body) return;
  body.replaceChildren();
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 8;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function attendanceStatusText(status) {
  return {
    lengkap: 'Lengkap',
    kurang: 'Tidak lengkap',
    menunggu_validasi: 'Menunggu validasi jeans'
  }[status] || status;
}

function attendanceJeansText(value, required) {
  if (!required) return 'Tidak wajib';
  if (value === null) return 'Menunggu penilaian';
  return value ? 'Sesuai' : 'Tidak sesuai';
}

function attendanceTimeText(value) {
  const parsed = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(parsed);
}

function updateAttendanceClassFilter(records) {
  const select = document.getElementById('filterKelasAbsensi');
  if (!select) return;
  const selected = select.value;
  const classes = [...new Set(records.map(item => item.kelas))].sort();
  select.replaceChildren(new Option('Semua kelas', 'all'));
  classes.forEach(kelas => select.add(new Option(kelas, kelas)));
  select.value = classes.includes(selected) ? selected : 'all';
}

function renderAttendanceMonitor(records) {
  const body = document.getElementById('attendanceTableBody');
  if (!body) return;
  body.replaceChildren();
  updateAttendanceClassFilter(records);

  if (records.length === 0) {
    setAttendanceTableMessage('Belum ada data absensi tersimpan.');
    return;
  }

  records.forEach(item => {
    const row = document.createElement('tr');
    row.dataset.id = item.id;
    row.dataset.kelas = item.kelas;
    row.dataset.status = item.status;
    [
      attendanceTimeText(item.waktu),
      item.nim,
      item.nama,
      item.kelas,
      item.mata_kuliah
    ].forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 0) cell.style.color = '#64748B';
      if (index === 1 || index === 2) cell.style.fontWeight = '700';
      row.appendChild(cell);
    });

    const jeansCell = document.createElement('td');
    const jeansRequired = item.wajib.includes('jeans');
    jeansCell.textContent = attendanceJeansText(item.jeans, jeansRequired);
    row.appendChild(jeansCell);

    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    const badgeClass = item.status === 'lengkap'
      ? 'adm-badge-green'
      : item.status === 'menunggu_validasi' ? 'adm-badge-blue' : 'adm-badge-red';
    statusBadge.className = `adm-badge ${badgeClass} status-badge`;
    statusBadge.textContent = attendanceStatusText(item.status);
    statusCell.appendChild(statusBadge);
    row.appendChild(statusCell);

    const actionCell = document.createElement('td');
    if (canReviewJeans && jeansRequired) {
      const select = document.createElement('select');
      select.className = 'adm-select-dropdown';
      select.setAttribute('aria-label', `Hasil jeans ${item.nama} (${item.nim})`);
      select.add(new Option('Pilih hasil', ''));
      select.add(new Option('Sesuai', '1'));
      select.add(new Option('Tidak sesuai', '0'));
      select.value = item.jeans === null ? '' : String(item.jeans);

      const saveButton = document.createElement('button');
      saveButton.type = 'button';
      saveButton.className = 'adm-btn-action-edit';
      saveButton.textContent = 'Simpan';
      const initialValue = select.value;
      saveButton.disabled = true;
      select.addEventListener('change', () => {
        saveButton.disabled = select.value === '' || select.value === initialValue;
      });
      saveButton.addEventListener('click', () => {
        saveManualJeansResult(item.id, select, saveButton);
      });
      actionCell.append(select, saveButton);
    } else {
      actionCell.textContent = jeansRequired ? 'Khusus PLP' : '—';
    }
    row.appendChild(actionCell);
    body.appendChild(row);
  });
  applyAbsensiFilters();
}

async function loadAttendanceSessions() {
  const select = document.getElementById('filterSesiAbsensi');
  if (!select) return;
  try {
    const response = await fetch('/api/sessions?aktif=0');
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Daftar sesi gagal dimuat.');

    const selected = select.value;
    select.replaceChildren(new Option('Semua sesi praktikum', 'all'));
    result.sessions.forEach(item => {
      const label = `${item.mata_kuliah} · ${item.kelas} · ${item.lab} · ${item.tanggal}`;
      select.add(new Option(label, String(item.id)));
    });
    select.value = result.sessions.some(item => String(item.id) === selected)
      ? selected
      : 'all';
  } catch (error) {
    select.replaceChildren(new Option('Daftar sesi gagal dimuat', 'all'));
    showToast(error.message);
  }
}

async function loadAttendanceMonitor() {
  try {
    const sessionSelect = document.getElementById('filterSesiAbsensi');
    const sessionId = sessionSelect ? sessionSelect.value : 'all';
    const params = new URLSearchParams();
    if (sessionId && sessionId !== 'all') params.set('sesi_id', sessionId);
    const query = params.toString();
    const response = await fetch(`/api/absensi${query ? `?${query}` : ''}`);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Data absensi gagal dimuat.');
    if (result.attendance.length === 0 && sessionId !== 'all') {
      const sessionName = sessionSelect.options[sessionSelect.selectedIndex].text;
      setAttendanceTableMessage(`Belum ada data absensi untuk sesi ${sessionName}.`);
      return;
    }
    renderAttendanceMonitor(result.attendance);
  } catch (error) {
    setAttendanceTableMessage(error.message);
    showToast(error.message);
  }
}

async function saveManualJeansResult(attendanceId, select, button) {
  if (!select.value) return;
  button.disabled = true;
  try {
    const response = await fetch(`/api/absensi/${attendanceId}/jeans`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jeans: Number(select.value) })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Hasil pemeriksaan jeans gagal disimpan.');
    showToast('Hasil pemeriksaan jeans berhasil disimpan.');
    await loadAttendanceMonitor();
  } catch (error) {
    showToast(error.message);
    button.disabled = false;
  }
}

async function initAttendanceMonitor() {
  if (!document.getElementById('tableMonitoringAbsensi')) return;
  try {
    const response = await fetch('/api/auth/me');
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.user) {
      window.location.href = '/login.html';
      return;
    }
    canReviewJeans = result.user.peran.toLowerCase() === 'plp';
    await loadAttendanceSessions();
    await loadAttendanceMonitor();
  } catch (error) {
    setAttendanceTableMessage(error.message);
  }
}

document.addEventListener('DOMContentLoaded', initAttendanceMonitor);

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

let mahasiswaEditingNim = null;
let mahasiswaCanEdit = false;

async function mahasiswaApi(url, options) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || 'Permintaan data mahasiswa gagal.');
  }
  return result;
}

function setMahasiswaMessage(message) {
  const body = document.getElementById('tabelMahasiswaBody');
  if (!body) return;
  body.replaceChildren();
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 5;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function updateMahasiswaClassFilter(students) {
  const select = document.getElementById('filterKelasMhs');
  if (!select) return;
  const selected = select.value;
  const classes = [...new Set(students.map(student => student.kelas))].sort();
  select.replaceChildren(new Option('Semua kelas', 'semua'));
  classes.forEach(kelas => select.add(new Option(kelas, kelas)));
  select.value = classes.includes(selected) ? selected : 'semua';
}

function renderMahasiswa(students) {
  const body = document.getElementById('tabelMahasiswaBody');
  if (!body) return;
  body.replaceChildren();
  updateMahasiswaClassFilter(students);

  if (students.length === 0) {
    setMahasiswaMessage('Belum ada data mahasiswa.');
    return;
  }

  students.forEach(student => {
    const row = document.createElement('tr');
    row.dataset.kelas = student.kelas;

    [student.nim, student.nama, student.kelas].forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 0) cell.style.color = '#64748B';
      if (index === 1) cell.style.fontWeight = '700';
      row.appendChild(cell);
    });

    const accountCell = document.createElement('td');
    const accountBadge = document.createElement('span');
    accountBadge.className = `adm-badge ${student.has_account ? 'adm-badge-green' : 'adm-badge-amber'}`;
    accountBadge.textContent = student.has_account ? 'Dibuat' : 'Belum dibuat';
    accountCell.appendChild(accountBadge);
    row.appendChild(accountCell);

    const actions = document.createElement('td');
    if (mahasiswaCanEdit) {
      const editButton = document.createElement('button');
      editButton.type = 'button';
      editButton.className = 'adm-btn-action-edit';
      editButton.textContent = student.has_account ? 'Edit' : 'Buat akun';
      editButton.addEventListener('click', () => openMahasiswaForm(student));

      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'adm-btn-action-delete';
      deleteButton.textContent = 'Hapus';
      deleteButton.addEventListener('click', () => deleteMahasiswa(student));
      actions.append(editButton, deleteButton);
    } else {
      actions.textContent = 'Hanya lihat';
    }
    row.appendChild(actions);
    body.appendChild(row);
  });
  filterAdmTable('tableMhs', 'searchMhs', 'filterKelasMhs', null);
}

async function loadMahasiswa() {
  try {
    const result = await mahasiswaApi('/api/mahasiswa');
    renderMahasiswa(result.mahasiswa);
  } catch (error) {
    setMahasiswaMessage(error.message);
    showToast(error.message);
  }
}

function openMahasiswaForm(student) {
  if (!mahasiswaCanEdit) return;
  const form = document.getElementById('formMahasiswa');
  const nimInput = document.getElementById('mahasiswaNim');
  const passwordInput = document.getElementById('mahasiswaPassword');
  mahasiswaEditingNim = student ? student.nim : null;
  form.reset();
  nimInput.disabled = Boolean(student);
  nimInput.value = student ? student.nim : '';
  document.getElementById('mahasiswaNama').value = student ? student.nama : '';
  document.getElementById('mahasiswaKelas').value = student ? student.kelas : '';
  passwordInput.required = !student || !student.has_account;
  document.getElementById('mahasiswaPasswordHint').textContent = !student || !student.has_account
    ? 'Wajib untuk membuat akun portal. Berikan secara aman; pendaftaran wajah dilakukan terpisah.'
    : 'Kosongkan jika kata sandi tidak ingin diubah. Pendaftaran wajah dikelola terpisah.';
  document.getElementById('mahasiswaFormEyebrow').textContent = student ? 'Data Pengguna' : 'Tambah Data';
  document.getElementById('mahasiswaFormTitle').textContent = student
    ? student.has_account ? 'Ubah Data Mahasiswa' : 'Buat Akun Mahasiswa'
    : 'Data & Akun Mahasiswa Baru';
  form.querySelector('button[type="submit"]').textContent = student && student.has_account
    ? 'Simpan Perubahan'
    : 'Simpan Data & Akun';
  openAdmModal('modalTambahMahasiswa');
}

async function deleteMahasiswa(student) {
  if (!mahasiswaCanEdit || !window.confirm(`Hapus data mahasiswa ${student.nama} (${student.nim})?`)) {
    return;
  }
  try {
    await mahasiswaApi(`/api/mahasiswa/${encodeURIComponent(student.nim)}`, { method: 'DELETE' });
    showToast('Data mahasiswa berhasil dihapus.');
    await loadMahasiswa();
  } catch (error) {
    showToast(error.message);
  }
}

async function submitMahasiswaForm(event) {
  event.preventDefault();
  if (!mahasiswaCanEdit) return;

  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const isEditing = Boolean(mahasiswaEditingNim);
  const payload = {
    nama: document.getElementById('mahasiswaNama').value.trim(),
    kelas: document.getElementById('mahasiswaKelas').value.trim()
  };
  const password = document.getElementById('mahasiswaPassword').value;
  if (!isEditing) {
    payload.nim = document.getElementById('mahasiswaNim').value.trim();
  }
  if (!isEditing || password) payload.password = password;

  submitButton.disabled = true;
  try {
    await mahasiswaApi(
      isEditing ? `/api/mahasiswa/${encodeURIComponent(mahasiswaEditingNim)}` : '/api/mahasiswa',
      {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    );
    closeAdmModal('modalTambahMahasiswa');
    showToast(isEditing && !password
      ? 'Data mahasiswa berhasil diperbarui.'
      : 'Data mahasiswa dan akun portal berhasil disimpan.');
    await loadMahasiswa();
  } catch (error) {
    showToast(error.message);
  } finally {
    submitButton.disabled = false;
  }
}

async function initMahasiswaPage() {
  if (!document.getElementById('tableMhs')) return;
  try {
    const result = await mahasiswaApi('/api/auth/me');
    mahasiswaCanEdit = Boolean(result.user && result.user.peran.toLowerCase() === 'operator');
    const addButton = document.getElementById('btnTambahMahasiswa');
    addButton.hidden = !mahasiswaCanEdit;
    await loadMahasiswa();
  } catch (error) {
    setMahasiswaMessage(error.message);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('formMahasiswa');
  if (form) form.addEventListener('submit', submitMahasiswaForm);
  initMahasiswaPage();
});

let academicEditingId = null;
let academicCanEdit = false;

async function academicApi(url, options) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || 'Permintaan data gagal.');
  }
  return result;
}

function setAcademicTableMessage(message) {
  const body = document.getElementById('tabelJadwalBody');
  if (!body) return;
  body.replaceChildren();
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 8;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function updateAcademicClassFilter(sessions) {
  const select = document.getElementById('filterKelasJadwal');
  if (!select) return;
  const selected = select.value;
  const classes = [...new Set(sessions.map(item => item.kelas))].sort();
  select.replaceChildren(new Option('Semua kelas', 'semua'));
  classes.forEach(kelas => select.add(new Option(kelas, kelas)));
  select.value = classes.includes(selected) ? selected : 'semua';
}

function academicDateLabel(value) {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  }).format(parsed);
}

function renderAcademicSessions(sessions) {
  const body = document.getElementById('tabelJadwalBody');
  if (!body) return;
  body.replaceChildren();
  updateAcademicClassFilter(sessions);

  if (sessions.length === 0) {
    setAcademicTableMessage('Belum ada sesi praktikum.');
    return;
  }

  sessions.forEach(item => {
    const row = document.createElement('tr');
    row.dataset.kelas = item.kelas;
    [
      academicDateLabel(item.tanggal),
      `${item.jam_mulai}–${item.jam_selesai}`,
      item.kelas,
      item.mata_kuliah,
      item.dosen,
      item.ruang
    ].forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 1) cell.style.fontWeight = '700';
      row.appendChild(cell);
    });

    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `adm-badge ${item.aktif ? 'adm-badge-green' : 'adm-badge-amber'}`;
    statusBadge.textContent = item.aktif ? 'Aktif' : 'Nonaktif';
    statusCell.appendChild(statusBadge);
    row.appendChild(statusCell);

    const actions = document.createElement('td');
    if (academicCanEdit) {
      const editButton = document.createElement('button');
      editButton.type = 'button';
      editButton.className = 'adm-btn-action-edit';
      editButton.textContent = 'Edit';
      editButton.addEventListener('click', () => openAcademicSessionForm(item));

      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'adm-btn-action-delete';
      deleteButton.textContent = 'Hapus';
      deleteButton.addEventListener('click', () => deleteAcademicSession(item));
      actions.append(editButton, deleteButton);
    } else {
      actions.textContent = '—';
    }
    row.appendChild(actions);
    body.appendChild(row);
  });
  filterAdmTable('tableJadwal', 'searchJadwal', 'filterKelasJadwal', null);
}

async function loadAcademicSessions() {
  try {
    const result = await academicApi('/api/sessions?aktif=0');
    renderAcademicSessions(result.sessions);
  } catch (error) {
    setAcademicTableMessage(error.message);
    showToast(error.message);
  }
}

async function initAcademicSessions() {
  if (!document.getElementById('tableJadwal')) return;
  try {
    const result = await academicApi('/api/auth/me');
    academicCanEdit = Boolean(
      result.user && ['operator', 'admin', 'dosen', 'plp'].includes(result.user.peran.toLowerCase())
    );
    document.getElementById('btnActionTop').hidden =
      !academicCanEdit || currentTopAction === 'Kelola aturan';
    await loadAcademicSessions();
  } catch (error) {
    setAcademicTableMessage(error.message);
  }
}

function openAcademicSessionForm(item) {
  if (!academicCanEdit) return;
  const form = document.getElementById('formJadwalAkademik');
  form.reset();
  academicEditingId = item ? item.id : null;
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
  document.getElementById('jadwalTanggal').value = item ? item.tanggal : localDate;
  document.getElementById('jadwalLab').value = item ? item.lab : 'Manufaktur';
  document.getElementById('jadwalJamMulai').value = item ? item.jam_mulai.replace('.', ':') : '';
  document.getElementById('jadwalJamSelesai').value = item ? item.jam_selesai.replace('.', ':') : '';
  document.getElementById('jadwalKelas').value = item ? item.kelas : '';
  document.getElementById('jadwalMataKuliah').value = item ? item.mata_kuliah : '';
  document.getElementById('jadwalDosen').value = item ? item.dosen : '';
  document.getElementById('jadwalRuang').value = item ? item.ruang : '';
  document.getElementById('jadwalAktif').value = item ? String(item.aktif) : '1';

  // Checklist APD Sesi
  const wHelm = document.getElementById('jadwalWajibHelm');
  const wBaju = document.getElementById('jadwalWajibBaju');
  const wJeans = document.getElementById('jadwalWajibJeans');
  const wSepatu = document.getElementById('jadwalWajibSepatu');
  if (wHelm) wHelm.checked = item ? (item.wajib_helm !== undefined ? Boolean(item.wajib_helm) : true) : true;
  if (wBaju) wBaju.checked = item ? (item.wajib_baju !== undefined ? Boolean(item.wajib_baju) : true) : true;
  if (wJeans) wJeans.checked = item ? (item.wajib_jeans !== undefined ? Boolean(item.wajib_jeans) : true) : true;
  if (wSepatu) wSepatu.checked = item ? (item.wajib_sepatu !== undefined ? Boolean(item.wajib_sepatu) : true) : true;

  document.getElementById('jadwalFormEyebrow').textContent = item ? 'Ubah Data' : 'Tambah Data';
  document.getElementById('jadwalFormTitle').textContent = item ? 'Ubah Jadwal Akademik' : 'Jadwal Akademik Baru';
  document.getElementById('btnSubmitJadwal').textContent = item ? 'Simpan Perubahan' : 'Simpan Jadwal';
  openAdmModal('modalEditJadwal');
}

async function deleteAcademicSession(item) {
  if (!academicCanEdit || !window.confirm(`Hapus sesi ${item.mata_kuliah} untuk kelas ${item.kelas}?`)) {
    return;
  }
  try {
    await academicApi(`/api/sessions/${item.id}`, { method: 'DELETE' });
    showToast('Sesi praktikum berhasil dihapus.');
    await loadAcademicSessions();
  } catch (error) {
    showToast(error.message);
  }
}

async function submitAcademicSession(event) {
  event.preventDefault();
  if (!academicCanEdit) return;

  const form = event.currentTarget;
  const submitButton = document.getElementById('btnSubmitJadwal');
  const payload = {
    lab: document.getElementById('jadwalLab').value,
    mata_kuliah: document.getElementById('jadwalMataKuliah').value.trim(),
    kelas: document.getElementById('jadwalKelas').value.trim(),
    tanggal: document.getElementById('jadwalTanggal').value,
    jam_mulai: document.getElementById('jadwalJamMulai').value,
    jam_selesai: document.getElementById('jadwalJamSelesai').value,
    dosen: document.getElementById('jadwalDosen').value.trim(),
    ruang: document.getElementById('jadwalRuang').value.trim(),
    aktif: Number(document.getElementById('jadwalAktif').value),
    wajib_helm: document.getElementById('jadwalWajibHelm') && document.getElementById('jadwalWajibHelm').checked ? 1 : 0,
    wajib_baju: document.getElementById('jadwalWajibBaju') && document.getElementById('jadwalWajibBaju').checked ? 1 : 0,
    wajib_jeans: document.getElementById('jadwalWajibJeans') && document.getElementById('jadwalWajibJeans').checked ? 1 : 0,
    wajib_sepatu: document.getElementById('jadwalWajibSepatu') && document.getElementById('jadwalWajibSepatu').checked ? 1 : 0
  };
  const isEditing = academicEditingId !== null;

  submitButton.disabled = true;
  try {
    await academicApi(
      isEditing ? `/api/sessions/${academicEditingId}` : '/api/sessions',
      {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    );
    closeAdmModal('modalEditJadwal');
    showToast(isEditing ? 'Jadwal berhasil diperbarui.' : 'Jadwal berhasil ditambahkan.');
    await loadAcademicSessions();
  } catch (error) {
    showToast(error.message);
  } finally {
    submitButton.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('formJadwalAkademik');
  if (form) form.addEventListener('submit', submitAcademicSession);
  initAcademicSessions();
});

let apdRulesCanEdit = false;

function setApdRulesMessage(message) {
  const body = document.getElementById('tabelAturanApd');
  if (!body) return;
  body.replaceChildren();
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 8;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function updateApdRuleLabFilter(rules) {
  const select = document.getElementById('filterLabAturan');
  if (!select) return;
  const selected = select.value;
  select.replaceChildren(new Option('Semua laboratorium', 'semua'));
  rules.forEach(rule => select.add(new Option(rule.lab, rule.lab)));
  select.value = rules.some(rule => rule.lab === selected) ? selected : 'semua';
}

function apdRuleValue(required) {
  return required ? 'Wajib' : 'Tidak diperiksa';
}

function renderApdRules(rules) {
  const body = document.getElementById('tabelAturanApd');
  if (!body) return;
  body.replaceChildren();
  updateApdRuleLabFilter(rules);

  if (rules.length === 0) {
    setApdRulesMessage('Belum ada aturan APD.');
    return;
  }

  rules.forEach(rule => {
    const row = document.createElement('tr');
    row.dataset.kelas = rule.lab;
    row.dataset.status = rule.aktif ? 'aktif' : 'nonaktif';
    const values = [
      rule.lab,
      'Wajib',
      apdRuleValue(rule.wajib_helm),
      apdRuleValue(rule.wajib_baju),
      apdRuleValue(rule.wajib_jeans),
      apdRuleValue(rule.wajib_sepatu)
    ];
    values.forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 0) cell.style.fontWeight = '700';
      if (index === 1) {
        const badge = document.createElement('span');
        badge.className = 'adm-badge adm-badge-blue';
        badge.textContent = value;
        cell.replaceChildren(badge);
      }
      row.appendChild(cell);
    });

    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `adm-badge ${rule.aktif ? 'adm-badge-green' : 'adm-badge-amber'}`;
    statusBadge.textContent = rule.aktif ? 'Berlaku' : 'Nonaktif';
    statusCell.appendChild(statusBadge);
    row.appendChild(statusCell);

    const actions = document.createElement('td');
    if (apdRulesCanEdit) {
      const editButton = document.createElement('button');
      editButton.type = 'button';
      editButton.className = 'adm-btn-action-edit';
      editButton.textContent = 'Edit';
      editButton.addEventListener('click', () => openApdRuleForm(rule));
      actions.appendChild(editButton);
    } else {
      actions.textContent = '—';
    }
    row.appendChild(actions);
    body.appendChild(row);
  });
  filterAdmTable('tableAturan', 'searchAturan', 'filterLabAturan', 'filterStatusAturan');
}

async function loadApdRules() {
  try {
    const result = await academicApi('/api/apd-rules');
    renderApdRules(result.rules);
  } catch (error) {
    setApdRulesMessage(error.message);
    showToast(error.message);
  }
}

async function initApdRules() {
  if (!document.getElementById('tableAturan')) return;
  try {
    const result = await academicApi('/api/auth/me');
    apdRulesCanEdit = Boolean(result.user && result.user.peran.toLowerCase() === 'operator');
    await loadApdRules();
  } catch (error) {
    setApdRulesMessage(error.message);
  }
}

function openApdRuleForm(rule) {
  if (!apdRulesCanEdit) return;
  document.getElementById('aturanLab').value = rule.lab;
  document.getElementById('aturanHelm').checked = Boolean(rule.wajib_helm);
  document.getElementById('aturanBaju').checked = Boolean(rule.wajib_baju);
  document.getElementById('aturanJeans').checked = Boolean(rule.wajib_jeans);
  document.getElementById('aturanSepatu').checked = Boolean(rule.wajib_sepatu);
  document.getElementById('aturanAktif').value = String(rule.aktif);
  document.getElementById('aturanFormEyebrow').textContent = 'Ubah Aturan';
  document.getElementById('aturanFormTitle').textContent = `Aturan APD — ${rule.lab}`;
  openAdmModal('modalAturanAI');
}

async function submitApdRule(event) {
  event.preventDefault();
  if (!apdRulesCanEdit) return;
  const button = document.getElementById('btnSubmitAturan');
  const lab = document.getElementById('aturanLab').value;
  const payload = {
    helm: document.getElementById('aturanHelm').checked,
    baju: document.getElementById('aturanBaju').checked,
    jeans: document.getElementById('aturanJeans').checked,
    sepatu: document.getElementById('aturanSepatu').checked,
    aktif: Number(document.getElementById('aturanAktif').value)
  };
  button.disabled = true;
  try {
    await academicApi(`/api/apd-rules/${encodeURIComponent(lab)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    closeAdmModal('modalAturanAI');
    showToast(`Aturan APD lab ${lab} berhasil disimpan.`);
    await loadApdRules();
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('formAturanAI');
  if (form) form.addEventListener('submit', submitApdRule);
  initApdRules();
});

async function reportApi(url) {
  const response = await fetch(url);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || 'Laporan gagal dimuat.');
  }
  return result;
}

function attendanceReportParams() {
  const params = new URLSearchParams();
  const filters = {
    tanggal_mulai: document.getElementById('filterTanggalMulaiLaporan').value,
    tanggal_selesai: document.getElementById('filterTanggalSelesaiLaporan').value,
    kelas: document.getElementById('filterKelasLaporan').value,
    status: document.getElementById('filterStatusLaporan').value,
    q: document.getElementById('searchLaporan').value.trim()
  };
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params;
}

function reportApdValue(value, required, isJeans) {
  if (value === null) {
    if (isJeans) return 'Belum diverifikasi manual';
    return required ? 'Belum diperiksa' : 'Tidak wajib';
  }
  return value ? 'Sesuai' : 'Tidak sesuai';
}

function setReportTableMessage(message) {
  const body = document.getElementById('tabelLaporanBody');
  if (!body) return;
  body.replaceChildren();
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 11;
  cell.textContent = message;
  row.appendChild(cell);
  body.appendChild(row);
}

function renderAttendanceReport(result) {
  const body = document.getElementById('tabelLaporanBody');
  if (!body) return;
  body.replaceChildren();
  const summary = document.getElementById('reportSummary');
  summary.textContent =
    `Total ${result.summary.total} catatan · ${result.summary.lengkap} lengkap · ${result.summary.kurang} tidak lengkap`;

  if (result.attendance.length === 0) {
    setReportTableMessage('Belum ada data absensi untuk filter yang dipilih.');
    return;
  }

  result.attendance.forEach(item => {
    const row = document.createElement('tr');
    row.dataset.kelas = item.kelas;
    row.dataset.status = item.status;
    const time = new Date(item.waktu.replace(' ', 'T'));
    const timeLabel = Number.isNaN(time.getTime())
      ? item.waktu
      : new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short' }).format(time);
    const required = item.wajib || [];
    const values = [
      timeLabel,
      item.nim,
      item.nama,
      item.kelas,
      item.mata_kuliah,
      item.lab,
      reportApdValue(item.helm, required.includes('helm'), false),
      reportApdValue(item.baju, required.includes('baju'), false),
      reportApdValue(item.jeans, required.includes('jeans'), true),
      reportApdValue(item.sepatu, required.includes('sepatu'), false),
      {
        lengkap: 'Lengkap',
        kurang: 'Tidak lengkap',
        menunggu_validasi: 'Menunggu validasi jeans'
      }[item.status] || item.status
    ];
    values.forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 10) {
        const badge = document.createElement('span');
        const badgeClass = item.status === 'lengkap'
          ? 'adm-badge-green'
          : item.status === 'menunggu_validasi' ? 'adm-badge-blue' : 'adm-badge-amber';
        badge.className = `adm-badge ${badgeClass}`;
        badge.textContent = value;
        cell.replaceChildren(badge);
      }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  filterAdmTable('tableLaporan', 'searchLaporan', null, null);
}

async function loadAttendanceReport() {
  const params = attendanceReportParams();
  try {
    const result = await reportApi(`/api/reports/attendance?${params.toString()}`);
    renderAttendanceReport(result);
  } catch (error) {
    setReportTableMessage(error.message);
    showToast(error.message);
  }
}

async function exportAttendanceReport() {
  const params = attendanceReportParams();
  window.location.href = `/api/reports/attendance.csv?${params.toString()}`;
}

async function initAttendanceReport() {
  if (!document.getElementById('tableLaporan')) return;
  try {
    const result = await reportApi('/api/mahasiswa');
    const select = document.getElementById('filterKelasLaporan');
    const classes = [...new Set(result.mahasiswa.map(item => item.kelas))].sort();
    classes.forEach(kelas => select.add(new Option(kelas, kelas)));
    await loadAttendanceReport();
  } catch (error) {
    setReportTableMessage(error.message);
  }
}

document.addEventListener('DOMContentLoaded', initAttendanceReport);
