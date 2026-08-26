const STATUS_CLASS_HEALTH = {
  ok: "label-success",
  warn: "label-info",
  fail: "label-danger",
};

function toggleLoader(show) {
  const loader = document.getElementById("loading-overlay");
  if (!loader) return;

  if (show) {
    loader.classList.remove("hidden");
  } else {
    loader.classList.add("hidden");
  }
}

function renderHealth(data) {
  const el = document.getElementById("health-cards");
  if (!el) return;

  el.innerHTML = (data.checks || [])
    .map(
      (c) => `
      <div class="chip">
        <span>${c.name}</span>
        <span class="label ${STATUS_CLASS_HEALTH[c.status] || "label-default"}">${c.detail}</span>
      </div>`,
    )
    .join("");

  const timeEl = document.getElementById("health-checked-at");
  if (timeEl) {
    timeEl.textContent =
      "terakhir diperiksa: " + new Date().toLocaleTimeString("id-ID");
  }
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health").then((r) => r.json());
    renderHealth(res);
  } catch (err) {
    console.error("Gagal memuat status kesehatan:", err);
  }
}

let activeContainer = null;

function markActiveTab() {
  document.querySelectorAll(".log-tab").forEach((btn) => {
    btn.classList.toggle(
      "log-tab-active",
      btn.dataset.container === activeContainer,
    );
  });
}

async function loadLogTabs() {
  try {
    const res = await fetch("/api/logs").then((r) => r.json());
    const el = document.getElementById("log-tabs");
    if (!el) return;

    el.innerHTML = (res.containers || [])
      .map((c) => `<button class="log-tab" data-container="${c}">${c}</button>`)
      .join("");

    el.querySelectorAll(".log-tab").forEach((btn) => {
      btn.addEventListener("click", async () => {
        activeContainer = btn.dataset.container;
        markActiveTab();

        const view = document.getElementById("log-view");
        if (view) view.textContent = "Memuat data log...";

        await loadLogView(true);
      });
    });

    if (!activeContainer && res.containers && res.containers.length) {
      activeContainer = res.containers[0];
      markActiveTab();
    }
  } catch (err) {
    console.error("Gagal memuat log tabs:", err);
  }
}

async function loadLogView(forceBottom = false) {
  if (!activeContainer) return;
  const view = document.getElementById("log-view");
  if (!view) return;

  try {
    const res = await fetch(`/api/logs/${activeContainer}?tail=200`).then((r) =>
      r.json(),
    );
    const wasAtBottom =
      forceBottom ||
      view.scrollTop + view.clientHeight >= view.scrollHeight - 20;

    if (Array.isArray(res.lines)) {
      view.textContent = res.lines.length
        ? res.lines.join("\n")
        : "(log kosong)";
    } else {
      view.textContent = res.error || "(gagal memuat log)";
    }

    if (wasAtBottom) {
      view.scrollTop = view.scrollHeight;
    }
  } catch (err) {
    console.error("Gagal memuat log view:", err);
    view.textContent = "(gagal terhubung ke server log)";
  }
}

// ── GENERATOR STATUS & BUTTONS ────────────────────────────────────────────
function renderGeneratorStatus(data) {
  const badge = document.getElementById("gen-status-badge");
  if (badge) {
    badge.textContent = data.running ? "JALAN" : "BERHENTI";
    badge.className =
      "label " + (data.running ? "label-success" : "label-default");
  }

  const lastActionEl = document.getElementById("gen-last-action");
  if (lastActionEl) {
    lastActionEl.textContent = data.error
      ? `Error: ${data.error}`
      : data.last_action
        ? `Tick ${data.tick} - aksi terakhir: ${data.last_action}`
        : "Belum ada aksi";
  }

  const cardsEl = document.getElementById("gen-latency-cards");
  if (!cardsEl) return;

  if (!data.latency) {
    cardsEl.innerHTML =
      '<div class="chip"><span>Latensi</span><span class="label label-default">belum ada sampel</span></div>';
    return;
  }
  const l = data.latency;
  cardsEl.innerHTML = `
    <div class="chip"><span>Sampel</span><span class="label label-default">${l.count}</span></div>
    <div class="chip"><span>Terakhir</span><span class="label label-info">${l.last}s</span></div>
    <div class="chip"><span>Min</span><span class="label label-success">${l.min}s</span></div>
    <div class="chip"><span>Rata-rata</span><span class="label label-info">${l.avg}s</span></div>
    <div class="chip"><span>Max</span><span class="label label-danger">${l.max}s</span></div>
  `;
}

async function loadGeneratorStatus() {
  try {
    const res = await fetch("/api/generator/status").then((r) => r.json());
    renderGeneratorStatus(res);
  } catch (err) {
    console.error("Gagal memuat status generator:", err);
  }
}

async function handleGeneratorAction(url, btn) {
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Proses...";

  try {
    await fetch(url, { method: "POST" });
    await loadGeneratorStatus();
  } catch (err) {
    console.error("Gagal mengeksekusi aksi generator:", err);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

const startBtn = document.getElementById("gen-start-btn");
if (startBtn) {
  startBtn.addEventListener("click", () =>
    handleGeneratorAction("/api/generator/start", startBtn),
  );
}

const stopBtn = document.getElementById("gen-stop-btn");
if (stopBtn) {
  stopBtn.addEventListener("click", () =>
    handleGeneratorAction("/api/generator/stop", stopBtn),
  );
}

async function tick(forceBottom = false) {
  await Promise.all([
    loadHealth(),
    loadLogView(forceBottom),
    loadGeneratorStatus(),
  ]);
}

async function init() {
  toggleLoader(true);
  try {
    await loadLogTabs();
    await tick(true);
  } finally {
    toggleLoader(false);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  init();
  setInterval(() => tick(false), 15000);
});
