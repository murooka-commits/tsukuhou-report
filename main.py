import os
import time
import requests
import dropbox
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── 環境変数 ────────────────────────────────────────────────
LINE_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID      = os.environ["LINE_USER_ID"]
SHOPSERVE_ID      = os.environ["SHOPSERVE_ID"]
SHOPSERVE_PASS    = os.environ["SHOPSERVE_PASS"]
DROPBOX_TOKEN     = os.environ["DROPBOX_TOKEN"]

REPORT_URL = (
    "https://kanri9.shopserve.jp/tsukuhou.ko/func01/bil_report_sps.cgi"
)

# ─── ① ショップサーブへログイン＆PDFダウンロード ─────────────
def download_pdf() -> str:
    """
    Seleniumでショップサーブにログインし、PDFをダウンロードして
    ローカルパスを返す。
    """
    download_dir = "/tmp/shopserve"
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        },
    )

    driver = webdriver.Chrome(options=options)
    wait   = WebDriverWait(driver, 30)

    try:
        # ログインページへ
        driver.get("https://kanri9.shopserve.jp/tsukuhou.ko/")
        wait.until(EC.presence_of_element_located((By.NAME, "login_id")))

        driver.find_element(By.NAME, "login_id").send_keys(SHOPSERVE_ID)
        driver.find_element(By.NAME, "password").send_keys(SHOPSERVE_PASS)
        driver.find_element(By.NAME, "password").submit()

        # レポートページへ
        driver.get(REPORT_URL)
        time.sleep(3)

        # ダウンロード完了待ち（最大60秒）
        pdf_path = None
        for _ in range(60):
            files = [
                f for f in os.listdir(download_dir)
                if f.endswith(".pdf") and not f.endswith(".crdownload")
            ]
            if files:
                # 最新ファイルを選択
                files.sort(
                    key=lambda f: os.path.getmtime(
                        os.path.join(download_dir, f)
                    ),
                    reverse=True,
                )
                pdf_path = os.path.join(download_dir, files[0])
                break
            time.sleep(1)

        if not pdf_path:
            raise FileNotFoundError("PDFのダウンロードがタイムアウトしました")

        return pdf_path

    finally:
        driver.quit()


# ─── ② Dropboxにアップロードして共有リンクを取得 ──────────────
def upload_to_dropbox(pdf_path: str) -> str:
    """
    PDFをDropboxにアップロードし、直接ダウンロードできる共有URLを返す。
    """
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)

    filename   = os.path.basename(pdf_path)
    dropbox_path = f"/tsukuhou-report/{filename}"

    with open(pdf_path, "rb") as f:
        dbx.files_upload(
            f.read(),
            dropbox_path,
            mode=dropbox.files.WriteMode.overwrite,
        )

    # 共有リンクを作成（既存なら取得）
    try:
        link_meta = dbx.sharing_create_shared_link_with_settings(dropbox_path)
    except dropbox.exceptions.ApiError as e:
        # すでにリンクが存在する場合
        links = dbx.sharing_list_shared_links(path=dropbox_path).links
        if not links:
            raise
        link_meta = links[0]

    # dl=0 → dl=1 に変換すると直接ダウンロードリンクになる
    shared_url = link_meta.url.replace("dl=0", "dl=1")
    return shared_url


# ─── ③ LINEにテキスト＋URLを送信 ─────────────────────────────
def send_line_message(text: str) -> None:
    """
    LINE Messaging API でプッシュメッセージを送信する。
    """
    url     = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    print("LINE送信完了:", resp.status_code)


# ─── メイン処理 ───────────────────────────────────────────────
def main():
    now = datetime.now()
    month_str = now.strftime("%Y年%-m月")   # 例: 2026年5月

    print("① PDFダウンロード開始...")
    pdf_path = download_pdf()
    print(f"   ダウンロード完了: {pdf_path}")

    print("② Dropboxアップロード開始...")
    shared_url = upload_to_dropbox(pdf_path)
    print(f"   アップロード完了: {shared_url}")

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
