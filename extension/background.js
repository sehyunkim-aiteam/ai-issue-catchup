// 설치·업데이트·제거 기록. 새 탭 화면(newtab.js)과 같은 uid·GA4 Measurement Protocol을 쓴다.
// - 설치(install)·업데이트(update): chrome.runtime.onInstalled에서 바로 보낸다.
// - 제거: 확장은 제거되는 순간 코드가 돌지 않는다. 대신 크롬이 제거 직후 setUninstallURL 주소를 새 탭으로 연다.
//   그 주소(Pages의 bye.html)가 uninstall 이벤트와 제거 사유 설문을 보낸다. uid·버전·설치일을 쿼리로 넘긴다.
import { FEED_URL, GA_MEASUREMENT_ID, GA_API_SECRET } from "./config.js";

const SESSION_IDLE_MS = 30 * 60 * 1000;
const LOG_URL = GA_MEASUREMENT_ID && GA_API_SECRET
  ? `https://www.google-analytics.com/mp/collect?measurement_id=${GA_MEASUREMENT_ID}&api_secret=${GA_API_SECRET}`
  : "";
const BYE_URL = new URL("bye.html", FEED_URL).href;
const VERSION = chrome.runtime.getManifest().version;

async function ensureIds() {
  let { uid, session, installedAt } = await chrome.storage.local.get(["uid", "session", "installedAt"]);
  const now = Date.now();
  if (!uid) uid = crypto.randomUUID();
  const sessionId = session && now - session.last < SESSION_IDLE_MS ? session.id : String(Math.floor(now / 1000));
  await chrome.storage.local.set({ uid, session: { id: sessionId, last: now } });
  return { uid, sessionId, installedAt };
}

async function send(uid, sessionId, name, params = {}) {
  if (!LOG_URL) return;
  const body = JSON.stringify({
    client_id: uid,
    events: [{ name, params: {
      session_id: sessionId, engagement_time_msec: 1,
      platform: "extension", app_version: VERSION, ...params,
    } }],
  });
  try {
    await fetch(LOG_URL, { method: "POST", body, mode: "no-cors", headers: { "Content-Type": "text/plain" } });
  } catch { /* 오프라인이면 기록만 빠진다 */ }
}

function setUninstallUrl(uid, installedAt) {
  const q = new URLSearchParams({ uid, v: VERSION });
  if (installedAt) q.set("i", String(installedAt));   // 설치 시각(ms) → 사용 기간 계산용. 0.1.3 이전 설치자는 없음
  chrome.runtime.setUninstallURL(`${BYE_URL}?${q}`);
}

chrome.runtime.onInstalled.addListener(async ({ reason, previousVersion }) => {
  if (reason !== "install" && reason !== "update") return;   // chrome_update·shared_module_update는 무시
  const ids = await ensureIds();
  let installedAt = ids.installedAt;
  if (reason === "install") {
    installedAt = Date.now();
    await chrome.storage.local.set({ installedAt });
    await send(ids.uid, ids.sessionId, "install");
  } else {
    await send(ids.uid, ids.sessionId, "update", { previous_version: previousVersion || "" });
  }
  setUninstallUrl(ids.uid, installedAt);
});
