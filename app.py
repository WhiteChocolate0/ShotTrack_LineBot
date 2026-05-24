import os
import requests
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
from supabase import create_client, Client

load_dotenv() # 載入 .env 檔案

# 初始化 Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)

# 初始化 LINE 與 Dify 金鑰
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"
DIFY_API_KEY = os.getenv('DIFY_API_KEY')

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

# 處理文字訊息的邏輯分流 (Router)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id
    print(f"LINE user_id: {user_id}", flush=True)

# 分流 1：攔截特定指令
    if user_msg == "近期疫苗時程":
        # 1. 從 Supabase 撈取該家長的未施打疫苗 (依照日期排序，最多取 10 筆)
        response = supabase.table('vaccine_schedule') \
            .select('*') \
            .eq('line_user_id', user_id) \
            .eq('status', 'pending') \
            .order('expected_date') \
            .limit(10) \
            .execute()
        
        vaccine_data = response.data

        # 2. 判斷如果沒有待打疫苗
        if not vaccine_data:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="太棒了！您的寶貝近期沒有需要施打的疫苗喔！"))
            return

        # 3. 動態組裝 Flex Message 的 Bubbles
        bubbles = []
        for vac in vaccine_data:
            # 判斷顏色：公費為藍綠色，自費為橘黃色
            bg_color = "#27ACB2" if vac.get('vaccine_type') == "公費" else "#F2A635"
            
            bubble = {
                "type": "bubble",
                "size": "micro",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": vac.get('vaccine_type', '一般'), "color": "#ffffff", "align": "center", "size": "sm", "weight": "bold"}
                    ],
                    "backgroundColor": bg_color,
                    "paddingAll": "sm"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": vac.get('vaccine_name', '未知疫苗'), "weight": "bold", "size": "md", "wrap": True},
                        {"type": "text", "text": vac.get('dose', '第 1 劑'), "size": "xs", "color": "#8c8c8c"},
                        {"type": "text", "text": f"預計: {vac.get('expected_date', '')}", "size": "xs", "color": "#ff5551", "margin": "md", "weight": "bold"}
                    ]
                }
            }
            bubbles.append(bubble)

        # 4. 組合 Carousel 模板並傳送
        carousel_template = {
            "type": "carousel",
            "contents": bubbles
        }
        
        line_bot_api.reply_message(
            event.reply_token, 
            FlexSendMessage(alt_text="您的近期疫苗時程提醒", contents=carousel_template)
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
