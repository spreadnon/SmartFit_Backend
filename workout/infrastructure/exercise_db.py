"""ExerciseDB数据加载与管理"""
import json
from typing import List, Dict, Any, Tuple, Optional
from core.constants import EXERCISE_DB_PATH
from core.exceptions import ExerciseDBError


class ExerciseDB:
    """ExerciseDB 管理器（单例）"""
    _instance = None
    _data: List[Dict[str, Any]] = []
    _meta: Dict[str, Any] = {}
    _mapping: Dict[str, Dict[str, Any]] = {}
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance
    
    def _load(self):
        """加载并预处理ExerciseDB数据"""
        if self._initialized:
            return
        
        try:
            with open(EXERCISE_DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not data:
                raise ExerciseDBError("ExerciseDB 文件为空")
            
            # 预处理图片路径
            for exercise in data:
                if "images" in exercise:
                    exercise["images"] = [
                        img.replace("/", "_").replace(".jpg", "")
                        for img in exercise["images"]
                    ]
            
            self._data = data
            self._compute_meta_and_mapping()
            self._initialized = True
            print(f"✅ ExerciseDB 加载成功，共 {len(data)} 条数据")
            
        except Exception as e:
            print(f"❌ 加载 ExerciseDB 失败: {e}")
            self._data = []
            self._meta = {}
            self._mapping = {}
    
    def _compute_meta_and_mapping(self):
        """计算元数据和名称映射"""
        if not self._data:
            return
        
        # 提取元数据
        self._meta = {
            "total_exercises": len(self._data),
            "available_equipment_types": list(set(
                e.get("equipment", "") for e in self._data if e.get("equipment")
            )),
            "difficulty_levels": list(set(
                e.get("level", "") for e in self._data if e.get("level")
            )),
            "target_muscle_groups": list(set(
                ",".join(e.get("primaryMuscles", [])) 
                for e in self._data if e.get("primaryMuscles")
            ))
        }
        
        # 构建名称映射（中英文，去空格归一化）
        for exercise in self._data:
            name_cn = exercise.get("nameCN", "")
            name_en = exercise.get("name", "")
            
            if name_cn:
                self._mapping[name_cn.replace(" ", "")] = exercise
            if name_en:
                self._mapping[name_en.replace(" ", "").lower()] = exercise
    
    @property
    def data(self) -> List[Dict[str, Any]]:
        return self._data
    
    @property
    def meta(self) -> Dict[str, Any]:
        return self._meta
    
    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """通过名称查找动作（支持中英文、归一化匹配）"""
        normalized = name.replace(" ", "").lower()
        
        # 精准匹配
        if normalized in self._mapping:
            return self._mapping[normalized]
        
        # 关键词保底搜索
        if len(normalized) >= 2:
            for key, value in self._mapping.items():
                if normalized in key or key in normalized:
                    return value
        
        return None
    
    def enrich_exercise(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """补充动作详情"""
        # 确保基础结构
        action.setdefault("images", [])
        action.setdefault("primary_muscles", [])
        action.setdefault("instructionsCN", [])
        action.setdefault("secondary_muscles", [])
        action.setdefault("exercise_type", "")
        
        # 获取原始名称
        raw_name = action.get("exercise_name") or action.get("动作名称", "")
        detail = self.find_by_name(raw_name)
        
        if detail:
            action["id"] = detail.get("id", "")
            action["images"] = detail.get("images", [])
            action["instructionsCN"] = detail.get("instructionsCN", [])
            action["secondary_muscles"] = detail.get("secondaryMuscles", [])
            action["exercise_type"] = detail.get("category", "")
            action["primary_muscles"] = detail.get("primaryMuscles", [])
        
        return action


# 全局ExerciseDB实例
exercise_db = ExerciseDB()
