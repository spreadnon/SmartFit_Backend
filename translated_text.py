import json
import requests
import os
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import sys
from deep_translator import GoogleTranslator

# 翻译函数：使用 Google 翻译 (通过 deep-translator 库)
def translate_text(text):
    if not isinstance(text, str) or len(text.strip()) == 0:
        return text
    
    # 尝试 3 次重试逻辑
    for _ in range(3):
        try:
            # 使用 GoogleTranslator 引擎
            translated = GoogleTranslator(source='en', target='zh-CN').translate(text)
            if translated:
                # 检查是否包含报错信息 (虽然 Google 报错通常抛出异常，但此处做双重保险)
                if "MYMEMORY WARNING" in str(translated):
                    return text
                return translated
        except Exception as e:
            # print(f"翻译出错: {e}")
            time.sleep(1)
            continue
    return text  # 失败返回原文

# 处理单条数据的包装函数
def task_wrapper(args):
    index, item, translated_map = args
    item_id = item.get("id")
    
    # 优先从 checkpoint 加载
    if item_id in translated_map:
        return index, translated_map[item_id].get("instructionsCN")
    
    # 否则执行翻译
    if "instructions" in item and isinstance(item["instructions"], list):
        if "instructionsCN" not in item or not item["instructionsCN"]:
            cn_instructions = [translate_text(step) for step in item["instructions"]]
            return index, cn_instructions
            
    return index, item.get("instructionsCN")

# ========== 主程序 ==========
if __name__ == "__main__":
    input_file = "free-exercise-db-main/dist/exercises.json"
    output_file = "free-exercise-db-main/dist/exercisesCN.json"
    MAX_WORKERS = 5  # 并发线程数。Google 翻译建议设低一点，避免被识别为爬虫 (5-8 比较稳妥)

    if not os.path.exists(input_file):
        print(f"Error: 找不到输入文件 {input_file}")
        exit(1)
        
    with open(input_file, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # 加载 Checkpoint
    translated_map = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                if isinstance(old_data, list):
                    # 过滤掉包含污染数据的条目 (再次检查)
                    translated_map = {
                        item["id"]: item for item in old_data 
                        if "id" in item and "instructionsCN" in item and 
                        not any("MYMEMORY WARNING" in str(s) for s in item["instructionsCN"])
                    }
            print(f"检测到已有进度，已同步 {len(translated_map)} 条有效翻译结果")
        except Exception as e:
            print(f"读取进度失败: {e}")

    if isinstance(json_data, list):
        total = len(json_data)
        tasks = [(i, item, translated_map) for i, item in enumerate(json_data)]
        
        print(f"开始多线程翻译 (引擎: Google Translate, 并发数: {MAX_WORKERS})...")
        
        save_lock = threading.Lock()
        
        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [executor.submit(task_wrapper, task) for task in tasks]
                
                with tqdm(total=total, desc="翻译总进度") as pbar:
                    for count, future in enumerate(as_completed(futures)):
                        try:
                            idx, cn_instructions = future.result()
                            if cn_instructions:
                                json_data[idx]["instructionsCN"] = cn_instructions
                            
                            pbar.update(1)
                            
                            # 每 50 个保存一次
                            if (count + 1) % 50 == 0:
                                with save_lock:
                                    with open(output_file, "w", encoding="utf-8") as f:
                                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            # 记录单个任务失败，但不中止全局
                            pass
        except KeyboardInterrupt:
            print("\n用户手动停止。")
    
    # 最终保存
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("\n✅ 翻译任务完成！结果已更新至 " + output_file)