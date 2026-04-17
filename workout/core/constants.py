"""核心业务常量定义"""

# 伤病史→禁忌动作映射表
INJURY_AVOID_MAP = {
    "肩伤": ["肩推", "推肩", "过头推举", "站姿推举", "哑铃肩推", "杠铃肩推", "前平举", "颈后推举"],
    "腰伤": ["硬拉", "早安式", "体前屈", "负重深蹲（大重量）", "山羊挺身（负重）"],
    "膝伤": ["深蹲", "箭步蹲", "保加利亚分腿蹲", "腿举（大重量）", "提踵（负重）"],
    "腕伤": ["俯卧撑", "卧推（窄距）", "哑铃弯举", "杠铃弯举", "农夫行走"],
    "肘伤": ["臂屈伸", "锤式弯举", "三头肌下压（大重量）", "杠铃卧推（宽距）"]
}

# 中英文键映射（用于LLM返回结果转换）
KEY_MAPPING = {
    "训练分化": "training_split",
    "每日计划": "daily_plans",
    "训练日": "training_day",
    "动作列表": "exercise_list",
    "动作名称": "exercise_name",
    "组数": "sets",
    "次数": "reps",
    "顺序": "order",
    "器械": "equipment",
    "难度": "difficulty",
    "次要肌肉": "secondary_muscles",
    "动作类型": "exercise_type",
    "备注": "remark",
    "说明": "instructions",
    "说明CN": "instructionsCN",
    "primaryMuscles": "primary_muscles",
    "id": "id"
}

# 难度等级映射
LEVEL_MAPPING = {
    "新手": "Beginner",
    "中级": "Intermediate",
    "高级": "Expert"
}

# ExerciseDB 文件路径
EXERCISE_DB_PATH = "free-exercise-db-main/dist/exercisesCN.json"

# 缓存配置
CACHE_EXPIRE_HOURS = 24
CACHE_REDIS_TTL_SECONDS = 60 * 60 * 24 * 7  # 7天

# API配置
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
QWEN_MODEL = "qwen-turbo"
