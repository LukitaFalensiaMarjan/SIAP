/**
 * POLMAN SMART ATTENDANCE — INTERACTIVE STUDENT PORTAL
 * Handles notifications, live table filters, compensation simulator, profile modals, and toast feedback
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
  toast.innerHTML = `<span>${message}</span>`;
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

// Mark notifications as read
function markAllNotificationsRead() {
  const badge = document.querySelector('.mhs-bell-badge');
  if (badge) badge.style.display = 'none';
  document.querySelectorAll('.mhs-badge-blue').forEach(b => {
    if (b.innerText.trim() === 'Baru') {
      b.style.display = 'none';
    }
  });
  showToast('Semua notifikasi ditandai telah dibaca.');
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

// Compensation Calculator Simulator
function simulateCompensation(minutes) {
  const totalLate = parseInt(minutes, 10) || 0;
  const compMinutes = totalLate * 5;
  const jp = Math.floor(compMinutes / 50);
  const remainingMins = compMinutes % 50;

  const lateEl = document.getElementById('calcLateMinutes');
  const compEl = document.getElementById('calcCompMinutes');
  const jpEl = document.getElementById('calcCompJP');
  const remainDebtEl = document.getElementById('calcRemainDebt');

  if (lateEl) lateEl.innerText = `${totalLate} menit`;
  if (compEl) compEl.innerText = `${compMinutes} menit`;
  if (jpEl) jpEl.innerText = `${jp} JP ${remainingMins} menit`;
  if (remainDebtEl) {
    const alreadyDone = 50;
    const debt = Math.max(0, compMinutes - alreadyDone);
    remainDebtEl.innerText = `${debt} menit`;
  }
}

// ── DYNAMIC NOTIFICATIONS SYNC (FROM ADMIN DECISIONS) ──
function initStudentNotifications() {
  let storedNotifs = [];
  try {
    const raw = localStorage.getItem('siap_notifications');
    if (raw) storedNotifs = JSON.parse(raw);
  } catch (e) {
    storedNotifs = [];
  }

  // 1. Render in notifikasi.html if present
  const notifListEl = document.getElementById('mhsNotifCardsList');
  if (notifListEl && storedNotifs.length > 0) {
    const htmlCards = storedNotifs.map(n => {
      if (n.isViolation) {
        return `
          <div class="mhs-notif-card" style="border-left: 4px solid #DC2626; background: #FEF2F2;" onclick="showToast('Silakan segera menuju ke administrasi jurusan untuk pengambilan fisik Surat Peringatan (SP).')">
            <div class="mhs-notif-body">
              <div class="mhs-notif-title-row">
                <span class="mhs-notif-title" style="color: #991B1B;">${n.title}</span>
                <div style="display: flex; gap: 6px;">
                  <span class="mhs-badge mhs-badge-red" style="font-size: 10px;">${n.badgeText || 'Surat Peringatan'}</span>
                  ${n.isNew ? '<span class="mhs-badge mhs-badge-blue" style="font-size: 10px;">Baru</span>' : ''}
                </div>
              </div>
              <div class="mhs-notif-desc" style="color: #7F1D1D; font-weight: 500; margin: 6px 0 8px;">
                ${n.desc}
              </div>
              <div class="mhs-notif-date" style="color: #991B1B;">${n.date} · Administrasi Jurusan</div>
            </div>
          </div>
        `;
      } else {
        return `
          <div class="mhs-notif-card" onclick="showToast('Membuka rincian notifikasi')">
            <div class="mhs-notif-body">
              <div class="mhs-notif-title-row">
                <span class="mhs-notif-title">${n.title}</span>
                ${n.isNew ? '<span class="mhs-badge mhs-badge-blue">Baru</span>' : ''}
              </div>
              <div class="mhs-notif-desc">${n.desc}</div>
              <div class="mhs-notif-date">${n.date}</div>
            </div>
          </div>
        `;
      }
    }).join('');

    notifListEl.innerHTML = htmlCards + notifListEl.innerHTML;
  }

  // 2. Render in dropdown list across all student pages
  const dropdownContainer = document.querySelector('.mhs-notif-dropdown');
  if (dropdownContainer && storedNotifs.length > 0) {
    const listWrap = dropdownContainer.querySelector('div[style*="max-height: 280px"]') || dropdownContainer.children[1];
    if (listWrap) {
      const dropdownHtml = storedNotifs.map(n => {
        if (n.isViolation) {
          return `
            <div style="background: #FEF2F2; padding: 10px; border-radius: 8px; border: 1px solid #FCA5A5; cursor: pointer;" onclick="window.location.href='notifikasi.html'">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
                <span style="font-size: 12px; font-weight: 700; color: #991B1B;">${n.title}</span>
                <span class="mhs-badge mhs-badge-red" style="font-size: 9px;">SP</span>
              </div>
              <p style="font-size: 11px; color: #7F1D1D; margin: 0 0 4px; line-height: 1.35;">${n.desc}</p>
              <span style="font-size: 10px; color: #B91C1C;">${n.date}</span>
            </div>
          `;
        } else {
          return `
            <div style="background: #F8FAFC; padding: 10px; border-radius: 8px; border: 1px solid #E2E8F0; cursor: pointer;" onclick="window.location.href='notifikasi.html'">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
                <span style="font-size: 12px; font-weight: 700; color: #0F172A;">${n.title}</span>
                <span class="mhs-badge mhs-badge-blue" style="font-size: 9.5px;">Baru</span>
              </div>
              <p style="font-size: 11px; color: #64748B; margin: 0 0 4px;">${n.desc}</p>
              <span style="font-size: 10px; color: #94A3B8;">${n.date}</span>
            </div>
          `;
        }
      }).join('');
      listWrap.innerHTML = dropdownHtml + listWrap.innerHTML;
    }

    // Ensure red dot indicator is visible on bell button
    const bellBadge = document.querySelector('.mhs-bell-badge');
    if (bellBadge) bellBadge.style.display = 'inline-block';
  }
}

document.addEventListener('DOMContentLoaded', initStudentNotifications);
