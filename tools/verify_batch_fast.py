# verify_batch_fast.py (v4.1 - Safe Mode)
# 功能：修復 429 Quota Exceeded 問題，加入 API 請求間隔

import os
import time
import requests
import hashlib
import urllib.parse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================= 配置區 =================
# Gname API
GNAME_API_URL = "https://api.gname.com/api/resolution/add"
GNAME_APPID = "126291696ef58ce4574"
GNAME_APPKEY = "5lPe55N621Oe2LogMjNq"

# Google Auth
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(CURRENT_DIR, 'client_secrets.json')
TOKEN_FILE = os.path.join(CURRENT_DIR, 'token.json')
SCOPES = [
    'https://www.googleapis.com/auth/webmasters',
    'https://www.googleapis.com/auth/siteverification'
]

# 檔案路徑
INPUT_FILE = os.path.join(CURRENT_DIR, 'domains.txt')
SUCCESS_FILE = os.path.join(CURRENT_DIR, 'success.txt')
FAILED_FILE = os.path.join(CURRENT_DIR, 'failed.txt')

# 批次設定
BATCH_SIZE = 30  # [修復] 降至 30 個一組，減少瞬間壓力
DNS_WAIT_TIME = 45 

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

def log_result(filename, domain, msg=""):
    with open(filename, 'a', encoding='utf-8') as f:
        if msg: f.write(f"{domain} | {msg}\n")
        else: f.write(f"{domain}\n")

def clean_domain(domain):
    domain = domain.strip()
    if domain.startswith("www."): return domain[4:]
    return domain

# ================= Google & Gname 核心邏輯 =================
def get_services():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try: creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except: creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try: creds.refresh(Request())
            except: creds = None
        if not creds:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print("❌ 錯誤：找不到 client_secrets.json")
                return None, None
            print("🌐 開啟瀏覽器登入 Google...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token: token.write(creds.to_json())
    
    return build('searchconsole', 'v1', credentials=creds), build('siteVerification', 'v1', credentials=creds)

def process_single_prep(sc_service, sv_service, domain):
    """第一步：獲取 Token 並寫入 DNS (不等待)"""
    try:
        # 1. Add to GSC
        try:
            sc_service.sites().add(siteUrl=f"sc-domain:{domain}").execute()
        except: pass 

        # 2. Get Token (這是最容易撞牆的地方)
        req = {"site": {"identifier": domain, "type": "INET_DOMAIN"}, "verificationMethod": "DNS_TXT"}
        resp = sv_service.webResource().getToken(body=req).execute()
        token = resp['token']

        # 3. Write to Gname
        timestamp = int(time.time())
        params = {
            "appid": GNAME_APPID, "gntime": timestamp, "ym": domain,
            "lx": "TXT", "zj": "@", "jlz": token, "mx": 0, "ttl": 600
        }
        params['gntoken'] = generate_gname_signature(params, GNAME_APPKEY)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        r = requests.post(GNAME_API_URL, data=params, headers=headers, timeout=10)
        res_json = r.json()
        
        if res_json.get('code') == 1:
            print(f"  📝 [DNS OK] {domain}")
            return True
        else:
            msg = str(res_json.get('msg'))
            if "复" in msg or "exist" in msg or "相同" in msg:
                print(f"  📝 [DNS Exist] {domain}")
                return True
            print(f"  ❌ [Gname Error] {domain}: {msg}")
            return False

    except Exception as e:
        print(f"  ❌ [Prep Error] {domain}: {e}")
        return False

def process_single_verify(sv_service, domain):
    """第二步：執行驗證 (只做驗證動作)"""
    try:
        body = {"site": {"identifier": domain, "type": "INET_DOMAIN"}}
        sv_service.webResource().insert(verificationMethod="DNS_TXT", body=body).execute()
        print(f"  ✅ [Verified] {domain}")
        return True
    except Exception as e:
        if "already verified" in str(e):
            print(f"  ✅ [Already Verified] {domain}")
            return True
        print(f"  ❌ [Verify Failed] {domain}: {e}")
        return False

# ================= 批次處理核心 =================
def process_batch(sc, sv, batch_domains):
    print(f"\n📦 開始處理批次 (共 {len(batch_domains)} 個)...")
    
    pending_verify = []

    # 1. 快速迴圈：拿 Token + 寫 DNS
    print("👉 階段一：獲取 Token 並寫入 DNS...")
    for domain in batch_domains:
        if process_single_prep(sc, sv, domain):
            pending_verify.append(domain)
            # [修復重點] 加入 1.5 秒冷卻，避免撞到 Google API 限制
            time.sleep(1.5) 
        else:
            log_result(FAILED_FILE, domain, "DNS/Token Error")
    
    if not pending_verify:
        print("⚠️ 此批次無成功寫入 DNS 的域名，跳過等待。")
        return

    # 2. 統一等待
    print(f"⏳ 全批次暫停 {DNS_WAIT_TIME} 秒，等待 DNS 生效...")
    time.sleep(DNS_WAIT_TIME)

    # 3. 快速迴圈：驗證
    print("👉 階段二：提交驗證...")
    for domain in pending_verify:
        if process_single_verify(sv, domain):
            log_result(SUCCESS_FILE, domain)
            time.sleep(0.5) # 驗證時也稍微慢一點點
        else:
            print(f"  ⚠️ {domain} 驗證失敗，稍後重試一次...")
            time.sleep(1)
            if process_single_verify(sv, domain):
                log_result(SUCCESS_FILE, domain)
            else:
                log_result(FAILED_FILE, domain, "Verification Failed")

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 找不到 {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r') as f:
        lines = f.readlines()
    
    domains = []
    seen = set()
    for line in lines:
        d = clean_domain(line)
        if d and d not in seen:
            seen.add(d)
            domains.append(d)
            
    print(f"🚀 載入 {len(domains)} 個唯一域名，準備批量驗證！")
    print(f"⚡️ 批次大小: {BATCH_SIZE} | 等待時間: {DNS_WAIT_TIME}秒")
    print("------------------------------------------------")

    sc_service, sv_service = get_services()
    if not sc_service: return

    # 分塊處理
    total_batches = (len(domains) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(0, len(domains), BATCH_SIZE):
        batch = domains[i : i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1
        print(f"\n🔹 [Batch {current_batch_num}/{total_batches}] 處理 {len(batch)} 個域名")
        process_batch(sc_service, sv_service, batch)

    print("\n🎉 所有批次處理完成！")

if __name__ == "__main__":
    main()