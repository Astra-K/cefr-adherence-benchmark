"""Render the DEV submission cover image deterministically with Pillow."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import random

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "cefr-adherence-cover.png"
WIDTH, HEIGHT = 1200, 630
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(path: str, size: int):
    return ImageFont.truetype(path, size)


def rounded_text(draw, xy, text, text_font, fill, box_fill, padding=(22, 10), radius=18):
    x, y = xy
    box = draw.textbbox((x, y), text, font=text_font)
    w, h = box[2] - box[0], box[3] - box[1]
    px, py = padding
    draw.rounded_rectangle((x - px, y - py, x + w + px, y + h + py), radius=radius, fill=box_fill)
    draw.text((x, y), text, font=text_font, fill=fill)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    top = (6, 14, 30)
    bottom = (17, 31, 58)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        row = tuple(round(a * (1 - t) + b * t) for a, b in zip(top, bottom))
        draw.line((0, y, WIDTH, y), fill=row)

    rng = random.Random(42)
    for _ in range(85):
        x = rng.randrange(WIDTH)
        y = rng.randrange(0, HEIGHT - 55)
        r = rng.choice([1, 1, 1, 2])
        alpha = rng.randrange(70, 180)
        base = (150, 190, 225)
        color = tuple(round(c * alpha / 255) for c in base)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    # Lunar arc behind the level cards.
    draw.ellipse((786, 70, 1190, 474), fill=(20, 52, 86), outline=(84, 171, 190), width=4)
    draw.ellipse((725, 22, 1095, 392), fill=(8, 18, 37))

    badge_font = font(BOLD, 21)
    rounded_text(draw, (74, 53), "KAGGLE BENCHMARK", badge_font, (6, 18, 31), (100, 214, 196))

    title_font = font(BOLD, 68)
    draw.multiline_text((70, 132), "Can an AI tutor\nstay at the\nlearner's level?", font=title_font,
                        fill=(242, 246, 250), spacing=5)

    sub_font = font(REGULAR, 27)
    draw.text((74, 405), "CEFR adherence for real learner questions", font=sub_font, fill=(172, 194, 215))

    # Level cards: simple visual ladder from A1 to C1.
    card_x = 855
    card_font = font(BOLD, 42)
    label_font = font(REGULAR, 18)
    cards = [
        ("A1", "basic", (104, 218, 195)),
        ("B1", "independent", (87, 164, 255)),
        ("C1", "advanced", (190, 126, 255)),
    ]
    for idx, (level, label, color) in enumerate(cards):
        y = 150 + idx * 115
        draw.rounded_rectangle((card_x, y, card_x + 250, y + 86), radius=20,
                               fill=(15, 30, 53), outline=color, width=3)
        draw.text((card_x + 22, y + 15), level, font=card_font, fill=color)
        draw.text((card_x + 102, y + 34), label.upper(), font=label_font, fill=(220, 230, 239))

    footer_font = font(BOLD, 21)
    footer = "30 QUESTIONS   •   3 LEVELS   •   2 PROMPT CONDITIONS"
    draw.line((70, 538, 1130, 538), fill=(73, 104, 137), width=2)
    draw.text((74, 564), footer, font=footer_font, fill=(156, 185, 211))

    image.save(OUT, optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
