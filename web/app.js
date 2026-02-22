const state = {
  rows: [],
  data: null,
  generatedAt: null,
  pollTimer: null,
  filters: {
    search: "",
    publishedFrom: "",
    publishedTo: "",
  },
};

const HOOK_STORAGE_KEY = "goi_finder_netlify_build_hook";
const POLL_INTERVAL_MS = 20000;
const POLL_TIMEOUT_MS = 12 * 60 * 1000;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function categoryFor(item) {
  const text = `${item.title || ""} ${item.summary || ""} ${(item.keywords_hit || []).join(" ")}`.toLowerCase();
  if (/\b(drone|uav|uas|aerial|anti-drone)\b/.test(text)) return "drones";
  if (/\b(robot|robotic|amr|ugv|automation|manipulator)\b/.test(text)) return "robotics";
  return "it";
}

function renderStats(data) {
  document.getElementById("totalCount").textContent = String(data.opportunities.length);
  document.getElementById("newCount").textContent = String(data.runs?.[0]?.new_count ?? 0);
  const generated = data.generated_at ? new Date(data.generated_at).toLocaleString() : "N/A";
  document.getElementById("generatedAt").textContent = generated;
}

function setRefreshStatus(message, kind = "") {
  const el = document.getElementById("refreshStatus");
  el.textContent = message;
  el.classList.remove("success", "error", "working");
  if (kind) {
    el.classList.add(kind);
  }
}

function rowHtml(item) {
  const buyer = item.buyer || item.org_path || "N/A";
  const deadline = item.deadline || "N/A";
  const status = item.status || "seen";
  return `
    <tr>
      <td>${escapeHtml(item.title || "Untitled")}</td>
      <td>${escapeHtml(buyer)}</td>
      <td>${escapeHtml(item.source || "-")}</td>
      <td>${escapeHtml(deadline)}</td>
      <td><span class="badge">${Number(item.score || 0)}</span></td>
      <td><span class="badge">${escapeHtml(status)}</span></td>
      <td><a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">Open</a></td>
    </tr>
  `;
}

function renderTable(rows) {
  const tbody = document.getElementById("opportunityRows");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7">No opportunities found.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.slice(0, 80).map(rowHtml).join("");
}

function listHtml(item) {
  const buyer = item.buyer || item.org_path || "N/A";
  return `<li>${escapeHtml(item.title)}<br/><small>${escapeHtml(buyer)} | Score ${Number(item.score || 0)}</small></li>`;
}

function renderGroups(rows) {
  const drones = rows.filter((item) => categoryFor(item) === "drones").slice(0, 8);
  const robotics = rows.filter((item) => categoryFor(item) === "robotics").slice(0, 8);
  const it = rows.filter((item) => categoryFor(item) === "it").slice(0, 8);

  document.getElementById("dronesList").innerHTML = drones.map(listHtml).join("") || "<li>No items</li>";
  document.getElementById("roboticsList").innerHTML = robotics.map(listHtml).join("") || "<li>No items</li>";
  document.getElementById("itList").innerHTML = it.map(listHtml).join("") || "<li>No items</li>";
}

function dateToNumber(value) {
  if (!value) return null;
  const n = Number(String(value).replaceAll("-", ""));
  return Number.isFinite(n) ? n : null;
}

function applyClientFilters() {
  const q = state.filters.search;
  const fromNum = dateToNumber(state.filters.publishedFrom);
  const toNum = dateToNumber(state.filters.publishedTo);

  const filtered = state.rows.filter((item) => {
    const hay = `${item.title || ""} ${item.buyer || ""} ${item.org_path || ""} ${(item.keywords_hit || []).join(" ")}`.toLowerCase();
    if (q && !hay.includes(q)) {
      return false;
    }

    if (fromNum !== null || toNum !== null) {
      const pubNum = dateToNumber(item.published_date);
      if (pubNum === null) {
        return false;
      }
      if (fromNum !== null && pubNum < fromNum) {
        return false;
      }
      if (toNum !== null && pubNum > toNum) {
        return false;
      }
    }
    return true;
  });

  renderTable(filtered);
  renderGroups(filtered);
}

function attachFilters() {
  const searchInput = document.getElementById("searchInput");
  const fromInput = document.getElementById("publishedFrom");
  const toInput = document.getElementById("publishedTo");

  searchInput.addEventListener("input", () => {
    state.filters.search = searchInput.value.trim().toLowerCase();
    applyClientFilters();
  });

  fromInput.addEventListener("change", () => {
    state.filters.publishedFrom = fromInput.value || "";
    applyClientFilters();
  });

  toInput.addEventListener("change", () => {
    state.filters.publishedTo = toInput.value || "";
    applyClientFilters();
  });
}

async function fetchData() {
  const cacheBypass = Date.now();
  const res = await fetch(`./opportunities.json?t=${cacheBypass}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch opportunities.json (${res.status})`);
  }
  return res.json();
}

function applyData(data) {
  const rows = (data.opportunities || []).sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
  state.rows = rows;
  state.data = data;
  state.generatedAt = data.generated_at || null;
  renderStats(data);
  applyClientFilters();
}

function getBuildHookUrl() {
  if (window.GOI_REFRESH_HOOK_URL && String(window.GOI_REFRESH_HOOK_URL).trim()) {
    return String(window.GOI_REFRESH_HOOK_URL).trim();
  }
  return localStorage.getItem(HOOK_STORAGE_KEY)?.trim() || "";
}

function setBuildHookUrl() {
  const existing = getBuildHookUrl();
  const input = window.prompt(
    "Paste Netlify Build Hook URL. Leave blank to clear saved hook.",
    existing
  );
  if (input === null) {
    return;
  }
  const cleaned = input.trim();
  if (!cleaned) {
    localStorage.removeItem(HOOK_STORAGE_KEY);
    setRefreshStatus("Build hook removed from this browser.", "success");
    return;
  }
  localStorage.setItem(HOOK_STORAGE_KEY, cleaned);
  setRefreshStatus("Build hook saved. You can now use Refresh Live Sources.", "success");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForNewSnapshot(previousGeneratedAt) {
  const start = Date.now();
  while (Date.now() - start < POLL_TIMEOUT_MS) {
    await sleep(POLL_INTERVAL_MS);
    try {
      const data = await fetchData();
      const nextGeneratedAt = data.generated_at || null;
      if (nextGeneratedAt !== previousGeneratedAt) {
        applyData(data);
        return true;
      }
    } catch (error) {
      // Continue polling; transient network issues are expected.
      console.error(error);
    }
  }
  return false;
}

async function triggerRefreshRun() {
  const refreshBtn = document.getElementById("refreshBtn");
  const previousGeneratedAt = state.generatedAt;
  const hookUrl = getBuildHookUrl();

  if (!hookUrl) {
    setRefreshStatus("Set your Netlify build hook first, then retry Refresh.", "error");
    return;
  }

  refreshBtn.disabled = true;
  setRefreshStatus("Triggering Netlify build for fresh crawl...", "working");

  try {
    // Build hooks do not reliably support browser CORS reads; no-cors still sends the POST.
    await fetch(hookUrl, { method: "POST", mode: "no-cors" });
    setRefreshStatus(
      "Build triggered. Waiting for updated opportunities (checks every 20s)...",
      "working"
    );
    const updated = await waitForNewSnapshot(previousGeneratedAt);
    if (updated) {
      setRefreshStatus("New crawl completed and dashboard updated.", "success");
    } else {
      setRefreshStatus(
        "No update detected yet. Build may still be running; refresh the page shortly.",
        "error"
      );
    }
  } catch (error) {
    console.error(error);
    setRefreshStatus("Failed to trigger build hook. Verify the hook URL.", "error");
  } finally {
    refreshBtn.disabled = false;
  }
}

function attachRefreshControls() {
  document.getElementById("setHookBtn").addEventListener("click", setBuildHookUrl);
  document.getElementById("refreshBtn").addEventListener("click", triggerRefreshRun);
}

async function bootstrap() {
  try {
    const data = await fetchData();
    applyData(data);
    attachFilters();
    attachRefreshControls();
  } catch (err) {
    document.getElementById("opportunityRows").innerHTML = "<tr><td colspan='7'>Failed to load data.</td></tr>";
    setRefreshStatus("Could not load opportunities.json.", "error");
    console.error(err);
  }
}

bootstrap();
