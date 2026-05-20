# google_push.py (v3.0 - 41nr.com DB Direct Edition)
import os
import time
import requests
import re
import json
import urllib3
import pymysql  # 🚀 新增：資料庫直連模組
from datetime import datetime
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 🚀 資料庫配置 (與 sitemap.php 對齊) =================
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "jieqidb",
    "password": "xsw2zaq1",
    "db": "jieqidb",
    "charset": "gbk"
}

# ================= Google 配置區 =================
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
SA_DIR = os.path.dirname(os.path.abspath(__file__))
SA_FILE_TEMPLATE = "sa{}.json"
TOTAL_SAS = 10
QUOTA_LIMIT = 195  

# ================= 工具函數 =================

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_msg(msg, end="\n"):
    text = f"[{get_now()}] {msg}"
    print(text, end=end)
    # 此處可保留原本的 LOG_FILE 寫入邏輯

def get_urls_from_db(max_count=200):
    """
    🚀 核心修改：直接從資料庫抓取 24 小時內更新的書籍網址
    優先推送詳情頁，這是 SEO 權重最高的地方
    """
    urls = []
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            # 抓取最近更新且 display=0 的書籍
            sql = "SELECT articleid FROM jieqi_article_article WHERE display = 0 ORDER BY lastupdate DESC LIMIT %s"
            cursor.execute(sql, (max_count,))
            rows = cursor.fetchall()
            for row in rows:
                aid = row[0]
                # 使用我們優化過後的路徑格式
                urls.append(f"https://m.41nr.com/txt/{aid}.html")
    except Exception as e:
        log_msg(f"❌ 資料庫查詢失敗: {e}")
    finally:
        if 'conn' in locals(): conn.close()
    
    return urls

def attempt_google_push(sa_idx, url):
    """執行 Google 推送"""
    sa_file = os.path.join(SA_DIR, SA_FILE_TEMPLATE.format(sa_idx))
    if not os.path.exists(sa_file): return 0, "Missing File"
    try:
        creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
        creds.refresh(Request())
        session = requests.Session()
        session.headers.update({"Authorization": "Bearer " + creds.token, "Content-Type": "application/json"})
        response = session.post(ENDPOINT, json={"url": url, "type": "URL_UPDATED"}, timeout=15, verify=False)
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)

# ================= 主程式 =================

def main():
    log_msg(f"📝 [資料庫版] 腳本啟動，準備為 m.41nr.com 進行精確推送...")

    # 1. 直接從資料庫抓取今天最值得推的 200 個網址 (對標 1 個 SA 的額度)
    target_urls = get_urls_from_db(max_count=200)
    
    if not target_urls:
        log_msg("⚠️ 沒有發現新更新的網址，任務結束。")
        return

    log_msg(f"🚀 成功獲取 {len(target_urls)} 個待推送網址。")

    sa_availability = {i: True for i in range(1, TOTAL_SAS + 1)}
    sa_usage = {i: 0 for i in range(1, TOTAL_SAS + 1)}
    total_success = 0
    current_sa = 1

    for i, url in enumerate(target_urls):
        # 尋找可用的 SA
        while current_sa <= TOTAL_SAS:
            if sa_availability[current_sa] and sa_usage[current_sa] < QUOTA_LIMIT:
                break
            current_sa += 1
        
        if current_sa > TOTAL_SAS:
            log_msg("🛑 所有 SA 配額已耗盡！")
            break

        status, resp = attempt_google_push(current_sa, url)

        if status == 200:
            sa_usage[current_sa] += 1
            total_success += 1
            log_msg(f"[{i+1}/{len(target_urls)}] ✅ SA#{current_sa} 推送成功: {url}")
        else:
            log_msg(f"[{i+1}/{len(target_urls)}] ❌ 推送失敗 ({status}): {url}")
            if status == 429: sa_availability[current_sa] = False

        time.sleep(0.5) # 安全間隔

    log_msg(f"🎉 任務完成！總計成功推送: {total_success} 條連結。")

if __name__ == "__main__":
    main()