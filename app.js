document.addEventListener("DOMContentLoaded", () => {
  // ---------- API base (auto + override) ----------
  const autoBase = (() => {
    const h = window.location.hostname;
    if (h.includes("localhost") || h.includes("127.0.0.1") || h.includes("[::]")) return "http://127.0.0.1:8000";
    return "https://nyconerise.onrender.com";
  })();
  const API_BASE = localStorage.getItem("apiBase") || autoBase;

  // ---------- el helpers ----------
  const $ = sel => document.querySelector(sel);

  // ---------- elements ----------
  const founderSelect = $("#founderSelect");
  const searchInput = $("#search");
  const loadBtn = $("#loadBtn");
  const matchBtn = $("#matchBtn");
  const kInput = $("#kInput");
  const kVal = $("#kVal");
  const matches = $("#matches");
  const needs = $("#needs");
  const meta = $("#meta");
  const nameEl = $("#name");
  const chips = $("#chips");
  const avatar = $("#avatar");
  const envChip = $("#envChip");
  const btnRefresh = $("#btnRefresh");
  const btnCopy = $("#btnCopy");
  const toast = $("#toast");
  const settingsModal = $("#settingsModal");
  const btnSettings = $("#btnSettings");
  const apiBaseInput = $("#apiBaseInput");
  const btnSaveSettings = $("#btnSaveSettings");
  const btnCancelSettings = $("#btnCancelSettings");
  const matchSubtitle = $("#matchSubtitle");

  // ---------- environment chip + settings input prefills ----------
  if (envChip) {
    envChip.textContent =
      API_BASE.includes("localhost") || API_BASE.includes("127.0.0.1") ? "Local" : "Production";
  }
  if (apiBaseInput) apiBaseInput.value = API_BASE;

  // ---------- utils ----------
  const delay = ms => new Promise(r => setTimeout(r, ms));
  const debounce = (fn, ms=300) => {
    let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); };
  };
  const showToast = (msg)=>{
    if (!toast) return;
    toast.textContent=msg;
    toast.style.display="block";
    setTimeout(()=>toast.style.display="none", 2400);
  };
  // keep a copy of content when skeleton toggles on, restore when off
  const setSkeleton = (el, on = true) => {
    if (!el) return;
    if (on) {
      el.classList.add("skeleton");
      el.dataset.prev = el.textContent; // keep old if needed
      el.textContent = "";
    } else {
      el.classList.remove("skeleton");
      // do NOT restore old text; leave whatever code assigned manually
      if (el.dataset.prev) delete el.dataset.prev;
    }
  };
  
  const initials = (str="")=>{
    const parts = String(str).trim().split(/\s+/).slice(0,2);
    return parts.map(p=>p[0]?.toUpperCase()||"").join("")||"?";
  };
  const scorePct = (s)=> Math.max(0, Math.min(100, Math.round((s||0)*100)));

  // ---------- data ----------
  let cacheList = []; // [{ founder_id, founder_name, industry, index?, needs_text, gives_text }]
  let selectedGlobalIndex = null;

  async function apiFounders(q=""){
    const url = new URL(API_BASE + "/api/founders");
    if (q.trim()) url.searchParams.set("q", q.trim());
    const res = await fetch(url);
    if(!res.ok) throw new Error(`Founders fetch failed: ${res.status}`);
    return res.json();
  }

  async function apiTopK(globalIndex, k){
    const url = new URL(API_BASE + "/api/topk");
    url.searchParams.set("i", globalIndex);
    url.searchParams.set("k", k);
    const res = await fetch(url);
    if(!res.ok) throw new Error(`TopK fetch failed: ${res.status}`);
    return res.json();
  }

  function renderFounders(list){
    if (!founderSelect) return;
    founderSelect.innerHTML = "";
    cacheList = list || [];
    cacheList.forEach((f, idx)=>{
      const opt = document.createElement("option");
      const display = `${f.founder_name} — ${f.industry ?? "—"}  #${f.founder_id}`;
      opt.value = idx; // position in current window
      opt.textContent = display;
      founderSelect.appendChild(opt);
    });
    founderSelect.size = Math.min(16, Math.max(8, cacheList.length || 8));
  }

  async function loadFounders(){
    try{
      if (founderSelect) founderSelect.classList.add("ghost");
      renderFounders([]);
      const q = (searchInput?.value) || "";
      const data = await apiFounders(q);
      renderFounders(data);
      if (founderSelect) founderSelect.classList.remove("ghost");
      // auto select first
      if (data.length){
        founderSelect.selectedIndex = 0;
        updateDetailsFromSelection();
      } else {
        resetDetails();
      }
    }catch(e){
      console.error(e);
      showToast("Failed to load founders");
      resetDetails();
    }
  }

  function resetDetails(){
    if (nameEl) nameEl.textContent = "Select a founder";
    if (chips) chips.innerHTML="";
    if (avatar) avatar.textContent="?";
    if (meta) meta.textContent="";
    if (needs) { needs.textContent=""; needs.classList.remove("skeleton"); }
    if (matches) {
      matches.innerHTML = `<div class="empty">No results yet. Pick a founder and press <strong>Find Matches</strong>.</div>`;
    }
    if (matchSubtitle) matchSubtitle.textContent = "Run a query to see matches.";
    selectedGlobalIndex = null;
  }

  function updateDetailsFromSelection(){
    if (!founderSelect || !cacheList.length) { resetDetails(); return; }
    const pos = founderSelect.selectedIndex;
    if (pos < 0 || !cacheList[pos]) { resetDetails(); return; }
    const f = cacheList[pos];
    selectedGlobalIndex = Number.isInteger(f.index) ? f.index : pos; // prefer backend-provided index

    if (nameEl) nameEl.textContent = f.founder_name || "Unnamed founder";
    if (avatar) avatar.textContent = initials(f.founder_name);
    if (chips) {
      chips.innerHTML = "";
      if (f.industry){
        const ch = document.createElement("span");
        ch.className="chip";
        ch.textContent = f.industry;
        chips.appendChild(ch);
      }
    }
    if (meta) meta.textContent = `ID ${f.founder_id ?? "—"}`;

    if (needs) {
      setSkeleton(needs, true);
      // instant render of list-provided needs
      setTimeout(()=>{
        needs.textContent = f.needs_text || "—";
        setSkeleton(needs, false);
      }, 120);
    }
  }

  async function runTopK(){
    if (selectedGlobalIndex == null){
      updateDetailsFromSelection();
      if (selectedGlobalIndex == null){ showToast("Pick a founder first"); return; }
    }
    const k = parseInt((kInput?.value || "5"), 10);
    localStorage.setItem("topK", String(k));

    if (matches) {
      matches.innerHTML = "";
      for (let i=0;i<Math.min(k, 8);i++){
        const sk = document.createElement("div");
        sk.className="match skeleton";
        sk.style.height="88px";
        matches.appendChild(sk);
      }
    }
    if (matchSubtitle) matchSubtitle.textContent = "Fetching…";

    try{
      const data = await apiTopK(selectedGlobalIndex, k);
      // Update header in case backend returns richer founder
      const f = data.founder || {};
      if (f.founder_name && nameEl) { nameEl.textContent = f.founder_name; if (avatar) avatar.textContent = initials(f.founder_name); }
      if (f.industry && chips) chips.innerHTML = `<span class="chip">${f.industry}</span>`;
      if (f.needs_text && needs) { needs.textContent = f.needs_text; needs.classList.remove("skeleton"); }

      if (!Array.isArray(data.matches) || data.matches.length===0){
        if (matches) matches.innerHTML = `<div class="empty">No matches returned.</div>`;
        if (matchSubtitle) matchSubtitle.textContent = "No results.";
        return;
      }

      if (matches) {
        matches.innerHTML = "";
        data.matches.forEach(m=>{
          const sc = scorePct(m.score);
          const el = document.createElement("div");
          el.className = "match";
          el.innerHTML = `
            <div class="top">
              <div class="who">
                <div class="avatar" style="width:34px;height:34px">${initials(m.founder_name)}</div>
                <div>
                  <div class="match-name" style="font-weight:650">${m.founder_name ?? "—"}</div>
                  <div class="muted match-industry">${m.industry ?? "—"}</div>
                </div>
              </div>
              <div class="score">
                <span class="match-score">${sc}%</span>
                <div class="bar"><i style="width:${sc}%"></i></div>
              </div>
            </div>
            <div class="body">
              <div class="muted">Gives</div>
              <div class="mono match-gives">${(m.gives_text || "—").slice(0,420)}</div>
            </div>
          `;
          matches.appendChild(el);
        });
      }
      if (matchSubtitle) matchSubtitle.textContent = `${data.matches.length} results`;
      showToast("Matches updated");
    }catch(e){
      console.error(e);
      if (matches) matches.innerHTML = `<div class="empty">Error fetching matches. Check backend & CORS.</div>`;
      if (matchSubtitle) matchSubtitle.textContent = "Request failed";
      showToast("Failed to fetch matches");
    }
  }

  // ---------- events ----------
  if (loadBtn) loadBtn.addEventListener("click", loadFounders);
  if (btnRefresh) btnRefresh.addEventListener("click", loadFounders);
  if (founderSelect) founderSelect.addEventListener("change", updateDetailsFromSelection);

  if (kInput && kVal) {
    kInput.value = localStorage.getItem("topK") || "5";
    kVal.textContent = kInput.value;
    kInput.addEventListener("input", ()=> kVal.textContent = kInput.value);
  }

  const debounced = debounce(loadFounders, 300);
  if (searchInput) searchInput.addEventListener("input", ()=> debounced());
  if (matchBtn) matchBtn.addEventListener("click", runTopK);

  document.addEventListener("keydown", (e)=>{
    const key = e.key?.toLowerCase?.();
    if (key === "m") { e.preventDefault(); runTopK(); }
    if (e.key === "ArrowDown" && founderSelect){ e.preventDefault(); founderSelect.selectedIndex = Math.min(founderSelect.length-1, founderSelect.selectedIndex+1); updateDetailsFromSelection(); }
    if (e.key === "ArrowUp" && founderSelect){ e.preventDefault(); founderSelect.selectedIndex = Math.max(0, founderSelect.selectedIndex-1); updateDetailsFromSelection(); }
    if (e.key === "Enter") { e.preventDefault(); runTopK(); }
  });

  if (btnCopy && matches) {
    btnCopy.addEventListener("click", ()=>{
      const cards = matches.querySelectorAll(".match");
      if (!cards.length){ showToast("Nothing to copy"); return; }
      const lines = [];
      cards.forEach(c=>{
        const name = c.querySelector(".match-name")?.textContent?.trim() || "";
        const ind = c.querySelector(".match-industry")?.textContent?.trim() || "";
        const score = c.querySelector(".match-score")?.textContent?.trim() || "";
        const gives = c.querySelector(".match-gives")?.textContent?.trim() || "";
        lines.push(`${name} — ${ind} — ${score}\n${gives}\n`);
      });
      navigator.clipboard.writeText(lines.join("\n"))
        .then(()=>showToast("Copied matches"))
        .catch(()=>showToast("Clipboard not available"));
    });
  }

  if (btnSettings && settingsModal) {
    btnSettings.addEventListener("click", ()=> settingsModal.style.display="grid");
  }
  if (btnCancelSettings && settingsModal) {
    btnCancelSettings.addEventListener("click", ()=> settingsModal.style.display="none");
  }
  if (btnSaveSettings && settingsModal) {
    btnSaveSettings.addEventListener("click", ()=>{
      const v = apiBaseInput?.value?.trim();
      if (!v){ showToast("Enter a valid URL"); return; }
      localStorage.setItem("apiBase", v);
      settingsModal.style.display="none";
      showToast("API base saved — Reloading…");
      setTimeout(()=>location.reload(), 500);
    });
  }
  if (settingsModal) {
    settingsModal.addEventListener("click", (e)=>{ if(e.target===settingsModal) settingsModal.style.display="none"; });
  }

  if (founderSelect) {
    founderSelect.addEventListener("dblclick", e => {
      if (founderSelect.selectedIndex >= 0) runTopK();
    });
  }

  // first load
  loadFounders().catch(()=>{ /* handled in loadFounders */ });
});
