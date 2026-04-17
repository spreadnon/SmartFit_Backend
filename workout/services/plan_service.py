"""训练计划业务服务"""
import time
from typing import Dict, Any, Optional, Tuple

from infrastructure.exercise_db import exercise_db
from services.llm_service import llm_service
from services.cache_service import cache_service
from utils.transform import (
    translate_chinese_keys,
    normalize_image_paths,
    parse_injuries_from_input,
    get_avoid_keywords
)
from infrastructure.db.mysql import mysql_client


class PlanService:
    """训练计划生成服务"""
    
    def generate_plan(
        self,
        user_input: str,
        user_profile: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        生成训练计划的主流程
        1. 查缓存 -> 2. 调用LLM -> 3. 补充详情 -> 4. 保存缓存
        """
        start_time = time.perf_counter()
        
        # 1. 解析伤病信息
        injuries = parse_injuries_from_input(user_input)
        avoid_keywords = get_avoid_keywords(injuries)
        
        # 2. 查多级缓存（内存 + Redis + MySQL）
        cached_result, cache_source = self._check_caches(
            user_id, user_input, user_profile
        )
        if cached_result:
            print(f"📌 命中 {cache_source} 缓存")
            normalized = normalize_image_paths(cached_result)
            return self._build_response(200, "训练计划生成成功", normalized)
        
        # 3. 调用LLM生成计划
        try:
            plan_logic = llm_service.generate_plan(
                user_input=user_input,
                user_profile=user_profile,
                exercise_meta=exercise_db.meta,
                injuries=injuries,
                avoid_keywords=avoid_keywords
            )
        except Exception as e:
            print(f"⚠️ LLM调用失败，使用降级方案: {e}")
            plan_logic = llm_service.fallback_plan()
        
        # 4. 补充动作详情
        enriched_plan = self._enrich_plan_with_exercises(plan_logic)
        
        # 5. 转换中文键
        translated_plan = translate_chinese_keys(enriched_plan)
        
        # 6. 保存到各级缓存和数据库
        self._save_to_caches(user_id, user_input, user_profile, translated_plan)
        
        # 7. 最终图片路径归一化
        final_data = normalize_image_paths(translated_plan)
        
        print(f"✅ 总处理耗时: {time.perf_counter() - start_time:.4f}s")
        return self._build_response(200, "训练计划生成成功", final_data)
    
    def _check_caches(
        self,
        user_id: int,
        user_input: str,
        user_profile: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        检查多级缓存
        返回: (数据, 来源: memory/redis/mysql/None)
        """
        # 1. 检查内存 + Redis
        result, source = cache_service.get(user_input, user_profile)
        if result:
            # 同步到MySQL
            self._save_to_mysql(user_id, user_input, result)
            return result, source
        
        # 2. 检查MySQL
        db_result = mysql_client.get_search_history(user_id, user_input)
        if db_result:
            # 同步到内存和Redis
            cache_service.set(user_input, user_profile, db_result)
            return db_result, "mysql"
        
        return None, None
    
    def _save_to_caches(
        self,
        user_id: int,
        user_input: str,
        user_profile: Dict[str, Any],
        data: Dict[str, Any]
    ) -> None:
        """保存到所有缓存层"""
        # 内存 + Redis
        cache_service.set(user_input, user_profile, data)
        
        # MySQL
        self._save_to_mysql(user_id, user_input, data)
    
    def _save_to_mysql(
        self,
        user_id: int,
        user_input: str,
        data: Dict[str, Any]
    ) -> None:
        """保存到MySQL"""
        try:
            mysql_client.save_search_history(user_id, user_input, data)
        except Exception as e:
            print(f"⚠️ MySQL 写入失败: {e}")
    
    def _enrich_plan_with_exercises(self, plan_logic: Dict[str, Any]) -> Dict[str, Any]:
        """补充动作详情"""
        # 获取每日计划列表（兼容中英文Key）
        daily_plans = (
            plan_logic.get("daily_plans") 
            or plan_logic.get("每日计划") 
            or []
        )
        
        for day_plan in daily_plans:
            # 获取动作列表（兼容中英文Key）
            exercise_list = (
                day_plan.get("exercise_list") 
                or day_plan.get("动作列表") 
                or []
            )
            
            for action in exercise_list:
                # 使用ExerciseDB补充详情
                exercise_db.enrich_exercise(action)
        
        return plan_logic
    
    def _build_response(self, code: int, msg: str, data: Any) -> Dict[str, Any]:
        """构建统一响应格式"""
        return {
            "code": code,
            "msg": msg,
            "data": data
        }


# 全局服务实例
plan_service = PlanService()
