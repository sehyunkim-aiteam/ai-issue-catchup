// 확장에서 읽을 feed.json 주소. repo를 만든 뒤 <user>/<repo>로 바꾼다.
// 웹(GitHub Pages·로컬 http)으로 열면 같은 폴더의 feed.json을 읽으므로 이 값은 확장 전용이다.
export const FEED_URL = "https://sehyunkim-aiteam.github.io/ai-issue-catchup/feed.json";
export const REFRESH_MINUTES = 30;
// 행동 로그(PV·CLICK) → GA4 Measurement Protocol. 둘 중 하나라도 비어 있으면 아무것도 보내지 않는다.
// api_secret은 전송 전용(데이터 조회 불가)이고, 클라이언트 전송 구조상 공개될 수밖에 없다.
export const GA_MEASUREMENT_ID = "G-3FDTV66F4V";
export const GA_API_SECRET = "Q6q6UgXsT1GzHyjp8Yqhgg";
