const API_BASE = (() => {
  if (window.location.hostname.includes("localhost") || window.location.hostname.includes("127.0.0.1") || window.location.hostname.includes("[::]")) {
    return "http://127.0.0.1:8000"; // local backend
  }
  return "https://nyconerise.onrender.com"; // deployed backend
})();

const founderSelect = document.getElementById("founderSelect");
const searchInput = document.getElementById("search");
const loadBtn = document.getElementById("loadBtn");
const matchBtn = document.getElementById("matchBtn");
const kInput = document.getElementById("kInput");
const matchList = document.getElementById("matchList");
const queryMeta = document.getElementById("queryMeta");

async function getFounders(q="") {
  const url = new URL(API_BASE + "/api/founders");
  if (q.trim()) url.searchParams.set("q", q.trim());
  const res = await fetch(url);
  if (!res.ok) throw new Error("failed to fetch founders");
  return await res.json();
}

function renderFounders(list) {
  founderSelect.innerHTML = "";
  list.forEach((f, idx) => {
    const opt = document.createElement("option");
    opt.value = idx; // this is position within this list, not global index
    opt.textContent = `${f.founder_name} — ${f.industry} (${f.founder_id})`;
    founderSelect.appendChild(opt);
  });
  founderSelect.dataset.cache = JSON.stringify(list); // store raw
}

async function loadFounders() {
  const q = searchInput.value || "";
  const data = await getFounders(q);
  renderFounders(data);
}

async function getTopK(globalIndex, k) {
  const url = new URL(API_BASE + "/api/topk");
  url.searchParams.set("i", globalIndex);
  url.searchParams.set("k", k);
  const res = await fetch(url);
  if (!res.ok) throw new Error("failed to fetch matches");
  return await res.json();
}

// naive: /api/founders returns a window (first 100). We’ll map the dropdown index to the
// global index using a second fetch if needed. For now, keep backend default order (0..N-1).
// If you need stable global indices regardless of filtering, expose DF index in /api/founders.

loadBtn.addEventListener("click", loadFounders);
matchBtn.addEventListener("click", async () => {
  const cached = JSON.parse(founderSelect.dataset.cache || "[]");
  const pos = founderSelect.selectedIndex;
  if (pos < 0) return;

  // TEMP: assume dropdown order == global index (works when API returns head of DF).
  // For full correctness, extend API to return "index" and use that here.
  const globalIndex = pos; 
  const k = Math.max(1, Math.min(50, parseInt(kInput.value || "5", 10)));

  const data = await getTopK(globalIndex, k);
  queryMeta.textContent = `${data.founder.founder_name} — ${data.founder.industry}
Needs: ${data.founder.needs_text}`;

  matchList.innerHTML = "";
  data.matches.forEach(m => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${m.founder_name}</strong> — ${m.industry}
      <div class="muted">Score: ${m.score.toFixed(3)}</div>
      <div class="mono">${m.gives_text}</div>`;
    matchList.appendChild(li);
  });
});

// initial load
loadFounders().catch(console.error);
