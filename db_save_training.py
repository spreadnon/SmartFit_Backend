import pymysql
import json
import os

# 从 .env 文件加载数据库配置
from dotenv import load_dotenv
load_dotenv()

# 数据库连接配置 (与 login.py 和 db_save.py 保持一致)
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "12345678",
    "database": "smartfit",
    "charset": "utf8mb4"
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def init_training_db():
    """
    初始化 training 表结构。
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            create_training_table = """
            CREATE TABLE IF NOT EXISTS training (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                exercise_name VARCHAR(255) NOT NULL,
                sets INT NOT NULL,
                reps VARCHAR(50) NOT NULL,
                weight DECIMAL(10, 2),
                log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(create_training_table)
        conn.commit()
        print("✅ 'training' 表初始化或已存在。")
    except Exception as e:
        print(f"❌ 初始化 'training' 表失败: {e}")
    finally:
        conn.close()

def get_training_data_from_db(user_id: int, date_str: str):
    """
    根据用户 ID 和日期查询训练数据。
    date_str 格式应为 'YYYY-MM-DD'。
    """
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 使用 DATE() 函数仅匹配日期部分，忽略时间
            sql = """
            SELECT id, exercise_name, sets, reps, weight, log_date 
            FROM training 
            WHERE user_id = %s AND DATE(log_date) = %s 
            ORDER BY log_date ASC
            """
            cursor.execute(sql, (user_id, date_str))
            results = cursor.fetchall()
            
            # 将 datetime 对象转换为字符串以方便 JSON 序列化
            for row in results:
                if row["log_date"]:
                    row["log_date"] = row["log_date"].strftime("%Y-%m-%d %H:%M:%S")
            
            return results
    except Exception as e:
        print(f"❌ 查询用户 {user_id} 在 {date_str} 的训练数据失败: {e}")
        return []
    finally:
        conn.close()

# 确保在模块加载时初始化表
init_training_db()

def save_training_data_to_db(user_id: int, training_data: dict):
    """
    保存用户的训练数据到 MySQL 的 'training' 表。
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO training (user_id, exercise_name, sets, reps, weight, log_date)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """
            # 确保 weight 是 float 或 None
            weight = training_data.get("weight")
            if weight is not None:
                try:
                    weight = float(weight)
                except ValueError:
                    weight = None # 如果转换失败，设为 None

            cursor.execute(sql, (
                user_id,
                training_data.get("exercise_name"),
                training_data.get("sets"),
                training_data.get("reps"),
                weight
            ))
        conn.commit()
        print(f"✅ 用户 {user_id} 的训练数据 '{training_data.get('exercise_name')}' 已保存。")
        return True
    except Exception as e:
        print(f"❌ 保存用户 {user_id} 训练数据失败: {e}")
        return False
    finally:
        conn.close()
