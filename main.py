import os
import time
import glob
import json
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ===== 設定 =====
SHOPSERVE_ID = os.environ["SHOPSERVE_ID"]
SHOPSERVE_PASS = os.environ["SHOPSERVE_PASS"]
LINE_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]

LOGIN_URL = "https://kanri9.shopserve.jp/index.cgi"
REPORT_URL = f"https://kanri9.shopserve.jp/{SHOPSERVE_ID}/func01/bil_report_sps.cgi"
DOWNLOAD_DIR = "/tmp/downloads"

def download_pdf():
    print("ブラウザを起動中...")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    try:
        print("ログイン中...")
        driver.get(LOGIN_URL)
        wait.until(EC.presence_of_element_located((By.NAME, "USERNAME")))
        driver.find_element(By.NAME, "USERNAME").send_keys(SHOPSERVE_ID)
        driver.find_element(By.NAME, "PASSWD").send_keys(SHOPSERVE_PASS)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()
        time.sleep(3)

        print("レポートページへ移動中...")
        driver.get(REPORT_URL)
        time.sleep(3)

        print("PDFをダウンロード中...")
        download_buttons = driver.find_elements(
            By.XPATH,
            "//input[@value='ダウンロード'] | //a[contains(text(),'ダウンロード')] | //button[contains(text(),'ダウンロード')]"
        )
        if download_buttons:
            download_buttons[0].click()
            time.sleep(8)
            print("PDFダウンロード完了！")
        else:
            raise Exception("ダウンロードボタンが見つかりません")
    finally:
        driver.quit()

    pdf_files = glob.glob(f"{DOWNLOAD_DIR}/*.pdf")
    if not pdf_files:
        raise Exception(f"PDFファイルが見つかりません: {os.listdir(DOWNLOAD_DIR)}")

    pdf_path = pdf_files[0]
    print(f"PDFファイル: {pdf_path}")
    return pdf_path

def upload_to_google_drive(pdf_path):
    print("Google Driveにアップロード中...")

    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

    service = build("drive", "v3", credentials=creds)

    last_month = datetime.now().replace(day=1) - timedelta(days=1)
    month_str = last_month.strftime("%Y年%m月")
    file_name = f"佃宝_{month_str}_振込明細書.pdf"

    file_metadata = {"name": file_name, "mimeType": "application/pdf"}
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    file_id = file.get("id")
    print(f"アップロード完了！ファイルID: {file_id}")

    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    share_link = f"https://drive.google.com/file/d/{file_id}/view"
    print(f"共有リンク: {share_link}")
    return share_link, month_str

def send_line_message(share_link, month_str):
    print("LINEにメッセージを送信中...")

    headers = {
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    message = f"お世話になっております。\nCPSTYLE八王子です。\n\n{month_str}分の振込明細書をお送りします。\n\n▼ PDFはこちらからご確認ください\n{share_link}"

    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }

    response = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers=headers,
        json=data
    )
    print(f"LINE送信結果: {response.status_code} {response.text}")

    if response.status_code != 200:
        raise Exception(f"LINE送信エラー: {response.status_code} {response.text}")

    print("LINE送信完了！")

if __name__ == "__main__":
    print("=== 月次レポート自動送信開始 ===")
    pdf_path = download_pdf()
    share_link, month_str = upload_to_google_drive(pdf_path)
    send_line_message(share_link, month_str)
    print("=== 完了 ===")
