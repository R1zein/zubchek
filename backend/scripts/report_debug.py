"""Show how a saved report was scored: tooth frames + what each pixel counted as.

Runs inside the backend container on the server, e.g. from the Timeweb web
console (no computer needed):

    cd /opt/zubchek && curl -sL https://raw.githubusercontent.com/R1zein/zubchek/main/backend/scripts/report_debug.py | docker compose exec -T backend python - 72

Re-scores the report's photo with its stored tooth/quadrant frames, uploads
one picture (photo with yellow tooth / green quadrant frames | pixel mask:
white = clean enamel, purple/blue/cyan = plaque, red = gum, dimmed = not
counted) to object storage and prints its link plus a per-tooth summary.
Nothing in the database is changed.
"""

import asyncio
import base64
import io
import json
import os
import sys
import urllib.request

from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.pixel_analysis import analyze_teeth_in_boxes
from services.s3_storage import store_image


def _data_uri(image_ref: str) -> str:
    if image_ref.startswith("data:"):
        return image_ref
    raw = urllib.request.urlopen(image_ref, timeout=30).read()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode()


def _img(data_uri: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1]))).convert("RGB")


async def main(report_id: int) -> None:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT image_data, analysis_data FROM reports WHERE id = :id"), {"id": report_id}
        )).fetchone()
    await engine.dispose()
    if not row:
        print(f"report {report_id} not found")
        return

    data = json.loads(row[1]) if row[1] else {}
    image_ref = row[0] or ""
    print(f"report {report_id}: method={data.get('method')} index={data.get('pollution_percentage')}%")
    print(f"photo: {image_ref if not image_ref.startswith('data:') else '(stored in database)'}")
    boxes = data.get("tooth_boxes") or {}
    if not boxes:
        print("no tooth frames stored (scored by the whole-photo fallback)")
        return

    res = analyze_teeth_in_boxes(_data_uri(image_ref), boxes, data.get("quadrant_boxes"), debug=True)
    left, right = _img(res["annotated_image"]), _img(res["debug_image"])
    sheet = Image.new("RGB", (left.width + right.width + 10, left.height), (255, 255, 255))
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width + 10, 0))
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=85)
    link = store_image("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    print("frames picture:", link if link.startswith("http") else "(upload failed — storage not configured)")

    print(f"frames: {len(boxes)}/12  gains={res.get('white_balance_gains')}")
    for tid, t in res["teeth"].items():
        if t["missing"]:
            print(f"  {tid}: {'no frame' if tid not in boxes else 'frame has too little tooth surface'}")
        else:
            print(f"  {tid}: plaque {t['pollution_percentage']}%  white {t['white']} purple {t['purple']} "
                  f"blue {t['blue']} light_blue {t['light_blue']}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
