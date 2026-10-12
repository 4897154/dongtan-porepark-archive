import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive.json"
OUT = ROOT / "images" / "timelapse.gif"

WIDTH, HEIGHT = 1000, 700
MARGIN = 22
CAPTION_HEIGHT = 64
BACKGROUND = (246, 248, 251)
TEXT = (24, 36, 58)

def font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()

def main():
    if not ARCHIVE.exists():
        raise FileNotFoundError("archive.json was not found")

    records = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    records = sorted(records, key=lambda row: row.get("month", ""))
    frames = []
    used_months = []

    for record in records:
        rel = record.get("image")
        if not rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            print(f"Skipping missing image: {path}")
            continue
        try:
            with Image.open(path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail((WIDTH - 2 * MARGIN, HEIGHT - CAPTION_HEIGHT - 2 * MARGIN), Image.Resampling.LANCZOS)

                frame = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
                x = (WIDTH - image.width) // 2
                y = MARGIN + (HEIGHT - CAPTION_HEIGHT - 2 * MARGIN - image.height) // 2
                frame.paste(image, (x, y))

                draw = ImageDraw.Draw(frame)
                label = f"CONSTRUCTION PROGRESS  |  {record.get('month', 'Unknown month')}"
                fnt = font(25)
                box = draw.textbbox((0, 0), label, font=fnt)
                label_width = box[2] - box[0]
                draw.text(((WIDTH - label_width) // 2, HEIGHT - CAPTION_HEIGHT + 12), label, fill=TEXT, font=fnt)

                frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
                used_months.append(record.get("month", ""))
        except Exception as exc:
            print(f"Skipping unreadable image {path}: {exc}")

    if not frames:
        raise RuntimeError("No readable archive images were available to create the timelapse.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=900,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Created {OUT}")
    print(f"Frames: {len(frames)}")
    print(f"Timeline: {used_months[0]} -> {used_months[-1]}")
    print(f"GIF size: {OUT.stat().st_size:,} bytes")

if __name__ == "__main__":
    main()
