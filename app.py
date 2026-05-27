import csv
import os
import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from flask import Flask, request, abort, send_from_directory
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    FlexSendMessage,
    ImageSendMessage,
    MessageAction,
    MessageEvent,
    QuickReply,
    QuickReplyButton,
    TextMessage,
    TextSendMessage,
)

load_dotenv() # 載入 .env 檔案

app = Flask(__name__)

# 初始化 LINE 與 Dify 金鑰
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"
DIFY_API_KEY = os.getenv('DIFY_API_KEY')

WAITING_NAME = "WAITING_NAME"
WAITING_BIRTHDATE = "WAITING_BIRTHDATE"
WAITING_VACCINE_STATUS = "WAITING_VACCINE_STATUS"
WAITING_VACCINATION_DATE = "WAITING_VACCINATION_DATE"
DEFAULT_VACCINE_STATUS = "尚未行動"
VACCINE_STATUS_OPTIONS = ["已接種", "已預約", "規劃中"]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
FIVE_IN_ONE_HEALTH_CARD_TRIGGER = "發送 五合一 衛教資訊"

# MVP 暫存資料：服務重啟後會清空，之後再接回資料庫保存。
registration_sessions = {}
registered_babies = {}

VACCINE_CSV_PATH = Path(__file__).with_name("vaccines.csv")
HEALTH_CARD_DIR = Path(__file__).with_name("health_cards")

RICH_MENU_PLACEHOLDER_REPLIES = {
    "數位接種紀錄": "數位接種紀錄功能準備中，之後會在這裡查看寶寶的完整接種紀錄。",
    "手冊掃描紀錄": "手冊掃描紀錄功能準備中，之後會在這裡查看上傳過的手冊影像與辨識結果。",
    "合作診所查詢": "合作診所查詢功能準備中，之後會在這裡查詢附近可施打疫苗的合作診所。",
    "托嬰中心連動": "托嬰中心連動功能準備中，之後會在這裡同步托嬰中心提醒與接種狀態。",
}

BABY_MANAGEMENT_OPTIONS = [
    "新增寶寶資料",
    "查看寶寶資料",
    "切換目前寶寶",
    "修改已建立的寶寶",
    "刪除寶寶資料",
]


def load_vaccine_rules():
    rules = []

    with VACCINE_CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            min_age = row.get("Min_Age", "").strip()
            if not min_age:
                continue

            rules.append({
                "code": row.get("Sys_Code", "").strip(),
                "name": row.get("UI_Name", "").strip() or row.get("Standard_Name", "").strip(),
                "dose": row.get("Dose", "").strip(),
                "min_age_days": int(min_age),
                "type": row.get("Type", "").strip(),
                "notes": row.get("Notes", "").strip(),
            })

    return sorted(rules, key=lambda rule: rule["min_age_days"])


VACCINE_RULES = load_vaccine_rules()


def parse_birthdate(raw_text):
    normalized = raw_text.strip().replace("/", "-")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def calculate_vaccine_schedules(birthdate):
    schedules = []

    for rule in VACCINE_RULES:
        expected_date = birthdate + timedelta(days=rule["min_age_days"])
        schedules.append({
            "code": rule["code"],
            "vaccine_name": rule["name"],
            "dose": f"第 {rule['dose']} 劑",
            "expected_date": expected_date,
            "type": rule["type"],
            "notes": rule["notes"],
            "status": DEFAULT_VACCINE_STATUS,
            "vaccinated_date": None,
        })

    return schedules


def is_vaccinated(vaccine):
    return vaccine.get("status") == "已接種"


def get_display_schedules(schedules):
    today = date.today()
    overdue = [
        vaccine for vaccine in schedules
        if vaccine["expected_date"] < today and not is_vaccinated(vaccine)
    ][-3:]
    upcoming = [
        vaccine for vaccine in schedules
        if vaccine["expected_date"] >= today
    ][:7]

    return overdue + upcoming


def get_vaccine_frame_style(vaccine):
    today = date.today()
    three_months_later = today + timedelta(days=90)

    if vaccine["expected_date"] < today and not is_vaccinated(vaccine):
        return "#FF5551"

    if today <= vaccine["expected_date"] <= three_months_later:
        return "#F2C94C"

    return "#D8EEEE"


def get_vaccine_status_text(vaccine):
    if vaccine.get("status") == "已接種" and vaccine.get("vaccinated_date"):
        return f"已於 {vaccine['vaccinated_date']} 接種"

    return f"狀態: {vaccine.get('status', DEFAULT_VACCINE_STATUS)}"


def build_vaccine_carousel(schedules):
    bubbles = []

    display_schedules = get_display_schedules(schedules)

    for vac in display_schedules:
        vaccine_index = schedules.index(vac)
        frame_color = get_vaccine_frame_style(vac)
        bubble = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "borderColor": frame_color,
                        "borderWidth": "light",
                        "cornerRadius": "md",
                        "paddingAll": "md",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {"type": "text", "text": vac["type"] or "疫苗", "color": "#ffffff", "align": "center", "size": "sm", "weight": "bold"}
                                ],
                                "backgroundColor": "#27ACB2",
                                "cornerRadius": "sm",
                                "paddingAll": "sm"
                            },
                            {"type": "text", "text": vac["vaccine_name"], "weight": "bold", "size": "xl", "wrap": True, "margin": "md"},
                            {"type": "text", "text": vac["dose"], "size": "md", "color": "#5f6f72", "weight": "bold", "margin": "sm"},
                            {"type": "text", "text": f"預計: {vac['expected_date'].isoformat()}", "size": "sm", "color": "#ff5551", "margin": "md", "weight": "bold"},
                            {"type": "text", "text": get_vaccine_status_text(vac), "size": "md", "color": "#27ACB2", "margin": "sm", "weight": "bold", "wrap": True},
                            {
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "margin": "md",
                                "action": {
                                    "type": "message",
                                    "label": "變更疫苗狀態",
                                    "text": f"變更疫苗狀態:{vaccine_index}"
                                }
                            }
                        ]
                    }
                ],
            }
        }
        bubbles.append(bubble)

    return {
        "type": "carousel",
        "contents": bubbles
    }


def get_health_card_filename(vaccine):
    code = vaccine.get("code", "").strip()
    if not code:
        return None

    return f"{code}.png"


def get_health_card_path(vaccine):
    filename = get_health_card_filename(vaccine)
    if not filename:
        return None

    return HEALTH_CARD_DIR / filename


def get_health_card_url(vaccine):
    filename = get_health_card_filename(vaccine)
    if not filename or not get_health_card_path(vaccine).exists():
        return None

    if PUBLIC_BASE_URL:
        base_url = PUBLIC_BASE_URL.rstrip("/")
    else:
        forwarded_host = request.headers.get("X-Forwarded-Host")
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "https")
        host = forwarded_host or request.host
        base_url = f"{forwarded_proto}://{host}".rstrip("/")

    return f"{base_url}/health-cards/{filename}"


def build_health_card_message(vaccine):
    image_url = get_health_card_url(vaccine)
    if not image_url:
        expected_filename = get_health_card_filename(vaccine)
        print(f"Health card not found: {expected_filename}", flush=True)
        return None

    print(f"Sending health card image: {image_url}", flush=True)
    return ImageSendMessage(
        original_content_url=image_url,
        preview_image_url=image_url
    )


def get_user_baby_profile(user_id):
    return registered_babies.setdefault(user_id, {
        "babies": [],
        "active_index": 0,
    })


def get_active_baby(user_id):
    profile = get_user_baby_profile(user_id)
    babies = profile["babies"]
    if not babies:
        return None

    profile["active_index"] = min(profile["active_index"], len(babies) - 1)
    return babies[profile["active_index"]]


def start_baby_registration(user_id, mode="add"):
    registration_sessions[user_id] = {
        "state": WAITING_NAME,
        "mode": mode,
        "data": {}
    }


def build_baby_management_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label=option, text=option))
        for option in BABY_MANAGEMENT_OPTIONS
    ])


def build_vaccine_status_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label=status, text=f"疫苗狀態:{status}"))
        for status in VACCINE_STATUS_OPTIONS
    ])


def build_date_choice_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="今天", text="今天")),
        QuickReplyButton(action=MessageAction(label="其他", text="其他")),
    ])


def build_view_schedule_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="查看近期疫苗資訊", text="查看近期疫苗資訊")),
        QuickReplyButton(action=MessageAction(label="不用", text="不用")),
    ])


def build_no_baby_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="新增寶寶", text="新增寶寶資料")),
        QuickReplyButton(action=MessageAction(label="沒關係", text="沒關係")),
    ])


def build_baby_switch_quick_reply(user_id):
    profile = get_user_baby_profile(user_id)
    items = []

    for index, baby in enumerate(profile["babies"]):
        label = f"{index + 1}. {baby['name']}"
        if len(label) > 20:
            label = f"{index + 1}. {baby['name'][:16]}"

        items.append(
            QuickReplyButton(action=MessageAction(label=label, text=f"切換寶寶:{index}"))
        )

    return QuickReply(items=items)


def format_baby_list(user_id):
    profile = get_user_baby_profile(user_id)
    lines = ["目前建立的寶寶："]

    for index, baby in enumerate(profile["babies"]):
        marker = "目前選取" if index == profile["active_index"] else "可切換"
        lines.append(f"{index + 1}. {baby['name']}（{baby['birthdate'].isoformat()}，{marker}）")

    return "\n".join(lines)


def format_baby_profile(baby):
    lines = [
        f"寶寶姓名：{baby['name']}",
        f"生日：{baby['birthdate'].isoformat()}",
    ]

    if baby["schedules"]:
        next_vaccine = baby["schedules"][0]
        lines.extend([
            "",
            "下一筆近期疫苗：",
            f"{next_vaccine['expected_date'].isoformat()}：{next_vaccine['vaccine_name']}（{next_vaccine['dose']}）",
        ])
    else:
        lines.append("\n近期沒有需要施打的疫苗。")

    return "\n".join(lines)


def get_vaccine_by_index(user_id, index):
    baby = get_active_baby(user_id)
    if not baby or not isinstance(index, int) or index < 0 or index >= len(baby["schedules"]):
        return None

    return baby["schedules"][index]

# 這是提供給 LINE Webhook 呼叫的入口
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@app.route("/health-cards/<path:filename>", methods=["GET"])
def health_card_file(filename):
    return send_from_directory(HEALTH_CARD_DIR, filename)

# 處理文字訊息的邏輯分流 (Router)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    user_id = event.source.user_id
    print(f"LINE user_id: {user_id}", flush=True)

    if user_msg == "取消":
        registration_sessions.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已取消目前的註冊流程。"))
        return

    if user_msg == "沒關係":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="沒問題，需要時再點選「寶寶切換與管理」。"))
        return

    if user_msg == "不用":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="好的，需要時再點選「近期疫苗時程」。"))
        return

    if user_msg == "查看近期疫苗資訊":
        baby = get_active_baby(user_id)
        if not baby:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前還沒有寶寶資料。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        if not get_display_schedules(baby["schedules"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"太棒了！{baby['name']} 近期沒有需要施打的疫苗喔！"))
            return

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text=f"{baby['name']} 的近期疫苗時程提醒",
                contents=build_vaccine_carousel(baby["schedules"])
            )
        )
        return

    if user_msg == "新增寶寶":
        start_baby_registration(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="為了精準追蹤疫苗時程，請先輸入寶寶的名字！"))
        return

    if user_msg in ["寶貝切換與管理", "寶寶切換與管理"]:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="請選擇要管理的項目：",
                quick_reply=build_baby_management_quick_reply()
            )
        )
        return

    if user_msg == "新增寶寶資料":
        start_baby_registration(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入要新增的寶寶姓名。"))
        return

    if user_msg == "查看寶寶資料":
        baby = get_active_baby(user_id)
        if not baby:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前還沒有寶寶資料。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"{format_baby_profile(baby)}\n\n{format_baby_list(user_id)}",
                quick_reply=build_baby_switch_quick_reply(user_id)
            )
        )
        return

    if user_msg == "切換目前寶寶":
        profile = get_user_baby_profile(user_id)
        if not profile["babies"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前還沒有寶寶資料。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        if len(profile["babies"]) == 1:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"目前只有一位寶寶：{profile['babies'][0]['name']}。")
            )
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="請選擇要切換成哪一位寶寶：",
                quick_reply=build_baby_switch_quick_reply(user_id)
            )
        )
        return

    if user_msg.startswith("切換寶寶:"):
        profile = get_user_baby_profile(user_id)
        index_text = user_msg.split(":", 1)[1]
        if not index_text.isdigit():
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="切換格式不正確，請重新選擇。"))
            return

        index = int(index_text)
        if index < 0 or index >= len(profile["babies"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到這位寶寶，請重新選擇。"))
            return

        profile["active_index"] = index
        baby = profile["babies"][index]
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已切換目前寶寶為：{baby['name']}。")
        )
        return

    if user_msg == "修改已建立的寶寶":
        baby = get_active_baby(user_id)
        if not baby:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前還沒有可修改的寶寶資料。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        start_baby_registration(user_id, mode="edit")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"目前要修改的是：{baby['name']}。\n請重新輸入寶寶姓名。")
        )
        return

    if user_msg == "刪除寶寶資料":
        registration_sessions.pop(user_id, None)
        profile = get_user_baby_profile(user_id)
        if not profile["babies"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前沒有寶寶資料可以刪除。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        active_index = min(profile["active_index"], len(profile["babies"]) - 1)
        deleted_baby = profile["babies"].pop(active_index)
        profile["active_index"] = max(0, min(active_index, len(profile["babies"]) - 1))

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"已刪除 {deleted_baby['name']} 的寶寶資料。")
        )
        return

    if user_msg.startswith("變更疫苗狀態:"):
        index_text = user_msg.split(":", 1)[1]
        if not index_text.isdigit():
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="疫苗狀態選擇格式不正確，請重新點選卡片按鈕。"))
            return

        vaccine_index = int(index_text)
        vaccine = get_vaccine_by_index(user_id, vaccine_index)
        if not vaccine:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到這筆疫苗資料，請重新查看近期疫苗時程。"))
            return

        registration_sessions[user_id] = {
            "state": WAITING_VACCINE_STATUS,
            "data": {"vaccine_index": vaccine_index}
        }
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"請選擇「{vaccine['vaccine_name']}（{vaccine['dose']}）」的狀態：",
                quick_reply=build_vaccine_status_quick_reply()
            )
        )
        return

    if user_msg.startswith("疫苗狀態:"):
        selected_status = user_msg.split(":", 1)[1]
        session = registration_sessions.get(user_id)
        if (
            selected_status not in VACCINE_STATUS_OPTIONS
            or not session
            or session.get("state") != WAITING_VACCINE_STATUS
        ):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請先從疫苗卡片點選「變更疫苗狀態」。"))
            return

        vaccine_index = session.get("data", {}).get("vaccine_index")
        vaccine = get_vaccine_by_index(user_id, vaccine_index)
        if not vaccine:
            registration_sessions.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到這筆疫苗資料，請重新查看近期疫苗時程。"))
            return

        if selected_status == "已接種":
            registration_sessions[user_id] = {
                "state": WAITING_VACCINATION_DATE,
                "data": {"vaccine_index": vaccine_index}
            }
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="請選擇實際接種日期：",
                    quick_reply=build_date_choice_quick_reply()
                )
            )
            return

        vaccine["status"] = selected_status
        vaccine["vaccinated_date"] = None
        registration_sessions.pop(user_id, None)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"已將 {vaccine['vaccine_name']} 更新為「{selected_status}」。是否需要查看近期疫苗資訊？",
                quick_reply=build_view_schedule_quick_reply()
            )
        )
        return

    session = registration_sessions.get(user_id)
    if session:
        state = session["state"]

        if state == WAITING_VACCINE_STATUS:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="請選擇疫苗狀態：",
                    quick_reply=build_vaccine_status_quick_reply()
                )
            )
            return

        if state == WAITING_VACCINATION_DATE:
            if user_msg == "其他":
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請手動輸入實際接種日期，格式為 YYYY-MM-DD，例如 2026-01-01。")
                )
                return

            vaccinated_date = date.today() if user_msg == "今天" else parse_birthdate(user_msg)
            if not vaccinated_date:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text="日期格式不正確，請用 YYYY-MM-DD，例如 2026-01-01。",
                        quick_reply=build_date_choice_quick_reply()
                    )
                )
                return

            if vaccinated_date > date.today():
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="接種日期不能是未來日期，請重新輸入。")
                )
                return

            vaccine_index = session.get("data", {}).get("vaccine_index")
            vaccine = get_vaccine_by_index(user_id, vaccine_index)
            if not vaccine:
                registration_sessions.pop(user_id, None)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到這筆疫苗資料，請重新查看近期疫苗時程。"))
                return

            vaccine["status"] = "已接種"
            vaccine["vaccinated_date"] = vaccinated_date.isoformat()
            registration_sessions.pop(user_id, None)
            baby = get_active_baby(user_id)
            reply_messages = [
                TextSendMessage(text=f"已更新：{vaccine['vaccine_name']} 已於 {vaccinated_date.isoformat()} 接種。")
            ]
            health_card_message = build_health_card_message(vaccine)
            if health_card_message:
                if vaccine.get("code") == "5in1-3":
                    reply_messages.append(TextSendMessage(text=FIVE_IN_ONE_HEALTH_CARD_TRIGGER))
                reply_messages.append(health_card_message)

            reply_messages.append(
                TextSendMessage(
                    text="是否需要查看近期疫苗資訊？",
                    quick_reply=build_view_schedule_quick_reply()
                )
            )
            line_bot_api.reply_message(
                event.reply_token,
                reply_messages
            )
            return

        if state == WAITING_NAME:
            session["data"]["name"] = user_msg
            session["state"] = WAITING_BIRTHDATE
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="請選擇寶寶生日：",
                    quick_reply=build_date_choice_quick_reply()
                )
            )
            return

        if state == WAITING_BIRTHDATE:
            if user_msg == "其他":
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請手動輸入寶寶生日，格式為 YYYY-MM-DD，例如 2026-01-01。")
                )
                return

            birthdate = date.today() if user_msg == "今天" else parse_birthdate(user_msg)
            if not birthdate:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(
                        text="日期格式不正確，請用 YYYY-MM-DD，例如 2026-01-01。",
                        quick_reply=build_date_choice_quick_reply()
                    )
                )
                return

            if birthdate > date.today():
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="生日不能是未來日期，請重新輸入正確生日。")
                )
                return

            baby_name = session["data"]["name"]
            schedules = calculate_vaccine_schedules(birthdate)
            baby_data = {
                "name": baby_name,
                "birthdate": birthdate,
                "schedules": schedules,
            }
            profile = get_user_baby_profile(user_id)

            if session.get("mode") == "edit" and profile["babies"]:
                active_index = min(profile["active_index"], len(profile["babies"]) - 1)
                profile["babies"][active_index] = baby_data
                profile["active_index"] = active_index
                action_text = "已更新寶寶資料"
            else:
                profile["babies"].append(baby_data)
                profile["active_index"] = len(profile["babies"]) - 1
                action_text = "已新增寶寶"

            registration_sessions.pop(user_id, None)

            if not get_display_schedules(schedules):
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{action_text}：{baby_name}\n太棒了！近期沒有需要施打的疫苗喔！")
                )
                return

            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(
                    alt_text=f"{baby_name} 的近期疫苗時程提醒",
                    contents=build_vaccine_carousel(schedules)
                )
            )
            return

# 分流 1：攔截特定指令
    if user_msg == "近期疫苗時程":
        baby = get_active_baby(user_id)

        if not baby:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="目前還沒有寶寶資料。要先新增寶寶嗎？",
                    quick_reply=build_no_baby_quick_reply()
                )
            )
            return

        if not get_display_schedules(baby["schedules"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"太棒了！{baby['name']} 近期沒有需要施打的疫苗喔！"))
            return

        line_bot_api.reply_message(
            event.reply_token, 
            FlexSendMessage(alt_text=f"{baby['name']} 的近期疫苗時程提醒", contents=build_vaccine_carousel(baby["schedules"]))
        )

    elif user_msg in RICH_MENU_PLACEHOLDER_REPLIES:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=RICH_MENU_PLACEHOLDER_REPLIES[user_msg])
        )
    
    # 分流 2：其他日常提問 (轉交給 Dify LLM 處理)
    else:
        # 呼叫 Dify API
        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": {},
            "query": user_msg,
            "response_mode": "blocking", # 等待 AI 生成完畢再回傳
            "user": user_id # 帶入 LINE 的 UID 讓 Dify 記住對話上下文
        }
        
        response = requests.post(DIFY_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            dify_answer = response.json().get('answer', '抱歉，AI 暫時無法回應。')
        else:
            dify_answer = "與 Dify 伺服器連線失敗，請稍後再試。"

        # 將 Dify 的回答傳回給家長
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=dify_answer))

if __name__ == "__main__":
    app.run(port=5001)
