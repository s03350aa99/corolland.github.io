# google_push.py (v2.6 - Speed Edition / No-Yandex)
# 功能：
# 1. [Speed] 移除 Yandex 推送，消除 5 秒連線超時瓶頸。
# 2. [VIP] 針對 corolland.com 維持批量推送 (50篇)。
# 3. [Batch] 支援單一域名多網址推送，快速建立老域名權重。

import os
import time
import requests
import re
import json
import urllib3
from datetime import datetime
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= Google 配置區 =================
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
SA_DIR = os.path.dirname(os.path.abspath(__file__))
SA_FILE_TEMPLATE = "sa{}.json"
TOTAL_SAS = 10
QUOTA_LIMIT = 195  # 每個 SA 每日安全限額 (官方200)

# 讀取域名來源
SUCCESS_FILE = os.path.join(SA_DIR, "success.txt")
# 失敗名單輸出
FAIL_FILE = os.path.join(SA_DIR, "fail.txt")
# ★★★ 日誌檔案路徑 ★★★
LOG_FILE = os.path.join(SA_DIR, "daily_push_log.txt")

# ================= IndexNow 配置區 (Bing Only) =================
INDEXNOW_KEY = "490a6062837f48529283035300589255"
INDEXNOW_FILE = "490a6062837f48529283035300589255.txt"
BING_ENDPOINT = "https://www.bing.com/indexnow"

# ================= 工具函數 =================


def get_now():
    """獲取當前時間字串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_msg(msg, end="\n"):
    """帶時間戳的輸出函數 (同時寫入 daily_push_log.txt)"""
    text = f"[{get_now()}] {msg}"
    print(text, end=end)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + end)
    except:
        pass


def get_latest_urls_batch(domain, max_count=1):
    """
    [升級版] 抓取最新的 N 個網址
    - 普通站點: max_count=1
    - VIP站點: max_count=50
    """
    urls_to_push = []

    # 優先嘗試 sitemap.php (動態)，其次 sitemap.xml
    for path in ["sitemap.php", "sitemap.xml"]:
        sitemap_url = f"https://{domain}/{path}"
        try:
            r = requests.get(sitemap_url, timeout=10, verify=False)
            if r.status_code == 200:
                # 抓取所有 <loc>
                found_urls = re.findall(r"<loc>(https?://[^<]+)</loc>", r.text)

                # 定義首頁變體 (這些不需要推)
                homepage_variants = [
                    f"https://{domain}/",
                    f"https://{domain}",
                    f"http://{domain}/",
                    f"http://{domain}",
                ]

                # 過濾並收集
                for u in found_urls:
                    u = u.strip()
                    if u not in homepage_variants and u not in urls_to_push:
                        urls_to_push.append(u)
                        if len(urls_to_push) >= max_count:
                            break

                # 如果成功抓到，就直接返回
                if urls_to_push:
                    return urls_to_push
        except:
            pass

    # 如果抓不到內頁，但至少要回傳首頁(作為保底)
    if not urls_to_push:
        return [f"https://{domain}/"]

    return urls_to_push


def attempt_google_push(sa_idx, url):
    """執行 Google 推送"""
    sa_file = os.path.join(SA_DIR, SA_FILE_TEMPLATE.format(sa_idx))
    if not os.path.exists(sa_file):
        return 0, "Missing File"
    try:
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=SCOPES
        )
        creds.refresh(Request())
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": "Bearer " + creds.token,
                "Content-Type": "application/json",
            }
        )
        response = session.post(
            ENDPOINT, json={"url": url, "type": "URL_UPDATED"}, timeout=15, verify=False
        )
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)


def push_to_indexnow(domain, url):
    """執行 IndexNow 推送 (僅 Bing)"""
    payload = {
        "host": domain,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{domain}/{INDEXNOW_FILE}",
        "urlList": [url],
    }

    # 只推送 Bing
    try:
        r_bing = requests.post(BING_ENDPOINT, json=payload, timeout=5)
        if r_bing.status_code in [200, 202]:
            return "Bing:✅"
        else:
            return f"Bing:{r_bing.status_code}"
    except:
        return "Bing:❌"


def run_push_process(domain_list, sa_availability, sa_usage, mode="第一輪"):
    """封裝好的推送流程 (Google + Bing)"""
    success_in_this_run = 0
    failed_in_this_run = []

    for i, domain in enumerate(domain_list):
        # VIP 判斷邏輯
        if "corolland.com" in domain:
            fetch_limit = 50
            is_vip = True
        else:
            fetch_limit = 1
            is_vip = False

        # 1. 獲取連結列表
        target_urls = get_latest_urls_batch(domain, max_count=fetch_limit)

        if is_vip:
            log_msg(f"👑 [VIP] 偵測到 {domain}，準備推送 {len(target_urls)} 篇 URL...")

        domain_failed = False

        for u_idx, target_url in enumerate(target_urls):
            # 顯示進度
            if is_vip:
                status_msg = f"[{mode}] [{i+1}/{len(domain_list)}] {domain} ({u_idx+1}/{len(target_urls)})"
            else:
                status_msg = f"[{mode}] [{i+1}/{len(domain_list)}] {domain}"

            # 3. 推送 Google
            google_pushed = False
            sa_used = 0

            for sa_idx in range(1, TOTAL_SAS + 1):
                if not sa_availability[sa_idx] or sa_usage[sa_idx] >= QUOTA_LIMIT:
                    continue

                status, resp = attempt_google_push(sa_idx, target_url)

                if status == 200:
                    sa_usage[sa_idx] += 1
                    google_pushed = True
                    sa_used = sa_idx
                    break
                elif status == 429:
                    log_msg(f"⚠️ SA#{sa_idx} 配額滿，切換下一個 SA。")
                    sa_availability[sa_idx] = False
                elif status == 403:
                    continue  # 權限不足，找下一個
                else:
                    break

            # 4. 推送 IndexNow (只推 Bing)
            indexnow_status = push_to_indexnow(domain, target_url)

            # 5. 整合日誌輸出
            url_suffix = target_url.split("/")[-1]
            if not url_suffix:
                url_suffix = "HOME"

            if google_pushed:
                log_msg(
                    f"{status_msg} -> 🔗 .../{url_suffix} | G(SA#{sa_used}):✅ | {indexnow_status}"
                )
                success_in_this_run += 1
            else:
                log_msg(f"{status_msg} -> ❌ Google 失敗 | {indexnow_status}")
                domain_failed = True

            # 極速模式：VIP 也不需要停頓太久
            if is_vip:
                time.sleep(0.1)

        if domain_failed and domain not in failed_in_this_run:
            failed_in_this_run.append(domain)

        # 極速模式：域名之間幾乎無延遲
        time.sleep(0.1)

    return success_in_this_run, failed_in_this_run


# ================= 主程式 =================


def main():
    log_msg(f"📝 [極速版] 腳本啟動，移除 Yandex 檢測...")

    if not os.path.exists(SUCCESS_FILE):
        log_msg("❌ 找不到 success.txt，任務終止。")
        return

    with open(SUCCESS_FILE, "r") as f:
        all_domains = sorted(
            list(set([line.split("|")[0].strip() for line in f if line.strip()]))
        )

    sa_availability = {i: True for i in range(1, TOTAL_SAS + 1)}
    sa_usage = {i: 0 for i in range(1, TOTAL_SAS + 1)}

    log_msg(f"🚀 [第一輪] 開始極速處理 {len(all_domains)} 個站點...")
    total_success, first_fail_list = run_push_process(
        all_domains, sa_availability, sa_usage, "第一輪"
    )

    if first_fail_list:
        log_msg(f"🔄 發現 {len(first_fail_list)} 個站點有失敗記錄，冷卻 5 秒後重試...")
        time.sleep(5)
        log_msg(f"🚀 [第二輪] 重新挑戰失敗站點...")
        retry_success, final_fail_list = run_push_process(
            first_fail_list, sa_availability, sa_usage, "第二輪"
        )
        total_success += retry_success
    else:
        final_fail_list = []

    # 寫入失敗名單
    with open(FAIL_FILE, "w") as f:
        for d in final_fail_list:
            f.write(f"{d}\n")

    print("\n" + "=" * 60)
    log_msg(f"🎉 任務總結完畢！")
    log_msg(f"✅ Google 成功推送總次數: {total_success}")
    log_msg(f"❌ 最終失敗站點數: {len(final_fail_list)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
