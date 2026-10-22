"""R5 Multimodal, data preparation.

Builds the inputs for the three table arms from the Meridian product catalog:

  1. renders the catalog tables as a PNG page image (stands in for a scanned or PDF table)
  2. control arm: parses the markdown tables with plain code into one text document per
     product, no vision involved
  3. vision arm: sends the PNG to Gemini, which reads the image and writes one text
     document per product, one sentence per attribute
  4. checks the vision output against the control, every number in the control text
     should appear in the vision text for the same product

Run from the repo root:
    pip install pillow
    python rag-r5-multimodal\\prepare_r5.py

Env knobs: RAG_PROJECT, RAG_LOCATION (default global), RAG_GEMINI (default
gemini-3.8-flash).

Outputs under rag-r5-multimodal\\data\\ : catalog.png, control\\*.txt, vision\\*.txt
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error

from PIL import Image, ImageDraw, ImageFont

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

CATALOG = os.path.join("rag-lab", "r0-foundation", "corpus", "product_catalog.md")
DATA = os.path.join("rag-r5-multimodal", "data")
PNG = os.path.join(DATA, "catalog.png")
CONTROL_DIR = os.path.join(DATA, "control")
VISION_DIR = os.path.join(DATA, "vision")


def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True,
        shell=(os.name == "nt"),
    ).strip()


# --- parse the markdown catalog ---------------------------------------------------

def parse_catalog(path):
    """Returns [{"name": "DX500 Pro Dishwasher", "code": "DX500", "rows": [(attr, val)]}]"""
    products, cur = [], None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("## "):
                name = line[3:].strip()
                cur = {"name": name, "code": name.split()[0], "rows": []}
                products.append(cur)
            elif cur and line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) == 2 and cells[0] != "Attribute" and not set(cells[0]) <= set("-"):
                    cur["rows"].append((cells[0], cells[1]))
    return products


# --- render the page image --------------------------------------------------------

def load_font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_png(products, out_path):
    f_title, f_head, f_cell = load_font(30, True), load_font(24, True), load_font(21)
    f_note = load_font(18)
    width, pad, col1, col2, row_h = 900, 40, 380, 440, 38
    height = pad + 60
    for p in products:
        height += 50 + row_h * (len(p["rows"]) + 1) + 30
    height += 60
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    y = pad
    d.text((pad, y), "Meridian Appliances, Product Catalog", font=f_title, fill="black")
    y += 60
    for p in products:
        d.text((pad, y), p["name"], font=f_head, fill=(20, 60, 120))
        y += 50
        # header row
        d.rectangle([pad, y, pad + col1 + col2, y + row_h], fill=(225, 232, 242), outline="black")
        d.text((pad + 10, y + 7), "Attribute", font=f_cell, fill="black")
        d.text((pad + col1 + 10, y + 7), "Value", font=f_cell, fill="black")
        y += row_h
        for attr, val in p["rows"]:
            d.rectangle([pad, y, pad + col1, y + row_h], outline="black")
            d.rectangle([pad + col1, y, pad + col1 + col2, y + row_h], outline="black")
            d.text((pad + 10, y + 7), attr, font=f_cell, fill="black")
            d.text((pad + col1 + 10, y + 7), val, font=f_cell, fill="black")
            y += row_h
        y += 30
    d.text((pad, y), "Note: acoustic noise ratings are not published in this catalog.",
           font=f_note, fill=(80, 80, 80))
    img.save(out_path)


# --- control arm, plain code --------------------------------------------------------

def control_text(p):
    lines = [f"{p['name']}."]
    for attr, val in p["rows"]:
        lines.append(f"The {p['name']} {attr.lower()} is {val}.")
    return "\n".join(lines)


# --- vision arm, Gemini reads the image -------------------------------------------

def _post(url, body, tok, retries=5):
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": PROJECT,
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except OSError:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


VISION_PROMPT = (
    "This image is a product catalog page with one specification table per product. "
    "Read every table. For each product write a short text document: first the product "
    "name as a sentence, then one sentence per table row, for example 'The DX500 Pro "
    "Dishwasher capacity is 14 place settings.' Copy every value exactly as shown, "
    "including units. Do not add anything that is not in the image. Return JSON only: "
    '{"products":[{"code":"DX500","text":"..."}]} where code is the first word of the '
    "product name."
)


def vision_docs(png_path, tok):
    with open(png_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    body = {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/png", "data": b64}},
            {"text": VISION_PROMPT},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json"},
    }
    resp = _post(GEMINI_URL, body, tok)
    parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw = "".join(p.get("text", "") for p in parts).strip()
    return {p["code"]: p["text"] for p in json.loads(raw).get("products", [])}


def numbers(text):
    return re.findall(r"\d+(?:\.\d+)?", text)


def main():
    os.makedirs(CONTROL_DIR, exist_ok=True)
    os.makedirs(VISION_DIR, exist_ok=True)
    products = parse_catalog(CATALOG)
    print(f"parsed {len(products)} products from {CATALOG}")

    render_png(products, PNG)
    print(f"rendered {PNG}")

    for p in products:
        with open(os.path.join(CONTROL_DIR, f"{p['code']}.txt"), "w", encoding="utf-8") as fh:
            fh.write(control_text(p) + "\n")
    print(f"wrote {len(products)} control documents to {CONTROL_DIR}")

    tok = token()
    docs = vision_docs(PNG, tok)
    print(f"gemini read the image, returned {len(docs)} product documents")
    ok = True
    for p in products:
        text = docs.get(p["code"], "")
        with open(os.path.join(VISION_DIR, f"{p['code']}.txt"), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        want = numbers(control_text(p))
        have = numbers(text)
        missing = [n for n in want if n not in have]
        status = "OK" if not missing else f"MISSING {missing}"
        if missing:
            ok = False
        print(f"  {p['code']}: vision text {len(text)} chars, numbers check {status}")
    print("vision reading matches the control on every number" if ok
          else "vision reading differs from the control, inspect the vision folder")


if __name__ == "__main__":
    main()
