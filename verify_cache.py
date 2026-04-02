import requests
import json
import time

URL = "http://localhost:8001/generate-plan"
DATA = {
    "user_input": "测试请求：新手，每周3天，想练胸背",
    "user_profile": {"水平": "初级", "器械": "哑铃"}
}

def test_cache():
    print("🚀 正在发起第一次请求（应触发 AI 生成并写入缓存）...")
    start_time = time.time()
    resp1 = requests.post(URL, json=DATA)
    end_time = time.time()
    
    if resp1.status_code == 200:
        print(f"✅ 第一次请求成功，耗时: {end_time - start_time:.2f}s")
        # print("结果示例:", json.dumps(resp1.json(), ensure_ascii=False)[:200], "...")
    else:
        print(f"❌ 第一次请求失败: {resp1.status_code}, {resp1.text}")
        return

    print("\n🚀 正在发起第二次请求（应命中缓存）...")
    start_time = time.time()
    resp2 = requests.post(URL, json=DATA)
    end_time = time.time()

    if resp2.status_code == 200:
        print(f"✅ 第二次请求成功，耗时: {end_time - start_time:.2f}s")
        if end_time - start_time < 0.5:
             print("⚡ 成功命中缓存！(响应时间极短)")
        else:
             print("⚠️ 响应时间较长，可能未命缓存或首次渲染较慢")
    else:
        print(f"❌ 第二次请求失败: {resp2.status_code}, {resp2.text}")

if __name__ == "__main__":
    test_cache()
