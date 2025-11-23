document.addEventListener("DOMContentLoaded", () => {
  // ---------- API base ----------
  const autoBase = (() => {
    const h = window.location.hostname;
    if (h.includes("localhost") || h.includes("127.0.0.1") || h.includes("[::]"))
      return "http://127.0.0.1:8000";
    return "https://nyconerise.onrender.com";
  })();
  const API_BASE = localStorage.getItem("apiBase") || autoBase;


  // ---------- el helpers ----------
  const $ = sel => document.querySelector(sel);


  // ---------- elements ----------
  const founderSelect = $("#founderSelect"); // may not exist anymore
  const founderList = $("#founderList");
  const searchInput = $("#search");
  const loadBtn = $("#loadBtn");
  const matchBtn = $("#matchBtn");


  //add founder button
  const addFounderBtn = $("#addFounderBtn");
  const addForm = $("#addFounderForm");
  const newName = $("#founderNameInput");
  const newIndustry = $("#founderIndustryInput");
  const newNeeds = $("#founderNeedsInput");
  const newGives = $("#founderGivesInput");
  const btnCancelAdd = $("#cancelAddFounderBtn");
  const btnSaveAdd = $("#submitAddFounderBtn");


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


  // ---------- environment ----------
  if (envChip) {
    envChip.textContent =
      API_BASE.includes("localhost") || API_BASE.includes("127.0.0.1")
        ? "Local"
        : "Production";
  }
  if (apiBaseInput) apiBaseInput.value = API_BASE;


  // ---------- utils ----------
  const debounce = (fn, ms = 300) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };
  const showToast = msg => {
    if (!toast) return;
    toast.textContent = msg;
    toast.style.display = "block";
    setTimeout(() => (toast.style.display = "none"), 2400);
  };
  const setSkeleton = (el, on = true) => {
    if (!el) return;
    if (on) {
      el.classList.add("skeleton");
      el.textContent = "";
    } else {
      el.classList.remove("skeleton");
    }
  };
  const initials = (str = "") => {
    const parts = String(str).trim().split(/\s+/).slice(0, 2);
    return parts.map(p => p[0]?.toUpperCase() || "").join("") || "?";
  };
  const scorePct = s => Math.max(0, Math.min(100, Math.round((s || 0) * 100)));


  // ---------- data ----------
  let cacheList = [];
  let selectedGlobalIndex = null;


  // ---------- API ----------
  async function apiFounders(q = "") {
    const url = new URL(API_BASE + "/api/founders");
    if (q.trim()) url.searchParams.set("q", q.trim());
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Founders fetch failed: ${res.status}`);
    return res.json();
  }


  async function apiTopK(globalIndex, k) {
    const url = new URL(API_BASE + "/api/topk");
    url.searchParams.set("i", globalIndex);
    url.searchParams.set("k", k);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`TopK fetch failed: ${res.status}`);
    return res.json();
  }


  //api explanation generator
  async function apiExplain(globalIndex, k) {
    try {
      const url = new URL(API_BASE + "/api/explain");
      url.searchParams.set("founder_index", globalIndex);
      url.searchParams.set("k", k);


      const res = await fetch(url);
      if (!res.ok) throw new Error("Explaination fetch failed");
      return res.json();
    } catch (err) {
      console.error(err);
      showToast("Failed to fetch explanation");
    }
  }


  // ---------- details helpers ----------
  function resetDetails() {
    nameEl.textContent = "Select a founder";
    chips.innerHTML = "";
    avatar.textContent = "?";
    meta.textContent = "";
    needs.textContent = "";
    needs.classList.remove("skeleton");
    matches.innerHTML =
      `<div class="empty">No results yet. Pick a founder and press <strong>Find Matches</strong>.</div>`;
    matchSubtitle.textContent = "Run a query to see matches.";
    selectedGlobalIndex = null;
  }


  function setSelectedIndex(idx) {
  if (idx == null || idx < 0 || !cacheList[idx]) {
    resetDetails();
    return;
  }
  const f = cacheList[idx];
  // prefer explicit global DF index returned by backend; fallback to local idx
  selectedGlobalIndex = (typeof f.index !== "undefined") ? f.index : idx;


    nameEl.textContent = f.founder_name || "Unnamed founder";
    avatar.textContent = initials(f.founder_name);
    chips.innerHTML = f.industry
      ? `<span class="chip">${f.industry}</span>`
      : "";
    meta.textContent = `ID ${f.founder_id ?? "—"}`;


    // render needs safely
    setSkeleton(needs, true);
    setTimeout(() => {
      setSkeleton(needs, false);
      needs.textContent = f.needs_text || "—";
    }, 80);
  }


  // ---------- render founders ----------
  function renderFounders(list) {
    const listEl = document.getElementById("founderList");
    listEl.innerHTML = "";
    cacheList = list;


    list.forEach((f, idx) => {
      const div = document.createElement("div");
      div.className = "founder-item";
      div.dataset.index = idx;
      div.innerHTML = `
        <div class="founder-name">
          <div class="founder-avatar">${initials(f.founder_name)}</div>
          <div>
            <div>${f.founder_name}</div>
            <div class="founder-industry">${f.industry ?? "—"}</div>
          </div>
        </div>
        <div class="founder-id">#${f.founder_id ?? "—"}</div>
      `;


      div.addEventListener("click", () => {
        document
          .querySelectorAll(".founder-item")
          .forEach(i => i.classList.remove("active"));
        div.classList.add("active");
        setSelectedIndex(idx);
      });


      div.addEventListener("dblclick", async () => {
        document
          .querySelectorAll(".founder-item")
          .forEach(i => i.classList.remove("active"));
        div.classList.add("active");
        setSelectedIndex(idx);
        // Wait briefly to ensure needs_text has rendered before fetching matches
        await new Promise(r => setTimeout(r, 150));
        runTopK();
      });


      listEl.appendChild(div);
    });
  }


  // ---------- load founders ----------
  async function loadFounders() {
    try {
      renderFounders([]);
      const q = searchInput?.value || "";
      const data = await apiFounders(q);
      renderFounders(data);
      if (data.length) {
        setSelectedIndex(0);
        document.querySelectorAll(".founder-item")[0]?.classList.add("active");
      } else resetDetails();
    } catch (e) {
      console.error(e);
      showToast("Failed to load founders");
      resetDetails();
    }
  }


  // ---------- run matches ----------
  async function runTopK() {
    if (selectedGlobalIndex == null) {
      showToast("Pick a founder first");
      return;
    }
    const k = parseInt((kInput?.value || "5"), 10);
    localStorage.setItem("topK", String(k));


    matches.innerHTML = "";
    for (let i = 0; i < Math.min(k, 10); i++) {
      const sk = document.createElement("div");
      sk.className = "match skeleton";
      sk.style.height = "88px";
      matches.appendChild(sk);
    }
    matchSubtitle.textContent = "Fetching…";


    try {
      const data = await apiTopK(selectedGlobalIndex, k);
      const f = data.founder || {};
      // Always re-render needs after match fetch
      if (f.needs_text) needs.textContent = f.needs_text;
      else if (cacheList[selectedGlobalIndex])
        needs.textContent = cacheList[selectedGlobalIndex].needs_text || "—";


      if (!Array.isArray(data.matches) || data.matches.length === 0) {
        matches.innerHTML = `<div class="empty">No matches returned.</div>`;
        matchSubtitle.textContent = "No results.";
        return;
      }


      matches.innerHTML = "";
      data.matches.forEach((m, idx) => {
      const sc = scorePct(m.score);
      const el = document.createElement("div");
      el.className = "match";
      // store the global DF index returned by backend (m.index)
      el.dataset.index = m.index ?? idx;
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
          <div class="mono match-gives short">${(m.gives_text || "—").slice(0,420)}</div>
          <button class="toggle-details btn small">Show More</button>
          <div class="mono match-gives full" style="display:none;">${m.gives_text || "—"}</div>
          <button class="btn small show-explanation">Show Explanation</button>
          <div class="explanation" style="margin-top:5px; font-size:0.85em; display:none;"></div>
        </div>
      `;
      matches.appendChild(el);
    });
      matchSubtitle.textContent = `${data.matches.length} results`;
      showToast("Matches updated");
    } catch (e) {
      console.error(e);
      matches.innerHTML = `<div class="empty">Error fetching matches. Check backend & CORS.</div>`;
      matchSubtitle.textContent = "Request failed";
      showToast("Failed to fetch matches");
    }
  }


  // ---------- events ----------
  if (loadBtn) loadBtn.addEventListener("click", loadFounders);
  if (btnRefresh) btnRefresh.addEventListener("click", loadFounders);
  if (matchBtn) matchBtn.addEventListener("click", runTopK);


  //events for add founder button
  if (addFounderBtn) {
  addFounderBtn.addEventListener("click", () => {
    addForm.style.display = addForm.style.display === "block" ? "none" : "block";
  });
}
  //cancel the add founder form
  if (btnCancelAdd) {
    btnCancelAdd.addEventListener("click", () => {
      addForm.style.display = "none";
      newName.value = "";
      newIndustry.value = "";
      newNeeds.value = "";
      newGives.value = "";
    });
  }
  //submit the add founder form
  if (btnSaveAdd) {
    btnSaveAdd.addEventListener("click", async () => {
      const name = newName.value.trim();
      const industry = newIndustry.value.trim();
      const needs = newNeeds.value.trim();
      const gives = newGives.value.trim();
       if (!name) {
      showToast("Enter a founder name");
      return;
    }


    try {
      const res = await fetch(API_BASE + "/api/founders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          founder_name: name,
          industry: industry,
          gives_text: gives,
          needs_text: needs,
        })
      });


      if (!res.ok) throw new Error("Failed");


      showToast("Founder added");
      addForm.style.display = "none";


      newName.value = "";
      newIndustry.value = "";
      newNeeds.value = "";
      newGives.value = "";


      loadFounders();
    } catch (err) {
      showToast("Error adding founder");
      console.error(err);
    }
  });
}


// toggle handling for dropdown details in matches
document.addEventListener("click", e => {
  if (e.target.classList.contains("toggle-details")) {
    const card = e.target.closest(".match");
    const shortEl = card.querySelector(".match-gives.short");
    const fullEl  = card.querySelector(".match-gives.full");


    const expanded = fullEl.style.display === "block";


    if (expanded) {
      fullEl.style.display = "none";
      shortEl.style.display = "block";
      e.target.textContent = "Show More";
    } else {
      fullEl.style.display = "block";
      shortEl.style.display = "none";
      e.target.textContent = "Show Less";
    }
  }
});
// explanation handling for matches
matches.addEventListener("click", async e => {
  if (e.target.classList.contains("show-explanation")) {
    const card = e.target.closest(".match");
    const explanationDiv = card.querySelector(".explanation");


    if (explanationDiv.style.display === "block") {
      explanationDiv.style.display = "none";
      e.targest.textContent = "Show Explanation";
    } else {
      e.target.textContent = "Loading…";
     const data = await apiExplain(selectedGlobalIndex, parseInt(kInput.value || "5"));
     const matchGlobalIndex = parseInt(card.dataset.index);
     const found = (data?.explanations || []).find(x => Number(x.index) === matchGlobalIndex);
      explanationDiv.textContent = found?.explanation || "No explanation available.";
      explanationDiv.style.display = "block";
      e.target.textContent = "Hide Explanation";
    }
  }
});






  if (kInput && kVal) {
    kInput.value = localStorage.getItem("topK") || "5";
    kVal.textContent = kInput.value;
    kInput.addEventListener("input", () => (kVal.textContent = kInput.value));
  }


  const debounced = debounce(loadFounders, 300);
  if (searchInput) searchInput.addEventListener("input", () => debounced());


  document.addEventListener("keydown", e => {
    const key = e.key?.toLowerCase?.();
    if (key === "m") {
      e.preventDefault();
      runTopK();
    }
    if (e.key === "Enter") {
      e.preventDefault();
      runTopK();
    }
  });


  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      const cards = matches.querySelectorAll(".match");
      if (!cards.length) {
        showToast("Nothing to copy");
        return;
      }
      const lines = [];
      cards.forEach(c => {
        const name = c.querySelector(".match-name")?.textContent?.trim() || "";
        const ind = c.querySelector(".match-industry")?.textContent?.trim() || "";
        const score = c.querySelector(".match-score")?.textContent?.trim() || "";
        const gives = c.querySelector(".match-gives")?.textContent?.trim() || "";
        lines.push(`${name} — ${ind} — ${score}\n${gives}\n`);
      });
      navigator.clipboard
        .writeText(lines.join("\n"))
        .then(() => showToast("Copied matches"))
        .catch(() => showToast("Clipboard not available"));
    });
  }


  // settings modal
  if (btnSettings)
    btnSettings.addEventListener("click", () => (settingsModal.style.display = "grid"));
  if (btnCancelSettings)
    btnCancelSettings.addEventListener("click", () => (settingsModal.style.display = "none"));
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", () => {
      const v = apiBaseInput?.value?.trim();
      if (!v) {
        showToast("Enter a valid URL");
        return;
      }
      localStorage.setItem("apiBase", v);
      settingsModal.style.display = "none";
      showToast("API base saved — Reloading…");
      setTimeout(() => location.reload(), 500);
    });
  }
  if (settingsModal)
    settingsModal.addEventListener("click", e => {
      if (e.target === settingsModal) settingsModal.style.display = "none";
    });


  // ---------- init ----------
  loadFounders().catch(() => {});
});






