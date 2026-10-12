import json, re, time, hashlib, os
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

BASE = "https://www.prugio.com"
INDEX_URL = f"{BASE}/construction/construction-view.aspx?Pkey=1077"
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive.json"
IMG_DIR = ROOT / "images"
REPORT = ROOT / "backfill-report.json"
DATE_RE = re.compile(r"(20\d{2})[-./](0[1-9]|1[0-2])")
IMAGE_RE = re.compile(r"\.(png|jpe?g|webp)(?:\?.*)?$", re.I)

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
})

def fetch(url):
    response = S.get(url, timeout=45)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response

def month_from_text(text):
    m = DATE_RE.search(text or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(20\d{2})\s*년\s*(0?[1-9]|1[0-2])\s*월", text or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return None

def find_main_image(html):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for tag in soup.select("img[src], a[href]"):
        raw = tag.get("src") or tag.get("href")
        if not raw:
            continue
        url = urljoin(BASE, raw)
        if "/aptimage/" in url.lower() and IMAGE_RE.search(url):
            candidates.append(url)
    if not candidates:
        return None
    # Prefer dated construction-upload image names, which the main progress photos use.
    dated = [u for u in candidates if re.search(r"20\d{4,}", u)]
    return (dated[0] if dated else candidates[0])

def urls_from_value(value):
    found = []
    if not isinstance(value, str):
        return found
    # Direct URLs / JavaScript URLs containing bbsNo.
    for bbs in re.findall(r"bbsNo\s*=\s*['\"]?(\d+)", value, re.I):
        found.append((bbs, value))
    for bbs in re.findall(r"(?:bbsNo|bbs_no)\s*[:=(]\s*['\"]?(\d+)", value, re.I):
        found.append((bbs, value))
    return found

def discover_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for tag in soup.find_all(True):
        label = tag.get_text(" ", strip=True)
        label_month = month_from_text(label)
        attrs = tag.attrs or {}
        attribute_values = []
        for key, val in attrs.items():
            if isinstance(val, list):
                val = " ".join(str(v) for v in val)
            attribute_values.append(str(val))
        # The label and value often live on the same <option>; a numeric option value
        # is treated as a post ID only when its label is a month.
        if tag.name == "option" and label_month:
            val = str(attrs.get("value", "")).strip()
            if re.fullmatch(r"\d{4,}", val):
                found[val] = {"bbsNo": val, "monthLabel": label_month}
        for value in attribute_values:
            for bbs, raw in urls_from_value(value):
                found[bbs] = {"bbsNo": bbs, "monthLabel": label_month}
        # On some page versions, a month selector stores the post ID in value while
        # the click handler is attached to the parent element.
        if label_month:
            for key in ("data-bbsno", "data-bbs-no", "bbsno", "bbsNo"):
                val = attrs.get(key)
                if val and re.fullmatch(r"\d{4,}", str(val).strip()):
                    found[str(val).strip()] = {"bbsNo": str(val).strip(), "monthLabel": label_month}
    return list(found.values())

def run():
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else []
    known_urls = {x.get("sourceImageUrl") for x in archive if x.get("sourceImageUrl")}
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    index_response = fetch(INDEX_URL)
    index_html = index_response.text
    index_soup = BeautifulSoup(index_html, "html.parser")
    index_text = index_soup.get_text(" ", strip=True)
    current_image_url = find_main_image(index_html)
    discovered = discover_posts(index_html)

    # Repair month metadata for already-imported historical records. On detail pages,
    # the first YYYY-MM in page text can be the newest month in the selector, not
    # the month of the selected post. The per-option month label is the correct value.
    post_month_by_id = {p["bbsNo"]: p.get("monthLabel") for p in discovered if p.get("monthLabel")}
    metadata_corrections = []
    for item in archive:
        source = item.get("sourceUrl", "")
        bbs_values = parse_qs(urlparse(source).query).get("bbsNo", [])
        bbs = bbs_values[0] if bbs_values else None
        correct_month = post_month_by_id.get(bbs)
        if not correct_month or not item.get("sourceImageUrl") or not item.get("image"):
            continue
        old_path = ROOT / item["image"]
        ext = Path(urlparse(item["sourceImageUrl"]).path).suffix.lower() or old_path.suffix.lower() or ".png"
        target_path = IMG_DIR / f"{correct_month}{ext}"
        if old_path.exists() and old_path.resolve() != target_path.resolve() and target_path.exists():
            target_path = IMG_DIR / f"{correct_month}-{hashlib.sha1(item['sourceImageUrl'].encode()).hexdigest()[:8]}{ext}"
        if old_path.exists() and old_path.resolve() != target_path.resolve():
            old_path.replace(target_path)
        previous_month = item.get("month")
        previous_image = item.get("image")
        item["month"] = correct_month
        item["image"] = f"images/{target_path.name}"
        if previous_month != correct_month or previous_image != item["image"]:
            metadata_corrections.append({
                "sourceUrl": source,
                "oldMonth": previous_month,
                "newMonth": correct_month,
                "oldImage": previous_image,
                "newImage": item["image"]
            })

    # Add the most recently known historical ID from the archive work so far;
    # duplicate URLs are filtered after the page is fetched.
    known_ids = {"100015"}
    for item in discovered:
        known_ids.add(item["bbsNo"])
    for bbs in known_ids:
        if not any(x["bbsNo"] == bbs for x in discovered):
            discovered.append({"bbsNo": bbs, "monthLabel": None})

    report = {
        "sourcePage": INDEX_URL,
        "runAt": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "currentImageUrl": current_image_url,
        "discoveredPostIds": discovered,
        "metadataCorrections": metadata_corrections,
        "processed": [],
        "errors": []
    }

    if current_image_url:
        month = month_from_text(index_text)
        if not month:
            month = "2026-10"
        existing = next((x for x in archive if x.get("sourceImageUrl") == current_image_url), None)
        if not existing:
            ext = Path(urlparse(current_image_url).path).suffix.lower() or ".png"
            target = IMG_DIR / f"{month}{ext}"
            if target.exists():
                target = IMG_DIR / f"{month}-{hashlib.sha1(current_image_url.encode()).hexdigest()[:8]}{ext}"
            img = S.get(current_image_url, timeout=90)
            img.raise_for_status()
            target.write_bytes(img.content)
            archive.append({
                "month": month, "image": f"images/{target.name}",
                "sourceUrl": INDEX_URL, "sourceImageUrl": current_image_url,
                "description": f"{month} 공사진행 사진"
            })
            known_urls.add(current_image_url)
            report["processed"].append({"month": month, "bbsNo": None, "imageUrl": current_image_url, "status": "added-current"})
        else:
            target = ROOT / existing.get("image", "")
            if existing.get("image") and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                img = S.get(current_image_url, timeout=90)
                img.raise_for_status()
                target.write_bytes(img.content)
                report["processed"].append({"month": existing.get("month"), "bbsNo": None, "imageUrl": current_image_url, "status": "restored-missing-file"})

    # Fetch each post detail page and retain every distinct image we can verify.
    for post in discovered:
        bbs = post["bbsNo"]
        url = f"{INDEX_URL}&bbsNo={bbs}"
        try:
            response = fetch(url)
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ", strip=True)
            image_url = find_main_image(html)
            if not image_url:
                report["errors"].append({"bbsNo": bbs, "url": url, "error": "No /aptimage/ image found"})
                continue
            if image_url in known_urls:
                report["processed"].append({"bbsNo": bbs, "month": post.get("monthLabel") or month_from_text(text), "imageUrl": image_url, "status": "duplicate-skipped"})
                continue

            month = post.get("monthLabel") or month_from_text(text)
            # Prefer month parsed from the image upload name only as a final fallback.
            if not month:
                m = re.search(r"20(\d{2})(0[1-9]|1[0-2])", image_url)
                if m:
                    month = f"20{m.group(1)}-{m.group(2)}"
            if not month:
                report["errors"].append({"bbsNo": bbs, "url": url, "imageUrl": image_url, "error": "Could not determine month"})
                continue

            ext = Path(urlparse(image_url).path).suffix.lower() or ".png"
            target = IMG_DIR / f"{month}{ext}"
            if target.exists():
                target = IMG_DIR / f"{month}-{hashlib.sha1(image_url.encode()).hexdigest()[:8]}{ext}"

            img = S.get(image_url, timeout=90)
            img.raise_for_status()
            target.write_bytes(img.content)

            description = f"{month} 공사진행 사진"
            m = re.search(r"(20\d{2}년\s*\d{1,2}월\s*말\s*기준\s*공사\s*진행현황)", text)
            if m:
                description = m.group(1)

            archive.append({
                "month": month,
                "image": f"images/{target.name}",
                "sourceUrl": url,
                "sourceImageUrl": image_url,
                "description": description
            })
            known_urls.add(image_url)
            report["processed"].append({"bbsNo": bbs, "month": month, "imageUrl": image_url, "status": "added", "localImage": f"images/{target.name}"})
            print(f"Added {month} from bbsNo={bbs}: {target.name}")
            time.sleep(0.25)
        except Exception as exc:
            report["errors"].append({"bbsNo": bbs, "url": url, "error": str(exc)})
            print(f"Problem for bbsNo={bbs}: {exc}")

    # Build and commit a discovery report even if the live HTML structure changes.
    archive.sort(key=lambda x: (x.get("month", ""), x.get("sourceImageUrl", "")))
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"discovered={len(discovered)}\n")
            f.write(f"added={sum(1 for x in report['processed'] if x['status'].startswith('added'))}\n")
    print(f"Discovered post IDs: {len(discovered)}")
    print(f"New images added: {sum(1 for x in report['processed'] if x['status'].startswith('added'))}")
    print(f"Errors recorded: {len(report['errors'])}")

if __name__ == "__main__":
    run()
