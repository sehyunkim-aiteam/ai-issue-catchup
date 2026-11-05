import { FEED_URL, REFRESH_MINUTES, GA_MEASUREMENT_ID, GA_API_SECRET } from "./config.js";

// 사이드바 카테고리 (icon = SVG path)
const CATEGORIES = [
  { id: "all", label: "전체", icon: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" },
  { id: "ai", label: "AI", icon: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" },
  { id: "vibe_coding", label: "Vibe Coding", icon: "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16" },
  { id: "business", label: "Business", icon: "M3 8h18v12H3zM8 8V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v3M3 13h18" },
  { id: "etc", label: "etc", icon: "M5 12h.01M12 12h.01M19 12h.01" },
];
const SAVED_ICON = "M6 3h12a1 1 0 0 1 1 1v17l-7-4.5L5 21V4a1 1 0 0 1 1-1z";
const CAT_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.id, c.label]));
const THEMES = ["system", "light", "dark"];
const THEME_TITLE = { system: "화면 모드: 시스템", light: "화면 모드: 라이트", dark: "화면 모드: 다크" };
const POP_SIZE = 10;
// 예전 피드·저장함에 남은 분류(design 등)는 etc로 본다
const normalize = (it) => (CAT_LABEL[it.category] && it.category !== "all" ? it : { ...it, category: "etc" });

// ── 저장소: 확장에선 chrome.storage.local, 웹에선 localStorage ──
const isExtension = location.protocol === "chrome-extension:";
const store = {
  async get(key, fallback) {
    try {
      if (isExtension) return (await chrome.storage.local.get(key))[key] ?? fallback;
      const v = localStorage.getItem(key);
      return v ? JSON.parse(v) : fallback;
    } catch { return fallback; }
  },
  async set(key, value) {
    try {
      if (isExtension) await chrome.storage.local.set({ [key]: value });
      else localStorage.setItem(key, JSON.stringify(value));
    } catch { /* 저장 실패해도 화면은 계속 동작 */ }
  },
};

// ── 행동 로그: PV(새 탭·페이지 열기)와 CLICK(콘텐츠 열기)만 GA4로 보낸다 ──
// uid = 처음 열 때 만든 무작위 UUID(GA4 client_id). 회원 개념이 없어 사용자 구분은 이것뿐이다.
//   확장: chrome.storage.local에 저장 → 설치 단위(삭제하면 같이 지워진다)
//   웹:   localStorage에 저장 → 브라우저 단위(브라우저 데이터를 지우면 새 uid)
// session_id = 30분 넘게 쉬었다 열면 새로 만든다(GA4 세션 기준과 같음).
const PLATFORM = isExtension ? "extension" : "web";
const APP_VERSION = isExtension ? chrome.runtime.getManifest().version : "web";
const SESSION_IDLE_MS = 30 * 60 * 1000;
// 로컬 개발(localhost)에서는 GA4 검증용 주소로 보내 실데이터에 섞이지 않게 한다.
const IS_DEV = ["localhost", "127.0.0.1"].includes(location.hostname);
const LOG_URL = GA_MEASUREMENT_ID && GA_API_SECRET
  ? `https://www.google-analytics.com/${IS_DEV ? "debug/" : ""}mp/collect?measurement_id=${GA_MEASUREMENT_ID}&api_secret=${GA_API_SECRET}`
  : "";
let uid = null;
let sessionId = null;

async function initUid() {
  uid = await store.get("uid", null);
  if (!uid) {
    uid = crypto.randomUUID();
    await store.set("uid", uid);
  }
  const now = Date.now();
  const s = await store.get("session", null);
  sessionId = s && now - s.last < SESSION_IDLE_MS ? s.id : String(Math.floor(now / 1000));
  await store.set("session", { id: sessionId, last: now });
}

function track(event, params = {}) {
  if (!LOG_URL || !uid) return;
  store.set("session", { id: sessionId, last: Date.now() });
  const body = JSON.stringify({
    client_id: uid,
    events: [{ name: event, params: {
      session_id: sessionId, engagement_time_msec: 1,   // 이 둘이 있어야 GA4 보고서에 사용자·세션으로 잡힌다
      platform: PLATFORM, app_version: APP_VERSION, ...params,
    } }],
  });
  try {
    // text/plain이라 CORS preflight가 없다. 링크를 눌러 페이지가 바뀌어도 전송된다.
    if (!navigator.sendBeacon(LOG_URL, new Blob([body], { type: "text/plain" }))) throw new Error("beacon");
  } catch {
    fetch(LOG_URL, { method: "POST", body, keepalive: true, mode: "no-cors" }).catch(() => {});
  }
}

// 콘텐츠 열기 = 읽음 표시 + CLICK 로그
function openContent(id) {
  track("click", { content_id: id });
  markRead(id);
}

const state = { feed: null, view: "all", saved: {}, read: {}, theme: "system" };   // view = 카테고리 id | "saved"
const $ = (s) => document.querySelector(s);
const feedUrl = isExtension ? FEED_URL : new URL("feed.json", location.href).href;

// ── 유틸 ──
function when(iso) {
  const d = new Date(iso);
  const min = (Date.now() - d.getTime()) / 60000;
  if (min < 60) return `${Math.max(1, Math.floor(min))}분 전`;
  if (min < 1440) return `${Math.floor(min / 60)}시간 전`;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}. ${p(d.getMonth() + 1)}. ${p(d.getDate())}.`;
}

function svgIcon(path) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", path);
  svg.append(p);
  return svg;
}

// 화제도(다른 매체가 같은 이슈를 다룬 수) 우선, 같으면 최신순. 오늘 기사가 부족하면 최근 72시간 전체에서 고른다.
function ranked(items) {
  const day = items.filter((it) => Date.now() - new Date(it.published_at) < 864e5);
  const pool = day.length >= POP_SIZE ? day : items;
  return [...pool].sort((a, b) => (b.buzz ?? 0) - (a.buzz ?? 0) || b.published_at.localeCompare(a.published_at));
}

// ── 렌더: 왼쪽 카테고리 ──
function renderNav(all) {
  const counts = { all: all.length };
  for (const it of all) counts[it.category] = (counts[it.category] ?? 0) + 1;

  const mk = (id, label, icon, count) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.className = "cat-btn";
    b.type = "button";
    b.setAttribute("aria-pressed", String(state.view === id));
    const name = document.createElement("span");
    name.className = "cat-name";
    name.textContent = label;
    const c = document.createElement("span");
    c.className = "cat-count";
    c.textContent = count || "";
    b.append(svgIcon(icon), name, c);
    b.onclick = () => setView(id);
    li.append(b);
    return li;
  };
  const sep = document.createElement("li");
  sep.className = "cat-sep";
  sep.setAttribute("aria-hidden", "true");

  $("#catList").replaceChildren(
    ...CATEGORIES.map((c) => mk(c.id, c.label, c.icon, counts[c.id])),
    sep,
    mk("saved", "저장한 콘텐츠", SAVED_ICON, Object.keys(state.saved).length),
  );
}

// ── 렌더: 오른쪽 인기 콘텐츠 ──
function renderPopular(all) {
  const top = ranked(all).slice(0, POP_SIZE);
  $(".pop").hidden = top.length === 0;
  $("#popList").replaceChildren(...top.map((it, i) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.className = "pop-item";
    a.href = it.url;
    a.title = it.summary || it.title;
    a.addEventListener("click", () => openContent(it.id));
    a.addEventListener("auxclick", (e) => { if (e.button === 1) openContent(it.id); });

    const rank = document.createElement("span");
    rank.className = "pop-rank";
    rank.textContent = i + 1;
    const img = document.createElement("img");
    img.className = "pop-thumb";
    img.alt = "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    if (it.image) img.src = it.image;
    img.onerror = () => img.removeAttribute("src");
    const text = document.createElement("div");
    const t = document.createElement("div");
    t.className = "pop-title";
    t.textContent = it.title;
    const s = document.createElement("div");
    s.className = "pop-src";
    s.textContent = it.source;
    text.append(t, s);

    a.append(rank, img, text);
    li.append(a);
    return li;
  }));
}

// ── 렌더: 카드 ──
function buildCard(it) {
  const node = $("#cardTpl").content.firstElementChild.cloneNode(true);
  node.dataset.id = it.id;

  const thumb = node.querySelector(".thumb");
  const img = thumb.querySelector("img");
  thumb.href = it.url;
  thumb.querySelector(".thumb-fallback").textContent = it.source;
  if (it.image) {
    img.src = it.image;
    img.onerror = () => thumb.classList.add("noimg");
  } else {
    thumb.classList.add("noimg");
  }

  node.querySelector(".src").textContent = it.source;
  const t = node.querySelector("time");
  t.dateTime = it.published_at;
  t.textContent = when(it.published_at);

  const title = node.querySelector(".title");
  title.href = it.url;
  title.textContent = it.title;
  const sum = node.querySelector(".summary");
  sum.textContent = it.summary ?? "";
  sum.title = it.summary ?? "";
  const cat = node.querySelector(".cat");
  cat.dataset.cat = it.category;
  cat.textContent = CAT_LABEL[it.category] ?? "etc";

  for (const a of [thumb, title]) {
    a.addEventListener("click", () => openContent(it.id));
    a.addEventListener("auxclick", (e) => { if (e.button === 1) openContent(it.id); });   // 휠 클릭(새 탭)
  }

  const save = node.querySelector(".save");
  const paint = () => {
    const on = Boolean(state.saved[it.id]);
    save.setAttribute("aria-pressed", String(on));
    save.setAttribute("aria-label", on ? "저장 해제" : "저장");
  };
  paint();
  save.onclick = async () => {
    if (state.saved[it.id]) delete state.saved[it.id];
    else state.saved[it.id] = it;   // 피드에서 사라져도 남도록 사본 보관
    paint();
    await store.set("saved", state.saved);
    renderNav(state.feed?.items ?? []);
    if (state.view === "saved") render();
  };

  paintRead(node, Boolean(state.read[it.id]));
  return node;
}

function paintRead(node, on) {
  node.classList.toggle("read", on);
  node.querySelector(".read-mark").hidden = !on;
}

function render() {
  const all = state.feed?.items ?? [];
  renderNav(all);
  renderPopular(all);
  $("#savedBtn").setAttribute("aria-pressed", String(state.view === "saved"));

  let items;
  if (state.view === "saved") {
    items = Object.values(state.saved).map(normalize).sort((a, b) => b.published_at.localeCompare(a.published_at));
  } else {
    items = state.view === "all" ? all : all.filter((it) => it.category === state.view);
  }
  $("#grid").replaceChildren(...items.map(buildCard));

  const empty = $("#empty");
  empty.hidden = items.length > 0;
  empty.textContent = !state.feed && state.view !== "saved" ? "뉴스를 불러오지 못했습니다. 잠시 후 다시 열어 주세요."
    : state.view === "saved" ? "카드에 마우스를 올리고 책갈피를 눌러 저장해 보세요." : "이 카테고리에 기사가 없습니다.";

  $("#foot").textContent = state.feed
    ? `${when(state.feed.generated_at)} 업데이트 · 기사 ${all.length}개 · 각 매체 RSS 기준, 자세한 내용은 원문에서 확인하세요.`
    : "";
}

function setView(view) {
  state.view = view;
  if (view !== "saved") savePrefs();
  render();
  window.scrollTo({ top: 0 });
}

async function markRead(id) {
  state.read[id] = Date.now();
  document.querySelectorAll(`.card[data-id="${id}"]`).forEach((n) => paintRead(n, true));
  const cutoff = Date.now() - 7 * 864e5;   // 7일 지난 읽음 기록 정리
  for (const [k, v] of Object.entries(state.read)) if (v < cutoff) delete state.read[k];
  await store.set("read", state.read);
}

function applyTheme() {
  if (state.theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = state.theme;
  $("#themeBtn").title = THEME_TITLE[state.theme];
  $("#themeBtn").setAttribute("aria-label", THEME_TITLE[state.theme]);
}

function savePrefs() { store.set("prefs", { cat: state.view === "saved" ? "all" : state.view, theme: state.theme }); }

// ── 피드: 캐시 먼저 그리고, 오래됐으면 새로 받아 다시 그림 ──
async function loadFeed() {
  const cached = await store.get("feedCache", null);
  const sameUrl = cached?.url === feedUrl;
  if (sameUrl && cached.feed) { state.feed = { ...cached.feed, items: cached.feed.items.map(normalize) }; render(); }
  if (sameUrl && Date.now() - cached.fetchedAt < REFRESH_MINUTES * 60000) return;
  try {
    const res = await fetch(feedUrl, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const feed = await res.json();
    state.feed = { ...feed, items: (feed.items ?? []).map(normalize) };
    await store.set("feedCache", { feed: state.feed, fetchedAt: Date.now(), url: feedUrl });
  } catch (err) {
    console.warn("feed load failed", err);
  }
  render();
}

async function init() {
  await initUid();
  track("pv");
  state.saved = await store.get("saved", {});
  state.read = await store.get("read", {});
  const prefs = await store.get("prefs", {});
  state.view = CAT_LABEL[prefs.cat] ? prefs.cat : "all";
  state.theme = THEMES.includes(prefs.theme) ? prefs.theme : "system";
  applyTheme();

  $("#savedBtn").onclick = () => setView(state.view === "saved" ? "all" : "saved");
  $("#themeBtn").onclick = () => {
    state.theme = THEMES[(THEMES.indexOf(state.theme) + 1) % THEMES.length];
    applyTheme();
    savePrefs();
  };
  document.querySelector("[data-home]").onclick = (e) => { e.preventDefault(); setView("all"); };
  // URL처럼 보이는 입력은 검색 대신 바로 이동
  $(".search").addEventListener("submit", (e) => {
    const q = e.target.q.value.trim();
    if (/^(https?:\/\/)?[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(q)) {
      e.preventDefault();
      location.href = q.startsWith("http") ? q : `https://${q}`;
    }
  });

  render();
  await loadFeed();
}

init();
