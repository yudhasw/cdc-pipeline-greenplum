const STATUS_CLASS = {
  Draft: "label-default",
  "On Progress": "label-info",
  Approved: "label-primary",
  Rejected: "label-danger",
  Completed: "label-success",
};

function statusBadge(status) {
  const cls = STATUS_CLASS[status] || "label-default";
  return `<span class="label ${cls}">${status}</span>`;
}

function renderWeekStatus(items = []) {
  const el = document.getElementById("card-week-status");
  if (!el) return;

  el.innerHTML = items.length
    ? items
        .map(
          (i) => `
      <div class="chip">
        <span class="chip-count">${i.count}</span>
        ${statusBadge(i.status)}
      </div>`,
        )
        .join("")
    : `<p class="text-muted">Belum ada pengajuan minggu ini.</p>`;
}

function renderLatestTable(rows = []) {
  const el = document.getElementById("table-latest");
  if (!el) return;

  el.innerHTML = rows.length
    ? rows
        .map(
          (r) => `
      <tr>
        <td class="text-muted">#${r.id}</td>
        <td>${r.fullname}</td>
        <td>${r.document_type}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${r.leaving_reason || "-"}</td>
        <td>${r.start_leave} &rarr; ${r.end_leave}</td>
        <td>${new Date(r.updated_at).toLocaleString("id-ID")}</td>
      </tr>`,
        )
        .join("")
    : `<tr><td colspan="7" class="text-muted">Belum ada data.</td></tr>`; // Fixed: colspan 7
}

function renderRecentDeleted(rows = []) {
  const el = document.getElementById("table-deleted");
  if (!el) return;

  el.innerHTML = rows.length
    ? rows
        .map(
          (r) => `
      <tr>
        <td class="text-muted">#${r.id}</td>
        <td>${r.fullname}</td>
        <td>${r.document_type}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${new Date(r.deleted_at).toLocaleString("id-ID")}</td>
      </tr>`,
        )
        .join("")
    : `<tr><td colspan="5" class="text-muted">Belum ada penghapusan.</td></tr>`;
}

function renderAccountTable(rows = []) {
  const el = document.getElementById("table-new-accounts");
  if (!el) return;

  el.innerHTML = rows.length
    ? rows
        .map(
          (r) => `
      <tr>
        <td class="text-muted">#${r.id}</td>
        <td>${r.fullname}</td>
        <td>${r.level}</td>
        <td>${r.working_unit}</td>
      </tr>`,
        )
        .join("")
    : `<tr><td colspan="4" class="text-muted">Belum ada akun.</td></tr>`; // Fixed: colspan 4
}

function toggleLoader(show) {
  const loader = document.getElementById("loading-overlay");
  if (!loader) return;

  if (show) {
    loader.classList.remove("hidden");
  } else {
    loader.classList.add("hidden");
  }
}

async function loadAnalytics() {
  toggleLoader(true);

  try {
    const fetchJson = (url) =>
      fetch(url).then((r) => {
        if (!r.ok) throw new Error(`HTTP Error! status: ${r.status}`);
        return r.json();
      });

    const [employees, weekCount, weekStatus, latest, recentDeleted, accounts] =
      await Promise.all([
        fetchJson("/api/analytics/employees"),
        fetchJson("/api/analytics/week-count"),
        fetchJson("/api/analytics/week-status"),
        fetchJson("/api/analytics/latest"),
        fetchJson("/api/analytics/recent-deleted"),
        fetchJson("/api/analytics/5-latest-account-created"),
      ]);

    document.getElementById("stat-employees").textContent =
      employees.total ?? "-";
    document.getElementById("stat-week-count").textContent =
      weekCount.total ?? "-";

    renderWeekStatus(weekStatus);
    renderLatestTable(latest);
    renderRecentDeleted(recentDeleted);
    renderAccountTable(accounts);
  } catch (error) {
    console.error("Gagal memuat analytics:", error);
  } finally {
    toggleLoader(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadAnalytics();

  // setInterval(loadAnalytics, 2000);
});
