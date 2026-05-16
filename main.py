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
        # ─── ログイン ───
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

        # ─── レポートページへ ───
        driver.get(REPORT_URL)
        time.sleep(3)

        # ページソースを全部出力してPDFダウンロードの仕組みを確認
        page_source = driver.page_source
        print("=== レポートページソース（先頭5000文字）===")
        print(page_source[:5000])
        print("=== ここまで ===")

        # ボタン・フォームを列挙
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"\nボタン数: {len(buttons)}")
        for i, btn in enumerate(buttons):
            print(f"  button[{i}]: text={btn.text}, onclick={btn.get_attribute('onclick')}, type={btn.get_attribute('type')}")

        forms = driver.find_elements(By.TAG_NAME, "form")
        print(f"\nフォーム数: {len(forms)}")
        for i, form in enumerate(forms):
            print(f"  form[{i}]: action={form.get_attribute('action')}, method={form.get_attribute('method')}")

        # inputのsubmitボタンを列挙
        submits = driver.find_elements(By.CSS_SELECTOR, "input[type='submit'], input[type='button']")
        print(f"\nsubmit/buttonインプット数: {len(submits)}")
        for i, s in enumerate(submits):
            print(f"  submit[{i}]: value={s.get_attribute('value')}, name={s.get_attribute('name')}, onclick={s.get_attribute('onclick')}")

        # onclickにbil_reportやpdfが含まれる要素を探す
        all_elements = driver.find_elements(By.CSS_SELECTOR, "[onclick]")
        print(f"\nonclick要素数: {len(all_elements)}")
        for el in all_elements:
            onclick = el.get_attribute("onclick") or ""
            if any(kw in onclick.lower() for kw in ["pdf", "bil", "report", "download"]):
                print(f"  関連要素: tag={el.tag_name}, text={el.text[:50]}, onclick={onclick}")

        raise Exception("デバッグ完了：ログを確認してください")

    finally:
        driver.quit()


def upload_to_dropbox(pdf_path: str) -> str:
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    filename = os.path.basename(pdf_path)
    dropbox_path = f"/tsukuhou-report/{filename}"
    with open(pdf_path, "rb") as f:
        dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
    try:
        link_meta = dbx.sharing_create_shared_link_with_settings(dropbox_path)
    except dropbox.exceptions.ApiError:
        links = dbx.sharing_list_shared_links(path=dropbox_path).links
        link_meta = links[0]
    return link_meta.url.replace("dl=0", "dl=1")


def send_line_message(text: str) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    print(f"LINE送信完了: {resp.status_code}")


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
