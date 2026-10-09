import json, re, hashlib
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = "https://www.prugio.com"
INDEX_URL = f"{BASE}/construction/construction-view.aspx?Pkey=1077"
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive.json"
IMG_DIR = ROOT / "images"

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
})

def fetch(url):
    r = S.get(url, timeout=40)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r

def get_month(text):
    # 현재 페이지는 "2026-09 2026-08월 촬영"처럼 표시하고,
    # 본문에는 "2026년 8월 말 기준"이 표시됨.
    m = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(20\d{2})\s*년\s*(0?[1-9]|1[0-2])\s*월", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None

def find_current_image(html):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for tag in soup.select("img[src], a[href]"):
        raw = tag.get("src") or tag.get("href")
        if not raw:
            continue
        u = urljoin(BASE, raw)
        if "/aptimage/" in u.lower() and re.search(r"\.(png|jpe?g|webp)(?:\?.*)?$", u, re.I):
            candidates.append(u)
    # 현재 페이지의 본문 이미지가 첫 후보인 구조를 우선 사용.
    # 여러 개라면 /aptimage/ 이미지 중 파일명에 날짜가 있는 후보를 우선.
    dated = [u for u in candidates if re.search(r"20\d{4,}", u)]
    return (dated[0] if dated else candidates[0]) if candidates else None

def main():
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else []
    known_urls = {x.get("sourceImageUrl") for x in archive if x.get("sourceImageUrl")}

    page = fetch(INDEX_URL)
    soup = BeautifulSoup(page.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    image_url = find_current_image(page.text)
    if not image_url:
        raise RuntimeError("Pkey=1077 페이지에서 /aptimage/ 공사진행 이미지를 찾지 못했습니다.")

    if image_url in known_urls:
        print("No new construction image.")
        print("Current image:", image_url)
        return

    month = get_month(text)
    if not month:
        # 이미지 URL의 YYYYMM에서 마지막 안전망
        m = re.search(r"(20\d{2})(0[1-9]|1[0-2])", image_url)
        if m:
            month = f"{m.group(1)}-{m.group(2)}"
    if not month:
        raise RuntimeError("새 이미지의 기준월을 판별하지 못했습니다.")

    ext = Path(image_url.split("?",1)[0]).suffix.lower() or ".png"
    target = IMG_DIR / f"{month}{ext}"
    if target.exists():
        # 같은 월에 다른 이미지가 올라오는 경우 기존 파일 보존
        short = hashlib.sha1(image_url.encode()).hexdigest()[:8]
        target = IMG_DIR / f"{month}-{short}{ext}"

    img = S.get(image_url, timeout=90)
    img.raise_for_status()
    target.write_bytes(img.content)

    # 설명은 본문에서 해당 월의 공사진행 문장을 간단히 보존
    description = f"{month} 공사진행 사진"
    m = re.search(r"(20\d{2}년\s*\d{1,2}월\s*말\s*기준\s*공사\s*진행현황)", text)
    if m:
        description = m.group(1)

    archive.append({
        "month": month,
        "image": f"images/{target.name}",
        "sourceUrl": INDEX_URL,
        "sourceImageUrl": image_url,
        "description": description
    })
    archive.sort(key=lambda x: x.get("month",""))
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")

    print("NEW IMAGE SAVED")
    print("month:", month)
    print("image:", image_url)
    print("saved:", target)

if __name__ == "__main__":
    main()
