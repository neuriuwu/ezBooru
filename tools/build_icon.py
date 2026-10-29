"""Convert the supplied square artwork into a multi-resolution Windows icon."""

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "assets" / "ezBooru.png"
DESTINATION = PROJECT_ROOT / "assets" / "ezBooru.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    with Image.open(SOURCE) as source:
        image = source.convert("RGBA")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        square = image.crop((left, top, left + side, top + side))
        square.save(DESTINATION, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    print(f"Created Windows icon: {DESTINATION}")


if __name__ == "__main__":
    main()
