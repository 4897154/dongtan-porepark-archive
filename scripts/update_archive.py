import json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = "https://www.prugio.com"
INDEX_URL = f"{BASE}/construction/construction-view.aspx?Pkey=1077"
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive.json"
IMG_DIR = ROOT / "images"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; PoreParkArchive/1.0)"
})

def get(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text

def extract_candidates(html):
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    # 현재 페이지가 가리키는 공사진행 상세 URL 후보
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        full = urljoin(BASE, href)
        if "construction-view.aspx" in full and "Pkey=1077" in full:
            urls.append(full)

    # 현재 페이지 자체도 후보
    urls.append(INDEX_URL)

    # 중복 제거
    out = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u); out.append(u)
    return out

def bbs_no(url):
    m = re.search(r"(?:[?&])bbsNo=(\d+)", url, re.I)
    return m.group(1) if m else None

def month_from_text(text):
    # "2026년 8월 말 기준" 등
    m = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # 파일명 등에 있는 YYYYMM
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None

def find_image(detail_html, detail_url):
    soup = BeautifulSoup(detail_html, "html.parser")
    candidates = []
    for tag in soup.select("img[src], a[href]"):
        u = tag.get("src") or tag.get("href")
        if not u: continue
        full = urljoin(BASE, u)
        low = full.lower()
        if "/aptimage/" in low and re.search(r"\.(png|jpe?g|webp)(?:\?|$)", low):
            candidates.append(full)
    # 페이지 안의 aptimage 후보 중 큰 원본을 우선할 수 있도록 순서를 유지
    return candidates[0] if candidates else None

def main():
    old = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else []
    known = {str(x.get("bbsNo")) for x in old if x.get("bbsNo")}

    index_html = get(INDEX_URL)
    candidates = extract_candidates(index_html)

    # 최신 게시물을 먼저 처리하기 위해 bbsNo가 존재하는 후보를 순서대로 확인
    detail = None
    for u in candidates:
        n = bbs_no(u)
        if n:
            try:
                html = get(u)
                detail = (u, n, html)
                # 인덱스에서 발견된 첫 상세 URL을 최신 후보로 사용
                break
            except Exception:
                pass

    if not detail:
        raise RuntimeError("Pkey=1077의 공사진행 상세 게시물을 찾지 못했습니다.")

    url, n, html = detail

    if n in known:
        print(f"No new BBSno: {n}")
        return

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    month = month_from_text(text) or month_from_text(url) or time.strftime("%Y-%m")

    image_url = find_image(html, url)
    if not image_url:
        raise RuntimeError(f"새 게시물 {n}에서 /aptimage/ 이미지를 찾지 못했습니다.")

    ext = Path(urlparse(image_url).path).suffix.lower() or ".png"
    filename = f"{month}{ext}"
    target = IMG_DIR / filename

    # 같은 월 파일이 이미 있다면 덮어쓰지 않고 안전하게 별도 파일 생성
    if target.exists():
        filename = f"{month}-bbs{n}{ext}"
        target = IMG_DIR / filename

    data = session.get(image_url, timeout=60)
    data.raise_for_status()
    target.write_bytes(data.content)

    old.append({
        "month": month,
        "bbsNo": n,
        "image": f"images/{filename}",
        "sourceUrl": url,
        "description": f"{month.replace('-', '년 ')}월 공사진행"
    })
    old.sort(key=lambda x: x.get("month",""))
    ARCHIVE.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Added {month} / BBSno {n} / {target}")

if __name__ == "__main__":
    main()
