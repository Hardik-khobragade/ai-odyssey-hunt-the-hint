"""
generate_images.py — Creates placeholder Round 2 images with hidden words.

Run this once to generate the starter set:
    python generate_images.py

Then REPLACE the generated images in static/images/ with your actual
designed images that visually hide the word. The word in each image
must match the answer in data/questions.json → round2[i].answer
"""

import os
import json

# ─── Requires Pillow ──────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Pillow not installed. Run: pip install Pillow")
    print("Generating minimal placeholder HTML images instead...")

OUTPUT_DIR = os.path.join("static", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

QUESTIONS_FILE = os.path.join("data", "questions.json")

# Ultron color palette
BG_COLOR = (5, 8, 22)
ACCENT1 = (230, 57, 70)
ACCENT2 = (255, 214, 10)
ACCENT3 = (0, 180, 216)
TEXT_COLOR = (200, 214, 229)

def make_image_pillow(idx, answer, hint, filename):
    """Create a styled image with the hidden word camouflaged in the design."""
    W, H = 900, 500
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Background grid
    for x in range(0, W, 40):
        draw.line([(x, 0), (x, H)], fill=(26, 58, 110, 40), width=1)
    for y in range(0, H, 40):
        draw.line([(0, y), (W, y)], fill=(26, 58, 110, 40), width=1)

    # Decorative circles
    import random
    rng = random.Random(idx * 42)
    for _ in range(8):
        cx = rng.randint(50, W-50)
        cy = rng.randint(50, H-50)
        r = rng.randint(20, 100)
        color = rng.choice([ACCENT1, ACCENT2, ACCENT3])
        alpha_color = tuple(list(color) + [30])
        # Outline only
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=color, width=1)

    # Question number top-left
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_hint = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_hidden = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except:
        font_big = font_med = font_hint = font_hidden = ImageFont.load_default()

    draw.text((30, 20), f"SIGNAL-{idx+1:02d}", font=font_big, fill=ACCENT2)
    draw.text((30, 80), hint or "Find the hidden word...", font=font_hint, fill=(*TEXT_COLOR, 150))

    # ─── Hide the word in the image ───────────────────────────────────────────
    # Technique: word is printed in a color very close to background,
    # slightly lighter — visible on close inspection but blends at a glance.
    # YOU SHOULD REPLACE THIS with a proper designed image where the word
    # is hidden in textures, circuit patterns, binary code, etc.

    hidden_x = rng.randint(200, W - 300)
    hidden_y = rng.randint(180, H - 100)

    # Draw word at low opacity (camouflaged)
    hidden_color = (30, 45, 70)  # Very close to background — "invisible"
    draw.text((hidden_x, hidden_y), answer.upper(), font=font_hidden, fill=hidden_color)

    # Noise lines around the word to make it harder to spot
    for _ in range(50):
        x1 = rng.randint(0, W); y1 = rng.randint(0, H)
        x2 = rng.randint(0, W); y2 = rng.randint(0, H)
        draw.line([(x1,y1),(x2,y2)], fill=(15, 25, 45), width=1)

    # Circuit-like connecting lines
    for _ in range(6):
        sx = rng.randint(0, W); sy = rng.randint(0, H)
        ex = rng.randint(0, W); ey = rng.randint(0, H)
        color = rng.choice([ACCENT1, ACCENT3])
        draw.line([(sx,sy),(ex,sy)], fill=(*color[:3], 60), width=1)  # horizontal
        draw.line([(ex,sy),(ex,ey)], fill=(*color[:3], 60), width=1)  # vertical

    # Border
    draw.rectangle([0, 0, W-1, H-1], outline=ACCENT1, width=2)

    # Watermark
    draw.text((W-160, H-30), "AI ODYSSEY", font=font_hint, fill=(40,40,60))

    out = os.path.join(OUTPUT_DIR, filename)
    img.save(out, "PNG", optimize=True)
    print(f"  ✓ {filename} (answer: '{answer}' hidden at {hidden_x},{hidden_y})")
    return out


def make_placeholder_svg(idx, answer, hint, filename):
    """Fallback: create SVG placeholder when Pillow unavailable."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="500">
  <rect width="900" height="500" fill="#050816"/>
  <text x="30" y="60" font-family="monospace" font-size="36" fill="#ffd60a">SIGNAL-{idx+1:02d}</text>
  <text x="30" y="100" font-family="monospace" font-size="18" fill="#c8d6e5">{hint}</text>
  <text x="450" y="250" font-family="monospace" font-size="14" fill="#1a2a4a" text-anchor="middle">{answer.upper()}</text>
  <text x="450" y="470" font-family="monospace" font-size="12" fill="#1a2a3a" text-anchor="middle">AI ODYSSEY — HUNT THE HINT</text>
  <rect x="1" y="1" width="898" height="498" fill="none" stroke="#e63946" stroke-width="2"/>
</svg>"""
    out = os.path.join(OUTPUT_DIR, filename.replace('.png', '.svg'))
    with open(out, 'w') as f:
        f.write(svg)
    print(f"  ✓ {out} (SVG placeholder)")


def main():
    # Load questions
    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)

    r2 = questions.get("round2", [])
    print(f"\n🎨 Generating {len(r2)} Round 2 images...\n")

    for i, q in enumerate(r2):
        answer = q.get("answer", f"word{i+1}")
        hint = q.get("display_hint") or q.get("hint", "Find the hidden word")
        filename = f"r2_q{i+1}.png"

        if HAS_PIL:
            make_image_pillow(i, answer, hint, filename)
        else:
            make_placeholder_svg(i, answer, hint, filename)

    print(f"\n✅ Done! Images saved to {OUTPUT_DIR}/")
    print("\n⚠️  IMPORTANT:")
    print("   These are PLACEHOLDER images.")
    print("   For a real event, replace them with properly designed images")
    print("   where the hidden word is visually embedded in the design.")
    print("   Use tools like Photoshop, Canva, or Figma.")
    print("\n   Image naming convention: r2_q1.png, r2_q2.png, ..., r2_q10.png")


if __name__ == "__main__":
    main()