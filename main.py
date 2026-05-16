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
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ─── 環境変数 ────────────────────────────────────────────────
LINE_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
LINE_USER_ID      = os.environ["LINE_USER_ID"]
SHOPSERVE_ID      = os.environ["SHOPSERVE_ID"]
SHOPSERVE_PASS    = os.environ["SHOPSERVE_PASS"]
DROPBOX_TOKEN     = os.environ["DROPBOX_TOKEN"]

LOGIN_URL  = "https://kanri9.shopserve.jp/tsukuhou.ko/"
REPORT_URL = "https://kanri9.shopserve.jp/tsukuhou.ko/func01/bil_report_sps.cgi"

# ─── ① ショップサーブへログイン＆PDFダウンロード ─────────────
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
    wait = WebDriverWait(driver, 30)

    try:
        print(f"ログインページへアクセス: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        time.sleep(3)

        # 全inputフィールドを列挙してデバッグ
        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"input要素数: {len(inputs)}")
        for i, inp in enumerate(inputs):
            print(
                f"  input[{i}]: type={inp.get_attribute('type')}, "
                f"name={inp.get_attribute('name')}, "
                f"id={inp.get_attribute('id')}, "
                f"class={inp.get_attribute('class')}"
            )

        # USERNAMEフィールドへ入力
        print("USERNAMEフィールドへ入力...")
        id_field = wait.until(
            EC.presence_of_element_located((By.NAME, "USERNAME"))
        )
        id_field.clear()
        id_field.send_keys(SHOPSERVE_ID)

        # パスワードフィールドを複数の方法で探す
        pass_field = None
        for selector_type, selector in [
            (By.NAME, "PASSWORD"),
            (By.NAME, "PASSWD"),
            (By.NAME, "password"),
            (By.NAME, "passwd"),
            (By.NAME, "pass"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                pass_field = driver.find_element(selector_type, selector)
                print(f"パスワードフィールド発見: {selector}")
                break
            except Exception:
                continue

        if pass_field is None:
            # type=passwordのinputを探す
            for inp in inputs:
                if inp.get_attribute("type") == "password":
                    pass_field = inp
                    print(f"パスワードフィールド発見（type=password）: name={inp.get_attribute('name')}")
                    break

        if pass_field is None:
            raise Exception("パスワードフィールドが見つかりません")

        pass_field.clear()
        pass_field.send_keys(SHOPSERVE_PASS)

        # JavaScriptでログイン実行
        print("loginSetup()を実行...")
        driver.execute_script("loginSetup();")
        time.sleep(4)
        print(f"ログイン後URL: {driver.current_url}")

        # ─── レポートページへ ───
        print(f"レポートページへアクセス: {REPORT_URL}")
        driver.get(REPORT_URL)
        time.sleep(3)
        print(f"レポートページURL: {driver.current_url}")

        # ページ上のリンクを確認
        links = driver.find_elements(By.TAG_NAME, "a")
        all_hrefs = [l.get_attribute("href") for l in links if l.get_attribute("href")]
        print(f"全リンク数: {len(all_hrefs)}")
        pdf_links = [h for h in all_hrefs if h and ".pdf" in h.lower()]
        print(f"PDFリンク: {pdf_links}")

        # PDFリンクがあればrequestsで直接ダウンロード
        if pdf_links:
            pdf_url = pdf_links[0]
            print(f"PDFを直接ダウンロード: {pdf_url}")

            session = requests.Session()
            for cookie in driver.get_cookies():
                session.cookies.set(cookie["name"], cookie["value"])

            resp = session.get(pdf_url, timeout=60)
            resp.raise_for_status()

            filename = pdf_url.split("/")[-1].split("?")[0]
            if not filename.endswith(".pdf"):
                filename = f"bil_report_{datetime.now().strftime('%Y%m%d')}.pdf"

            pdf_path = os.path.join(download_dir, filename)
            with open(pdf_path, "wb") as f:
                f.write(resp.content)
            print(f"PDF保存完了: {pdf_path} ({len(resp.content)} bytes)")
            return pdf_path

        # Seleniumのダウンロード待ち（フォールバック）
        print("PDFリンクが見つからない。ダウンロード完了を待機...")
        for i in range(90):
            files = [
                f for f in os.listdir(download_dir)
                if f.endswith(".pdf") and not f.endswith(".crdownload")
            ]
            if files:
                files.sort(
                    key=lambda f: os.path.getmtime(os.path.join(download_dir, f)),
                    reverse=True,
                )
                pdf_path = os.path.join(download_dir, files[0])
                print(f"PDFダウンロード完了: {pdf_path}")
                return pdf_path
            if i % 10 == 0:
                print(f"  ダウンロード待機中... {i}秒")
            time.sleep(1)

        print(f"ダウンロードディレクトリの中身: {os.listdir(download_dir)}")
        raise FileNotFoundError("PDFが見つかりませんでした")

    finally:
        driver.quit()


# ─── ② Dropboxにアップロードして共有リンクを取得 ──────────────
def upload_to_dropbox(pdf_path: str) -> str:
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    filename = os.path.basename(pdf_path)
    dropbox_path = f"/tsukuhou-report/{filename}"

    with open(pdf_path, "rb") as f:
        dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
    print(f"Dropboxアップロード完了: {dropbox_path}")

    try:
        link_meta = dbx.sharing_create_shared_link_with_settings(dropbox_path)
    except dropbox.exceptions.ApiError:
        links = dbx.sharing_list_shared_links(path=dropbox_path).links
        if not links:
            raise
        link_meta = links[0]

    return link_meta.url.replace("dl=0", "dl=1")


# ─── ③ LINEにテキスト＋URLを送信 ─────────────────────────────
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


# ─── メイン処理 ───────────────────────────────────────────────
def main():
    now = datetime.now()
    month_str = now.strftime("%Y年%-m月")

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
