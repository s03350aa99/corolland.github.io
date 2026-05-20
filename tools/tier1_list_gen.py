# tier1_list_gen.py
# 功能：將 410 個域名轉存為 JSON 格式供檢查腳本使用

import json

domains = [
    "fintechbase.cc", "radarfinancelab.cc", "assetvista.cc", "aisemanticnet.net",
    "wealthnews.cc", "wealthbeacon.cc", "avaxsignals.cc", "nearpulse.it.com",
    "aiforesight.net", "aiprobability.net", "solanapulse.cc", "aidatacortex.net",
    "signalroute.cc", "logicfield.cc", "aidecisionmap.cc", "nexussignal.cc",
    "globalpulsemarkets.it.com", "alphacapitalmatrix.cc", "datastackhub.cc", "indexlayer.cc",
    "edgemarketspro.it.com", "pulsesignalmatrix.it.com", "financechoice.cc", "systemmesh.cc"
]

# 去重並排序
unique_domains = sorted(list(set(domains)))

print(f"📊 共整理出 {len(unique_domains)} 個唯一域名")
with open('tier1_410.json', 'w') as f:
    json.dump(unique_domains, f, indent=4)
print("✅ 已儲存至 tier1_410.json")