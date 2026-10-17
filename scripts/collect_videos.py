#!/usr/bin/env python3
"""유튜브 쇼츠 수집기 -> data/videos.json

영상 파일을 받아오는 게 아니라 영상 ID + 제목만 저장한다. 재생은 사이트에서 유튜브 공식 플레이어로 함.
필요: 환경변수 YOUTUBE_API_KEY (구글 클라우드에서 'YouTube Data API v3' 를 켜고 API 키 발급)

사용:  python scripts/collect_videos.py            (실제 저장)
       python scripts/collect_videos.py --dry-run  (저장 안 하고 결과만 출력)

쿼터: 검색 1번에 100 단위가 들어간다. 내가 알기론 무료 한도가 하루 1만 단위라서
      (검색 횟수 = 카테고리 수 x VIDEO_SEARCHES) 가 하루 100번을 넘지 않게 맞춰.
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import is_blocked  # noqa  (싫어하는 주제 필터를 같이 씀)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "videos.json")

KEY = os.environ.get("YOUTUBE_API_KEY", "")
SEARCHES = int(os.environ.get("VIDEO_SEARCHES", "1"))      # 카테고리당 검색 횟수 (1번 = 100 쿼터)
MAX_SEC = int(os.environ.get("SHORT_MAX_SEC", "61"))        # 이 길이(초) 이하만 (쇼츠)
MAX_ITEMS = int(os.environ.get("MAX_VIDEOS", "3000"))
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "30"))    # API 약관상 저장한 정보는 오래 안 두는 게 안전해서 30일 지나면 지움
DRY = "--dry-run" in sys.argv
UA = "RandomKnowledgeTV/1.0 (personal hobby project)"

# 채널(카테고리) -> 검색어. 여기를 고치면 채널이 바뀜. 영상은 '#shorts' 를 붙여서 쇼츠 위주로 찾음.
VIDEO_QUERIES = {
    "웃김": ["웃긴 영상 #shorts", "개그 상황극 #shorts", "웃긴 실수 #shorts"],
    "동물": ["귀여운 동물 #shorts", "고양이 #shorts", "강아지 #shorts", "신기한 동물 #shorts"],
    "먹방": ["먹방 #shorts", "길거리 음식 #shorts", "요리 레시피 #shorts"],
    "만족": ["만족스러운 영상 #shorts", "oddly satisfying #shorts", "ASMR #shorts"],
    "잡학": ["신기한 사실 #shorts", "알고 보면 #shorts", "잡학 #shorts"],
    "미스터리": ["미스터리 #shorts", "미제사건 #shorts", "괴담 #shorts"],
    "여행": ["여행 브이로그 #shorts", "풍경 #shorts", "세계 여행 #shorts"],
    "음악": ["노래 커버 #shorts", "버스킹 #shorts", "연주 #shorts"],
}


def api(endpoint, params):
    params = dict(params, key=KEY)
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}")


def iso_to_sec(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 10 ** 6
    dd, hh, mm, ss = (int(x or 0) for x in m.groups())
    return dd * 86400 + hh * 3600 + mm * 60 + ss


def search_ids(query):
    res = api("search", {
        "part": "snippet", "type": "video", "videoDuration": "short", "videoEmbeddable": "true",
        "maxResults": 25, "q": query, "regionCode": "KR", "relevanceLanguage": "ko",
        "safeSearch": "moderate", "order": random.choice(["relevance", "date", "viewCount"]),
    })
    return [x["id"]["videoId"] for x in res.get("items", []) if x.get("id", {}).get("videoId")]


def details(ids):
    out = {}
    for i in range(0, len(ids), 50):
        res = api("videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids[i:i + 50])})
        for it in res.get("items", []):
            out[it["id"]] = it
    return out


def load():
    try:
        with open(DATA, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except FileNotFoundError:
        return []


def main():
    if not KEY:
        print("YOUTUBE_API_KEY 가 없어서 건너뜀 (깃허브 Settings > Secrets 에 추가해)")
        return
    items = load()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).date().isoformat()
    kept = [x for x in items if x.get("added", "9999") >= cutoff and not is_blocked(x.get("t"), x.get("ch"))]
    if len(kept) != len(items):
        print(f"오래됐거나 싫어하는 주제라서 {len(items) - len(kept)}개 지움")
    have = {x["id"] for x in kept}
    new = []
    today = datetime.now(timezone.utc).date().isoformat()
    for cat, queries in VIDEO_QUERIES.items():
        got = 0
        for q in random.sample(queries, min(SEARCHES, len(queries))):
            try:
                ids = [i for i in search_ids(q) if i not in have]
                info = details(ids) if ids else {}
            except Exception as e:  # noqa
                print("실패", cat, q, e)
                if "quota" in str(e).lower():
                    print("쿼터가 다 찼어. 내일 다시 돌려")
                    break
                continue
            for vid in ids:
                it = info.get(vid)
                if not it:
                    continue
                sn, st = it.get("snippet", {}), it.get("status", {})
                sec = iso_to_sec(it.get("contentDetails", {}).get("duration"))
                if not st.get("embeddable") or st.get("privacyStatus") != "public" or sec > MAX_SEC:
                    continue
                title, ch = sn.get("title", ""), sn.get("channelTitle", "")
                if is_blocked(title, ch, sn.get("description", "")[:200]):
                    continue
                new.append({"id": vid, "c": cat, "t": title[:100], "ch": ch[:40], "sec": sec, "added": today})
                have.add(vid)
                got += 1
            time.sleep(0.3)
        print(f"  [{cat}] +{got}")
    print(f"새로 {len(new)}개")
    if DRY:
        print(json.dumps(new[:10], ensure_ascii=False, indent=1))
        return
    out = (kept + new)[-MAX_ITEMS:]
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
