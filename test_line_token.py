import os
import requests

LINE_CHANNEL_ID     = os.environ["LINE_CHANNEL_ID"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

def main():
    url = "https://api.line.me/oauth2/v3/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": LINE_CHANNEL_ID,
        "client_secret": LINE_CHANNEL_SECRET,
    }
    resp = requests.post(url, data=data)
    print(f"ステータスコード: {resp.status_code}")
    print(f"レスポンス: {resp.text}")
    resp.raise_for_status()
    print("✅ トークン発行成功。LINE_CHANNEL_ID / LINE_CHANNEL_SECRET は正しく設定されています。")
    print("（このテストはLINEへのメッセージ送信は一切行いません）")

if __name__ == "__main__":
    main()
