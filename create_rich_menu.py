import os
from pathlib import Path

from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import MessageAction, RichMenu, RichMenuArea, RichMenuBounds, RichMenuSize


load_dotenv()

RICH_MENU_IMAGE_PATH = Path(__file__).with_name("rich_menu_upload.jpg")
RICH_MENU_IMAGE_CONTENT_TYPE = "image/jpeg"

MENU_ITEMS = [
    ("近期疫苗時程", "近期疫苗時程"),
    ("數位接種紀錄", "數位接種紀錄"),
    ("手冊掃描紀錄", "手冊掃描紀錄"),
    ("合作診所查詢", "合作診所查詢"),
    ("托嬰中心連動", "托嬰中心連動"),
    ("寶寶切換與管理", "寶寶切換與管理"),
]


def build_areas():
    width = 2500
    height = 1686
    cell_width = width // 3
    cell_height = height // 2
    areas = []

    for index, (_, message_text) in enumerate(MENU_ITEMS):
        col = index % 3
        row = index // 3
        x = col * cell_width
        y = row * cell_height
        area_width = cell_width if col < 2 else width - x
        area_height = cell_height if row < 1 else height - y

        areas.append(
            RichMenuArea(
                bounds=RichMenuBounds(x=x, y=y, width=area_width, height=area_height),
                action=MessageAction(label=message_text, text=message_text),
            )
        )

    return areas


def main():
    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not channel_access_token:
        raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN in .env")

    if not RICH_MENU_IMAGE_PATH.exists():
        raise RuntimeError(f"Missing rich menu image: {RICH_MENU_IMAGE_PATH}")

    line_bot_api = LineBotApi(channel_access_token)
    rich_menu = RichMenu(
        size=RichMenuSize(width=2500, height=1686),
        selected=True,
        name="ShotTrack MVP 六宮格",
        chat_bar_text="功能選單",
        areas=build_areas(),
    )

    rich_menu_id = line_bot_api.create_rich_menu(rich_menu=rich_menu)
    with RICH_MENU_IMAGE_PATH.open("rb") as image_file:
        line_bot_api.set_rich_menu_image(rich_menu_id, RICH_MENU_IMAGE_CONTENT_TYPE, image_file)

    line_bot_api.set_default_rich_menu(rich_menu_id)
    print(f"Created and set default rich menu: {rich_menu_id}")


if __name__ == "__main__":
    main()
