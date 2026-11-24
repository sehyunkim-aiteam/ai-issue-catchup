"""수집할 소스 목록 — 한국어 콘텐츠만.

url: RSS 주소. 없으면 RSS로는 수집하지 않는다.
fishcrawl: 사내 크롤러(fishcrawl) 프로젝트 ID. 있으면 크롤러 수집분을 함께 쓴다(RSS와 같은 기사는 RSS 쪽을 쓴다).

category: 키워드 규칙에 안 걸릴 때 쓰는 기본 분류.
max_items: 소스 하나가 피드를 도배하지 않도록 회당 남길 최대 기사 수(필터 통과 기준).
require_ai: True면 제목·본문에 AI 관련 키워드가 있는 기사만 남긴다. 종합 IT·비즈니스 매체용.
"""

SOURCES = [
    # AI 전문 매체 — 전부 남김
    {"id": "aitimes", "name": "AI타임스", "url": "https://www.aitimes.com/rss/allArticle.xml", "category": "ai", "max_items": 15, "fishcrawl": "ba01574062024408b636943aa71aa5b4"},
    {"id": "aitimes-kr", "name": "인공지능신문", "url": "https://www.aitimes.kr/rss/allArticle.xml", "category": "ai", "max_items": 10, "fishcrawl": "07c84aab5da14d69a0c65cf7510e8f46"},
    {"id": "newstheai", "name": "더에이아이", "url": "https://www.newstheai.com/rss/allArticle.xml", "category": "ai", "max_items": 10, "fishcrawl": "0f7cbf7c9b0d4861a786eb6938de5e9b"},
    {"id": "pytorchkr", "name": "PyTorchKR", "url": "https://discuss.pytorch.kr/latest.rss", "category": "ai", "max_items": 8, "fishcrawl": "930d25429cbf43758a0b13f915ad608c"},
    # 개발·바이브 코딩
    {"id": "geeknews", "name": "GeekNews", "url": "https://news.hada.io/rss/news", "category": "vibe_coding", "max_items": 15, "fishcrawl": "89cd1f21fccb443592189861416b6f6d"},
    {"id": "yozm", "name": "요즘IT", "url": "https://yozm.wishket.com/magazine/feed/", "category": "vibe_coding", "max_items": 10},
    {"id": "toss", "name": "토스 테크", "url": "https://toss.tech/rss.xml", "category": "vibe_coding", "max_items": 5, "fishcrawl": "696b0f227bb648b99f8982be68bc7780"},
    {"id": "kakao", "name": "카카오 테크", "url": "https://tech.kakao.com/feed/", "category": "vibe_coding", "max_items": 5},
    # 종합 IT·비즈니스 — AI 관련 기사만
    {"id": "bloter", "name": "블로터", "url": "https://www.bloter.net/rss/allArticle.xml", "category": "business", "max_items": 12, "require_ai": True, "fishcrawl": "a91837f913c548778a2bad6eb6d3331a"},
    {"id": "byline", "name": "바이라인네트워크", "url": "https://byline.network/feed/", "category": "business", "max_items": 10, "require_ai": True},
    {"id": "platum", "name": "플래텀", "url": "https://platum.kr/feed", "category": "business", "max_items": 8, "require_ai": True},
    {"id": "venturesquare", "name": "벤처스퀘어", "url": "https://www.venturesquare.net/feed", "category": "business", "max_items": 8, "require_ai": True, "fishcrawl": "e42e6c5e4dea4945a695a6bebf44e9f5"},
    {"id": "outstanding", "name": "아웃스탠딩", "url": "https://outstanding.kr/rss", "category": "business", "max_items": 8, "require_ai": True},
    {"id": "mobiinside", "name": "모비인사이드", "url": "https://www.mobiinside.co.kr/feed/", "category": "business", "max_items": 8, "require_ai": True, "fishcrawl": "9ee017a3656c44bca23a0fea784b488a"},
]
