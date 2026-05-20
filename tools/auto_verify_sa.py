# auto_verify_sa.py
# 功能：讓 Service Account (SA) 自動進行「自我驗證」，成為網站擁有者
# 優勢：繞過 Google 關閉的 User API，直接透過 DNS 獲取最高權限
# 流程：SA登入 -> 拿驗證碼 -> Gname寫DNS -> SA驗證

import os
import time
import json
import requests
import hashlib
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ================= Gname 配置 (請填入您的設定) =================
GNAME_API_URL = "https://api.gname.com/api/resolution/add"
GNAME_APPID = "126291696ef58ce4574"   # 請確認與 verify_batch.py 一致
GNAME_APPKEY = "5lPe55N621Oe2LogMjNq" # 請確認與 verify_batch.py 一致

# ================= 腳本配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SUCCESS_FILE = os.path.join(CURRENT_DIR, 'success.txt')
# SA 檔案命名規則：sa1.json, sa2.json ... sa10.json
SA_FILE_TEMPLATE = "sa{}.json" 

# GSC 權限範圍
SCOPES = [
    'https://www.googleapis.com/auth/webmasters',
    'https://www.googleapis.com/auth/siteverification'
]

# ================= 工具函數 =================
def generate_gname_signature(params, app_key):
    sorted_keys = sorted(params.keys())
    kv_pairs = []
    for key in sorted_keys:
        val = str(params[key])
        encoded_val = urllib.parse.quote_plus(val)
        kv_pairs.append(f"{key}={encoded_val}")
    string_a = "&".join(kv_pairs)
    string_sign_temp = string_a + app_key
    return hashlib.md5(string_sign_temp.encode('utf-8')).hexdigest().upper()

def add_gname_dns(domain, token):
    """呼叫 Gname API 寫入 TXT 記錄"""
    timestamp = int(time.time())
    params = {
        "appid": GNAME_APPID, "gntime": timestamp, "ym": domain,
        "lx": "TXT", "zj": "@", "jlz": token, "mx": 0, "ttl": 600
    }
    params['gntoken'] = generate_gname_signature(params, GNAME_APPKEY)
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        r = requests.post(GNAME_API_URL, data=params, headers=headers, timeout=15)
        res_json = r.json()
        if res_json.get('code') == 1:
            return True
        msg = str(res_json.get('msg'))
        if "复" in msg or "exist" in msg or "相同" in msg:
            return True 
        print(f"    ❌ Gname 寫入失敗: {msg}")
        return False
    except Exception as e:
        print(f"    ❌ Gname 連線錯誤: {e}")
        return False

def get_sa_service(sa_file_path):
    """使用 JSON 金鑰登入 SA"""
    if not os.path.exists(sa_file_path):
        print(f"❌ 找不到金鑰檔案: {sa_file_path}")
        return None, None
    
    try:
        creds = service_account.Credentials.from_service_account_file(sa_file_path, scopes=SCOPES)
        # 我們需要兩個服務：GSC (加資源) 和 SiteVerification (驗證)
        sc = build('searchconsole', 'v1', credentials=creds)
        sv = build('siteVerification', 'v1', credentials=creds)
        return sc, sv, creds.service_account_email
    except Exception as e:
        print(f"❌ SA 登入失敗 {sa_file_path}: {e}")
        return None, None, None

def process_sa_batch(sa_index, domains):
    """處理單一 SA 的所有域名"""
    sa_filename = SA_FILE_TEMPLATE.format(sa_index)
    sa_path = os.path.join(CURRENT_DIR, sa_filename)
    
    print(f"\n🤖 [SA #{sa_index}] 載入身分: {sa_filename} ...")
    sc_service, sv_service, sa_email = get_sa_service(sa_path)
    
    if not sc_service:
        print(f"⚠️ 跳過 SA #{sa_index} (無法登入)")
        return

    print(f"   📧 Email: {sa_email}")
    print(f"   Mw 任務目標: 驗證 {len(domains)} 個網站")
    
    # 批次處理，避免 Gname 請求過快
    BATCH_SIZE = 10
    
    for i in range(0, len(domains), BATCH_SIZE):
        batch = domains[i : i + BATCH_SIZE]
        print(f"   📦 處理批次 {i+1}-{i+len(batch)} ...")
        
        pending_verify = [] # (domain, token)
        
        # 1. 獲取 Token 並寫入 DNS
        for domain in batch:
            try:
                # 告訴 Google SA 要管理這個網域
                site_url = f"sc-domain:{domain}"
                try:
                    sc_service.sites().add(siteUrl=site_url).execute()
                except:
                    pass # 如果已經加過，忽略

                # 拿驗證碼
                request_body = { "site": { "identifier": domain, "type": "INET_DOMAIN" }, "verificationMethod": "DNS_TXT" }
                token_resp = sv_service.webResource().getToken(body=request_body).execute()
                token = token_resp['token']
                
                # 寫 DNS
                if add_gname_dns(domain, token):
                    pending_verify.append(domain)
                    print(f"      📝 {domain} -> DNS 寫入成功")
                
                time.sleep(0.2)
                
            except Exception as e:
                print(f"      ❌ {domain} 準備失敗: {e}")

        if not pending_verify: continue

        # 2. 等待 DNS 生效
        print("      ⏳ 等待 40 秒讓 DNS 生效...")
        time.sleep(40)
        
        # 3. 執行驗證
        for domain in pending_verify:
            try:
                body = { "site": { "identifier": domain, "type": "INET_DOMAIN" } }
                sv_service.webResource().insert(verificationMethod="DNS_TXT", body=body).execute()
                print(f"      ✅ {domain} -> SA 驗證成功 (Owner)")
            except Exception as e:
                if "already verified" in str(e):
                    print(f"      ✅ {domain} -> 已經是 Owner 了")
                else:
                    print(f"      ❌ {domain} 驗證失敗: {e}")
                    # 簡單重試一次
                    try:
                        time.sleep(2)
                        sv_service.webResource().insert(verificationMethod="DNS_TXT", body=body).execute()
                        print(f"      ✅ {domain} -> 重試成功")
                    except:
                        pass

def main():
    if not os.path.exists(SUCCESS_FILE):
        print("❌ 找不到 success.txt")
        return

    # 讀取所有域名
    all_domains = []
    with open(SUCCESS_FILE, 'r') as f:
        for line in f:
            d = line.split('|')[0].strip()
            if d: all_domains.append(d)
    all_domains = sorted(list(set(all_domains)))
    
    print(f"🚀 啟動 SA 自我驗證程序，共 {len(all_domains)} 個網站。")
    print("------------------------------------------------")
    
    # 策略：每 160 個域名換一個 SA
    SA_CAPACITY = 160
    total_sas = 10 # 假設有 10 個 SA json
    
    # 將域名分組分配給 SA
    # sa_batches = { 1: [domains...], 2: [domains...] }
    sa_batches = {}
    
    for i, domain in enumerate(all_domains):
        # 計算是第幾個 SA (1-based)
        # 0-159 -> sa1, 160-319 -> sa2 ...
        sa_num = (i // SA_CAPACITY) % total_sas + 1
        
        if sa_num not in sa_batches:
            sa_batches[sa_num] = []
        sa_batches[sa_num].append(domain)
        
    # 開始執行
    for sa_num in sorted(sa_batches.keys()):
        domains = sa_batches[sa_num]
        process_sa_batch(sa_num, domains)
        
    print("\n🎉 全部 SA 驗證程序結束！")

if __name__ == "__main__":
    main() 