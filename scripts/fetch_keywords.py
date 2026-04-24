"""
네이버 검색광고 API 키워드 데이터 수집 스크립트
GitHub Actions에서 매월 자동 실행
"""
import os, json, time, hmac, hashlib, base64
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from pathlib import Path

API_BASE = "https://api.searchad.naver.com"
KEYWORDS_FILE = "config/keywords.json"
DATA_DIR = "data"
HISTORY_FILE = f"{DATA_DIR}/history.json"

def get_env():
    cid = os.environ.get("NAVER_CUSTOMER_ID", "")
    key = os.environ.get("NAVER_API_KEY", "")
    sec = os.environ.get("NAVER_SECRET_KEY", "")
    if not all([cid, key, sec]):
        raise ValueError("환경변수 NAVER_CUSTOMER_ID, NAVER_API_KEY, NAVER_SECRET_KEY 필요")
    return cid, key, sec

def sign(ts, method, uri, secret):
    msg = f"{ts}.{method}.{uri}"
    return base64.b64encode(
        hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()

def fetch_keywords(keywords, cid, key, sec):
    uri = "/keywordstool"
    results = {}
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i+5]
        ts = str(int(time.time() * 1000))
        sig = sign(ts, "GET", uri, sec)
        params = urlencode({"hintKeywords": ",".join(batch), "showDetail": "1"}, quote_via=quote)
        url = f"{API_BASE}{uri}?{params}"
        req = Request(url)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Timestamp", ts)
        req.add_header("X-API-KEY", key)
        req.add_header("X-Customer", cid)
        req.add_header("X-Signature", sig)
        try:
            with urlopen(req) as r:
                data = json.loads(r.read().decode())
            for item in data.get("keywordList", []):
                kw = item.get("relKeyword", "")
                if kw.lower() in [k.lower() for k in batch]:
                    pc = item.get("monthlyPcQcCnt", 0)
                    mo = item.get("monthlyMobileQcCnt", 0)
                    pc = 0 if not isinstance(pc, (int, float)) else int(pc)
                    mo = 0 if not isinstance(mo, (int, float)) else int(mo)
                    results[kw] = {"pc": pc, "mo": mo, "total": pc + mo}
            print(f"  ✓ {', '.join(batch)}")
        except Exception as e:
            print(f"  ✗ {', '.join(batch)}: {e}")
        if i + 5 < len(keywords):
            time.sleep(1)
    return results

def main():
    now = datetime.now()
    label = f"{str(now.year)[2:]}년 {now.month}월"
    print(f"🚀 네이버 키워드 수집 - {label}")

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    tags = config.get("tags", {})
    all_kw = []
    for kws in tags.values():
        all_kw.extend(kws)
    all_kw = list(set(all_kw))
    print(f"📋 {len(all_kw)}개 키워드")

    cid, key, sec = get_env()
    print("🌐 API 호출 중...")
    results = fetch_keywords(all_kw, cid, key, sec)
    print(f"✅ {len(results)}개 수집 완료\n")

    for kw in sorted(results.keys()):
        d = results[kw]
        print(f"  {kw:<15} PC:{d['pc']:>7,}  MO:{d['mo']:>9,}  합계:{d['total']:>9,}")

    # Load history (tag-based structure)
    Path(DATA_DIR).mkdir(exist_ok=True)
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    # Update each tag
    for tag, kws in tags.items():
        if tag not in history:
            history[tag] = {}
        if label not in history[tag]:
            history[tag][label] = {}
        for kw in kws:
            if kw in results:
                history[tag][label][kw] = results[kw]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"\n💾 저장: {HISTORY_FILE}")
    print("🎉 완료!")

if __name__ == "__main__":
    main()
