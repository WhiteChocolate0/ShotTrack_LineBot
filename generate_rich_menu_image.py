from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 2500
HEIGHT = 1686
OUTPUT_PATH = Path(__file__).with_name("rich_menu.png")
FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"

MENU_ITEMS = [
    ("近期疫苗時程", "Schedule"),
    ("數位接種紀錄", "Records"),
    ("手冊掃描紀錄", "Scan"),
    ("合作診所查詢", "Clinics"),
    ("托嬰中心連動", "Daycare"),
    ("寶寶切換與管理", "Manage"),
]


def centered_text(draw, box, text, font, fill):
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    x = box[0] + (box[2] - box[0] - text_width) / 2
    y = box[1] + (box[3] - box[1] - text_height) / 2
    draw.text((x, y), text, font=font, fill=fill)


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#F7FCFC")
    draw = ImageDraw.Draw(image)

    primary = "#114D50"
    secondary = "#5A7577"
    border = "#27ACB2"
    divider = "#BFE7E8"

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=border, width=16)
    draw.line((WIDTH // 3, 0, WIDTH // 3, HEIGHT), fill=divider, width=8)
    draw.line((WIDTH * 2 // 3, 0, WIDTH * 2 // 3, HEIGHT), fill=divider, width=8)
    draw.line((0, HEIGHT // 2, WIDTH, HEIGHT // 2), fill=divider, width=8)

    title_font = ImageFont.truetype(FONT_PATH, 86)
    subtitle_font = ImageFont.truetype(FONT_PATH, 42)

    cell_width = WIDTH // 3
    cell_height = HEIGHT // 2

    for index, (title, subtitle) in enumerate(MENU_ITEMS):
        col = index % 3
        row = index // 3
        left = col * cell_width
        top = row * cell_height
        right = WIDTH if col == 2 else left + cell_width
        bottom = HEIGHT if row == 1 else top + cell_height

        title_box = (left, top + 250, right, top + 420)
        subtitle_box = (left, top + 415, right, top + 510)
        centered_text(draw, title_box, title, title_font, primary)
        centered_text(draw, subtitle_box, subtitle, subtitle_font, secondary)

    image.save(OUTPUT_PATH)
    print(f"Generated {OUTPUT_PATH} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
