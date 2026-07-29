from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parent
ICO_PATH = OUT_DIR / "markdown-viewer.ico"
PNG_PATH = OUT_DIR / "markdown-viewer-256.png"


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded_rectangle(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_icon(size):
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def xy(values):
        return tuple(round(value * scale) for value in values)

    rounded_rectangle(draw, xy((18, 18, 238, 238)), round(46 * scale), (11, 93, 86, 255))
    rounded_rectangle(draw, xy((34, 34, 222, 222)), round(34 * scale), (18, 121, 112, 255))

    page = xy((65, 44, 195, 212))
    rounded_rectangle(draw, page, round(14 * scale), (248, 253, 251, 255))
    draw.polygon([xy((158, 44)), xy((195, 82)), xy((158, 82))], fill=(211, 234, 229, 255))
    draw.line([xy((158, 44)), xy((158, 82)), xy((195, 82))], fill=(143, 188, 178, 255), width=max(1, round(3 * scale)))

    draw.rectangle(xy((84, 104, 176, 114)), fill=(15, 118, 110, 255))
    draw.rectangle(xy((84, 128, 164, 138)), fill=(15, 118, 110, 205))
    draw.rectangle(xy((84, 152, 144, 162)), fill=(15, 118, 110, 170))

    md_font = font(round(42 * scale), bold=True)
    bbox = draw.textbbox((0, 0), "MD", font=md_font)
    text_w = bbox[2] - bbox[0]
    draw.text(xy(((256 - text_w / scale) / 2, 166)), "MD", font=md_font, fill=(11, 93, 86, 255))

    arrow = [xy((119, 81)), xy((137, 81)), xy((137, 58)), xy((163, 91)), xy((137, 124)), xy((137, 101)), xy((119, 101))]
    draw.polygon(arrow, fill=(255, 184, 77, 255))
    return image


def main():
    images = [draw_icon(size) for size in (16, 24, 32, 48, 64, 128, 256)]
    images[-1].save(PNG_PATH)
    images[-1].save(ICO_PATH, sizes=[(image.width, image.height) for image in images], append_images=images[:-1])
    print(f"Wrote {ICO_PATH}")
    print(f"Wrote {PNG_PATH}")


if __name__ == "__main__":
    main()
