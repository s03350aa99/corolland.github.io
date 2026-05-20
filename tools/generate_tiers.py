# core/manager/generate_tiers.py
import pandas as pd
import json
import os

def generate_site_tiers(csv_path, tier1_manual_path):
    # 1. 載入原始 CSV 數據
    df = pd.read_csv(csv_path)
    df['Clicks (90d)'] = df['Clicks (90d)'].fillna(0)
    df['Impressions (90d)'] = df['Impressions (90d)'].fillna(0)
    
    # 2. 載入手動 150 個菁英名單 (白名單)
    manual_tier1 = set()
    if os.path.exists(tier1_manual_path):
        try:
            with open(tier1_manual_path, 'r', encoding='utf-8') as f:
                manual_tier1 = set(json.load(f))
            print(f"📥 已載入 {len(manual_tier1)} 個手動菁英站點 (白名單)")
        except Exception as e:
            print(f"⚠️ 載入白名單失敗: {e}")

    tiers = {
        "tier1": [], # Money Sites
        "tier2": [], # Rising Stars
        "tier3": []  # Dormant
    }
    
    processed_domains = set()

    # 3. 第一階段：處理 Tier 1 (白名單優先 + 數據黑馬)
    for _, row in df.iterrows():
        domain = row['Domain']
        clicks = row['Clicks (90d)']
        
        if domain in manual_tier1 or clicks > 0:
            tiers["tier1"].append(domain)
            processed_domains.add(domain)

    # 4. 第二階段：處理 Tier 2 與 Tier 3
    for _, row in df.iterrows():
        domain = row['Domain']
        if domain in processed_domains:
            continue
            
        impressions = row['Impressions (90d)']
        
        if impressions >= 50:
            tiers["tier2"].append(domain)
        else:
            tiers["tier3"].append(domain)
            
    # 5. 輸出統計與存檔
    print(f"✅ 雙重驗證分級完成！")
    print(f"   - Tier 1 (菁英): {len(tiers['tier1'])} 站")
    print(f"   - Tier 2 (潛力): {len(tiers['tier2'])} 站")
    print(f"   - Tier 3 (休眠): {len(tiers['tier3'])} 站")
    
    # --- 修正重點：確保目錄存在 ---
    output_path = 'core/manager/site_tiers.json'
    output_dir = os.path.dirname(output_path)
    
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"📂 已自動建立目錄: {output_dir}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tiers, f, indent=4)
    print(f"💾 分級地圖已成功存至: {output_path}")

if __name__ == "__main__":
    CSV_FILE = 'traffic_report_90d.csv'
    MANUAL_LIST = 'true_tier1_list.json' 
    generate_site_tiers(CSV_FILE, MANUAL_LIST)