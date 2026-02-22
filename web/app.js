const state = {
  rows: [],
};

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

function attachSearch() {
  const input = document.getElementById("searchInput");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      renderTable(state.rows);
      renderGroups(state.rows);
      return;
    }
    const filtered = state.rows.filter((item) => {
      const hay = `${item.title || ""} ${item.buyer || ""} ${item.org_path || ""} ${(item.keywords_hit || []).join(" ")}`.toLowerCase();
      return hay.includes(q);
    });
    renderTable(filtered);
    renderGroups(filtered);
  });
}

async function bootstrap() {
  try {
    const res = await fetch("./opportunities.json", { cache: "no-store" });
    const data = await res.json();
    const rows = (data.opportunities || []).sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
    state.rows = rows;
    renderStats(data);
    renderTable(rows);
    renderGroups(rows);
    attachSearch();
  } catch (err) {
    document.getElementById("opportunityRows").innerHTML = "<tr><td colspan='7'>Failed to load data.</td></tr>";
    console.error(err);
  }
}

bootstrap();
