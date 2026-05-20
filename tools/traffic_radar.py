# traffic_radar.py
# 功能：掃描全網 (2,000+ 站) 的 GSC 流量數據
# 邏輯：Smart SA 輪詢 + Search Analytics API (90天長週期版)

import os
import csv
import json
import time
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ================= 設定區 =================
SOURCE_CSV = 'gsc_report.csv'      # 來源：之前的全網體檢報告
OUTPUT_FILE = 'traffic_report_90d.csv' # 輸出：90天流量報告
TOTAL_SAS = 10                     # 10組 SA 輪詢機制
SA_FOLDER = '.' 
DAYS_TO_CHECK = 90                 # 修改處：檢查過去 90 天的數據[cite: 1]
# =========================================

def get_service(sa_index):
    sa_file = os.path.join(SA_FOLDER, f"sa{sa_index}.json")
    if not os.path.exists(sa_file):
        return None
    try:
        # 使用你資料夾內的 sa{n}.json 進行認證[cite: 1]
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=['https://www.googleapis.com/auth/webmasters']
        )
        return build('searchconsole', 'v1', credentials=creds, cache_discovery=False)
    except:
        return None

def get_search_analytics(service, domain):
    site_url = f"sc-domain:{domain}"
    
    # 計算日期範圍：GSC 數據通常有 2-3 天延遲，回推 90 天[cite: 1]
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=DAYS_TO_CHECK)
    
    request_body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["date"], 
        "rowLimit": 100 # 增加 rowLimit 以確保 90 天的數據都被累加
    }

    try:
        # 確保網域已加入該 SA 的清單[cite: 1]
        try:
            service.sites().add(siteUrl=site_url).execute()
        except:
            pass

        # 查詢點擊與曝光數據[cite: 1]
        response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
        
        total_clicks = 0
        total_impressions = 0
        
        if 'rows' in response:
            for row in response['rows']:
                total_clicks += row.get('clicks', 0)
                total_impressions += row.get('impressions', 0)
        
        return {
            "clicks": total_clicks,
            "impressions": total_impressions,
            "status": "OK"
        }

    except Exception as e:
        if "You do not own this site" in str(e) or "403" in str(e):
            return "PERMISSION_DENIED"
        return {"error": str(e), "status": "ERROR"}

def main():
    if not os.path.exists(SOURCE_CSV):
        print(f"❌ 找不到 {SOURCE_CSV}，請確認檔案存在。")
        return

    # 讀取域名清單[cite: 1]
    domains = []
    with open(SOURCE_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Domain'):
                domains.append(row['Domain'])

    print(f"🚀 啟動 90 天流量長程雷達")
    print(f"🎯 目標: 掃描 {len(domains)} 個站點的流量")
    print("-" * 60)

    # 預載入 10 組服務帳號[cite: 1]
    services = {}
    for i in range(1, TOTAL_SAS + 1):
        svc = get_service(i)
        if svc: services[i] = svc

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Domain', 'Clicks (90d)', 'Impressions (90d)', 'CTR', 'Status', 'SA Used'])

        for idx, domain in enumerate(domains):
            print(f"[{idx+1}/{len(domains)}] 🔍 正在查詢 {domain} ...", end="\r")
            
            final_result = None
            working_sa = "NONE"

            # 自動輪詢 10 組 SA 直到獲得權限[cite: 1]
            for sa_num in range(1, TOTAL_SAS + 1):
                if sa_num not in services: continue
                
                result = get_search_analytics(services[sa_num], domain)
                
                if result != "PERMISSION_DENIED":
                    final_result = result
                    working_sa = f"sa{sa_num}"
                    break
            
            clicks = 0
            impressions = 0
            status = "AUTH_FAIL"
            ctr = "0%"

            if final_result and isinstance(final_result, dict):
                if final_result['status'] == 'OK':
                    clicks = final_result['clicks']
                    impressions = final_result['impressions']
                    status = "OK"
                    if impressions > 0:
                        ctr = f"{(clicks/impressions)*100:.2f}%"
                else:
                    status = "API_ERROR"
            
            # 流量亮點顯示
            if clicks > 50: # 90天點擊大於50設為大礦標誌
                print(f"[{idx+1}/{len(domains)}] 💎 發現金礦！ {domain} -> {clicks} Clicks (by {working_sa})")
            elif clicks > 0:
                print(f"[{idx+1}/{len(domains)}] 💰 穩定產出: {domain} -> {clicks} Clicks (by {working_sa})")
            elif impressions > 1000:
                print(f"[{idx+1}/{len(domains)}] 👀 高潛力站: {domain} -> {impressions} Imps (by {working_sa})")

            writer.writerow([domain, clicks, impressions, ctr, status, working_sa])

    print(f"\n\n🎉 90 天流量掃描完成！結果已存入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()