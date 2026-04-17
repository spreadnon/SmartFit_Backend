# core/logger.py
import logging
import logging.handlers
from pathlib import Path


def setup_logger():
    """配置结构化日志"""
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    
    # 配置根日志
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            # 控制台输出
            logging.StreamHandler(),
            # 文件输出（按天轮转）
            logging.handlers.TimedRotatingFileHandler(
                log_dir / "fitness_api.log",
                when="D",
                interval=1,
                backupCount=7,
                encoding="utf-8"
            )
        ]
    )