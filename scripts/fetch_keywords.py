"""
네이버 키워드 데이터 수집 스크립트
1) 검색광고 API → PC/모바일 검색수
2) 데이터랩 API → 성별/연령별 검색 비율
"""
import os, json, time, hmac, hashlib, base64
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from pathlib import Path

API_BASE = "https://api.searchad.naver.com"
DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
KEYWORDS_FILE = "config/keywords.json"
DATA_DIR = "data"
HISTORY_FILE = f"{DATA_DIR}/history.json"
DEMO_FILE = f"{DATA_DIR}/demographics.json"

def get_env():
    cid = os.environ.get("NAVER_CUSTOMER_ID", "")
    key = os.environ.get("NAVER_API_KEY", "")
    sec = os.environ.get("NAVER_SECRET_KEY", "")
    dl_id = os.environ.get("NAVER_DATALAB_CLIENT_ID", "")
    dl_sec = os.environ.get("NAVER_DATALAB_CLIENT_SECRET", "")
    if not all([cid, key, sec]):
        raise ValueError("검색광고 API 환경변수 필요")
    return cid, key, sec, dl_id, dl_sec

def sign(ts, method, uri, secret):
    msg = f"{ts}.{method}.{uri}"
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()

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
            print(f"  ✓ 검색량: {', '.join(batch)}")
        except Exception as e:
            print(f"  ✗ 검색량 실패: {', '.join(batch)}: {e}")
        if i + 5 < len(keywords):
            time.sleep(1)
    return results

def fetch_demographics(keywords, dl_id, dl_sec):
    """데이터랩 API로 성별/연령별 검색 비율 조회"""
    if not dl_id or not dl_sec:
        print("  ⚠ 데이터랩 API 키 없음 - 건너뜀")
        return {}

    now = datetime.now()
    # 최근 1개월 데이터
    end = now.strftime("%Y-%m-%d")
    start = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    results = {}
    genders = {"f": "여성", "m": "남성"}
    ages = {"1": "0~12세", "2": "13~18세", "3": "19~24세", "4": "25~29세",
            "5": "30~34세", "6": "35~39세", "7": "40~44세", "8": "45~49세",
            "9": "50~54세", "10": "55~59세", "11": "60세이상"}

    for kw in keywords:
        demo = {"gender": {}, "age": {}}

        # 성별 조회
        try:
            for g_code, g_label in genders.items():
                body = json.dumps({
                    "startDate": start,
                    "endDate": end,
                    "timeUnit": "month",
                    "keywordGroups": [{"groupName": kw, "keywords": [kw]}],
                    "gender": g_code
                }).encode()
                req = Request(DATALAB_URL, data=body, method="POST")
                req.add_header("X-Naver-Client-Id", dl_id)
                req.add_header("X-Naver-Client-Secret", dl_sec)
                req.add_header("Content-Type", "application/json")
                with urlopen(req) as r:
                    data = json.loads(r.read().decode())
                ratio = 0
                for result in data.get("results", []):
                    for d in result.get("data", []):
                        ratio = d.get("ratio", 0)
                demo["gender"][g_label] = round(ratio, 1)
                time.sleep(0.2)
        except Exception as e:
            print(f"  ⚠ 성별 조회 실패 [{kw}]: {e}")

        # 연령별 조회
        try:
            age_ratios = {}
            for a_code, a_label in ages.items():
                body = json.dumps({
                    "startDate": start,
                    "endDate": end,
                    "timeUnit": "month",
                    "keywordGroups": [{"groupName": kw, "keywords": [kw]}],
                    "ages": [a_code]
                }).encode()
                req = Request(DATALAB_URL, data=body, method="POST")
                req.add_header("X-Naver-Client-Id", dl_id)
                req.add_header("X-Naver-Client-Secret", dl_sec)
                req.add_header("Content-Type", "application/json")
                with urlopen(req) as r:
                    data = json.loads(r.read().decode())
                ratio = 0
                for result in data.get("results", []):
                    for d in result.get("data", []):
                        ratio = d.get("ratio", 0)
                age_ratios[a_label] = round(ratio, 1)
                time.sleep(0.1)

            # 10대, 20대, 30대, 40대, 50대이상으로 그룹핑
            grouped = {
                "10대": age_ratios.get("13~18세", 0),
                "20대": round(age_ratios.get("19~24세", 0) + age_ratios.get("25~29세", 0), 1),
                "30대": round(age_ratios.get("30~34세", 0) + age_ratios.get("35~39세", 0), 1),
                "40대": round(age_ratios.get("40~44세", 0) + age_ratios.get("45~49세", 0), 1),
                "50대이상": round(age_ratios.get("50~54세", 0) + age_ratios.get("55~59세", 0) + age_ratios.get("60세이상", 0), 1),
            }
            demo["age"] = grouped
        except Exception as e:
            print(f"  ⚠ 연령 조회 실패 [{kw}]: {e}")

        results[kw] = demo
        print(f"  ✓ 인구통계: {kw}")
        time.sleep(0.3)

    return results

def main():
    now = datetime.now()
    label = f"{str(now.year)[2:]}년 {now.month}월"
    print(f"🚀 네이버 키워드 수집 - {label}")

    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    tags = config.get("tags", {})
    all_kw = list(set(kw for kws in tags.values() for kw in kws))
    print(f"📋 {len(all_kw)}개 키워드\n")

    cid, key, sec, dl_id, dl_sec = get_env()

    # 1. 검색량 수집
    print("🌐 검색광고 API 호출...")
    search_results = fetch_keywords(all_kw, cid, key, sec)
    print(f"✅ 검색량 {len(search_results)}개 완료\n")

    # 2. 성별/연령 수집
    print("👥 데이터랩 API 호출...")
    demo_results = fetch_demographics(all_kw, dl_id, dl_sec)
    print(f"✅ 인구통계 {len(demo_results)}개 완료\n")

    # 결과 출력
    for kw in sorted(search_results.keys()):
        d = search_results[kw]
        print(f"  {kw:<15} PC:{d['pc']:>7,}  MO:{d['mo']:>9,}  합계:{d['total']:>9,}")

    # 저장 - 검색량
    Path(DATA_DIR).mkdir(exist_ok=True)
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    for t, kws in tags.items():
        if t not in history: history[t] = {}
        if label not in history[t]: history[t][label] = {}
        for kw in kws:
            if kw in search_results:
                history[t][label][kw] = search_results[kw]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 저장 - 인구통계
    demographics = {}
    if os.path.exists(DEMO_FILE):
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            demographics = json.load(f)

    if label not in demographics:
        demographics[label] = {}
    demographics[label].update(demo_results)

    with open(DEMO_FILE, "w", encoding="utf-8") as f:
        json.dump(demographics, f, ensure_ascii=False, indent=2)

    print(f"\n💾 저장 완료")
    print("🎉 완료!")

if __name__ == "__main__":
    main()
