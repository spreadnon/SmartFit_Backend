"""数据转换工具"""
from typing import Any, Dict, List
from core.constants import KEY_MAPPING


def translate_chinese_keys(data: Any) -> Any:
    """递归将中文键转换为英文"""
    if isinstance(data, dict):
        translated = {}
        for k, v in data.items():
            new_key = KEY_MAPPING.get(k, k)
            translated[new_key] = translate_chinese_keys(v)
        return translated
    elif isinstance(data, list):
        return [translate_chinese_keys(item) for item in data]
    return data


def normalize_image_paths(data: Any) -> Any:
    """递归将图片路径中的 '/' 替换为 '_' 并去掉 '.jpg'"""
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == "images" and isinstance(v, list):
                new_dict[k] = [
                    (img.replace("/", "_").replace(".jpg", "") if isinstance(img, str) else img)
                    for img in v
                ]
            else:
                new_dict[k] = normalize_image_paths(v)
        return new_dict
    elif isinstance(data, list):
        return [normalize_image_paths(item) for item in data]
    return data


def parse_injuries_from_input(user_input: str) -> List[str]:
    """从用户输入中解析伤病史"""
    from core.constants import INJURY_AVOID_MAP
    injuries = []
    for injury in INJURY_AVOID_MAP.keys():
        if injury in user_input:
            injuries.append(injury)
    return injuries


def get_avoid_keywords(injuries: List[str]) -> List[str]:
    """获取需要避免的动作关键词"""
    from core.constants import INJURY_AVOID_MAP
    keywords = []
    for injury in injuries:
        keywords.extend(INJURY_AVOID_MAP.get(injury, []))
    return keywords
