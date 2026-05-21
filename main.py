import os
import time
import requests
import dropbox
from dropbox.oauth import DropboxOAuth2FlowNoRedirect
from datetime import datetime
from dateutil.relativedelta import relativedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ─── 環境変数 ────────────────────────────────────────────────
LINE_ACCESS_TOKEN    = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID         = os.environ["LINE_USER_ID"]
SHOPSERVE_ID         = os.environ["SHOPSERVE_ID"]
SHOPSERVE_PASS       = os.environ["SHOPSERVE_PASS"]
DROPBOX_APP_KEY      = os.environ["DROPBOX_APP_KEY"]
DROPBOX_APP_SECRET   = os.environ["DROPBOX_APP_SECRET"]
DROPBOX_REFRESH_TOKEN = os.environ["DROPBOX_REFRESH_TOKEN"]

LOGIN_URL  = "https://kanri9.shopserve.jp/tsukuhou.ko/"
REPORT_URL = "https://kanri9.shopserve.jp/tsukuhou.ko/func01/bil_report_sps.cgi"

def download_pdf() -> str:
    download_dir = "/tmp/shopserve"
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
    wait = WebDriverWait(driver, 30)

    try:
        driver.get(LOGIN_URL)
        time.sleep(3)
        id_field = wait.until(EC.presence_of_element_located((By.NAME, "USERNAME")))
        pass_field = driver.find_element(By.NAME, "PASSWD")
        id_field.clear()
        id_field.send_keys(SHOPSERVE_ID)
        pass_field.clear()
        pass_field.send_keys(SHOPSERVE_PASS)
        driver.execute_script("loginSetup();")
        time.sleep(4)
        print(f"ログイン後URL: {driver.current_url}")

        driver.get(REPORT_URL)
        time.sleep(3)

        download_btn = None
        submits = driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
        for s in submits:
            val = s.get_attribute("value") or ""
            if "ダウンロード" in val:
                download_btn = s
                break
        if download_btn is None and submits:
            download_btn = submits[0]

        before_files = set(os.listdir(download_dir))
        download_btn.click()
        print("ダウンロードボタンをクリックしました")
        time.sleep(5)

        pdf_path = None
        for i in range(90):
            current_files = set(os.listdir(download_dir))
            new_files = current_files - before_files
            pdf_files = [f for f in new_files if f.endswith(".pdf") and not f.endswith(".crdownload")]
            if pdf_files:
                pdf_path = os.path.join(download_dir, pdf_files[0])
                print(f"PDFダウンロード完了: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")
                break
            if i % 10 == 0:
                print(f"  待機中... {i}秒")
            time.sleep(1)

        if not pdf_path:
            raise FileNotFoundError("PDFが見つかりませんでした")

        return pdf_path

    finally:
        driver.quit()


def upload_to_dropbox(pdf_path: str) -> str:
    # リフレッシュトークンで自動的に新しいアクセストークンを取得
    dbx = dropbox.Dropbox(
        oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
        app_key=DROPBOX_APP_KEY,
        app_secret=DROPBOX_APP_SECRET,
    )

    filename = os.path.basename(pdf_path)
    dropbox_path = f"/tsukuhou-report/{filename}"
    with open(pdf_path, "rb") as f:
        dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
    print(f"Dropboxアップロード完了: {dropbox_path}")

    try:
        link_meta = dbx.sharing_create_shared_link_with_settings(dropbox_path)
    except dropbox.exceptions.ApiError:
        links = dbx.sharing_list_shared_links(path=dropbox_path).links
        link_meta = links[0]

    return link_meta.url.replace("dl=0", "dl=1")


def send_line_message(text: str) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    print(f"LINE送信完了: {resp.status_code}")


def main():
    now = datetime.now()
    last_month = now - relativedelta(months=1)
    month_str = last_month.strftime("%Y年%-m月")

    print("① PDFダウンロード開始...")
    pdf_path = download_pdf()

    print("② Dropboxアップロード開始...")
    shared_url = upload_to_dropbox(pdf_path)
    print(f"   共有URL: {shared_url}")

    print("③ LINE送信開始...")
    message = (
        f"【{month_str}分 代金回収レポート】\n\n"
        f"ショップサーブの月次レポートをお送りします。\n"
        f"下記リンクよりPDFをご確認ください。\n\n"
        f"{shared_url}"
    )
    send_line_message(message)
    print("✅ すべての処理が完了しました。")


if __name__ == "__main__":
    main()
