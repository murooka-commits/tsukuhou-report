import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== 設定 =====
SHOPSERVE_ID = os.environ["SHOPSERVE_ID"]
SHOPSERVE_PASS = os.environ["SHOPSERVE_PASS"]
LINE_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]  # 鈴木社長のユーザーID

LOGIN_URL = "https://kanri9.shopserve.jp/index.cgi"
REPORT_URL = f"https://kanri9.shopserve.jp/{SHOPSERVE_ID}/func01/bil_report_sps.cgi"
PDF_PATH = "/tmp/report.pdf"

def download_pdf():
    """ショップサーブに自動ログインしてPDFをダウンロード"""
    print("ブラウザを起動中...")

    # Chromeの設定
    options = Options()
    options.add_argument("--headless")           # 画面なしで動作
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # ダウンロード先の設定
    prefs = {
        "download.default_directory": "/tmp",
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    try:
        # ログイン
        print("ログイン中...")
        driver.get(LOGIN_URL)
        wait.until(EC.presence_of_element_located((By.NAME, "shop_id")))
        driver.find_element(By.NAME, "shop_id").send_keys(SHOPSERVE_ID)
        driver.find_element(By.NAME, "password").send_keys(SHOPSERVE_PASS)
        driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        time.sleep(3)

        # レポートページへ移動
        print("レポートページへ移動中...")
        driver.get(REPORT_URL)
        time.sleep(3)

        # 最新のダウンロードボタンをクリック
        print("PDFをダウンロード中...")
        download_buttons = driver.find_elements(By.XPATH, "//input[@value='ダウンロード'] | //a[contains(text(),'ダウンロード')]")
        if download_buttons:
            download_buttons[0].click()
            time.sleep(5)
            print("PDFダウンロード完了！")
        else:
            raise Exception("ダウンロードボタンが見つかりません")

    finally:
        driver.quit()

def send_line_pdf():
    """LINE Messaging APIでPDFを送信"""
    print("LINEにPDFを送信中...")

    # まずテキストメッセージを送信
    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # テキストメッセージ
    from datetime import datetime, timedelta
    last_month = datetime.now().replace(day=1) - timedelta(days=1)
    month_str = last_month.strftime("%Y年%m月")

    text_data = {
        "to": LINE_USER_ID,
        "messages": [{
            "type": "text",
            "text": f"お世話になっております。\nCPSTYLE八王子です。\n\n{month_str}分の振込明細書をお送りします。"
        }]
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json=text_data
    )
    print(f"テキスト送信結果: {response.status_code}")

    # PDFファイルを送信
    with open(PDF_PATH, "rb") as f:
        files = {"file": ("report.pdf", f, "application/pdf")}
        upload_headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
        upload_response = requests.post(
            "https://api-data.line.me/v2/bot/message/push/multipart",
            headers=upload_headers,
            data={"to": LINE_USER_ID, "messages": '[{"type":"file","originalContentUrl":"","previewImageUrl":""}]'},
            files=files
        )

    # ファイル送信（代替：PDFのURLをメッセージで送る）
    print("LINE送信完了！")

if __name__ == "__main__":
    print("=== 月次レポート自動送信開始 ===")
    download_pdf()
    send_line_pdf()
    print("=== 完了 ===")
