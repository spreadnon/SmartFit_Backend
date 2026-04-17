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
    初始化 training 表结构，并执行增量更新。
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

            # 增量更新：添加新字段
            new_columns = {
                "external_id": "VARCHAR(50)",
                "extra_data": "JSON",
                "duration": "INT DEFAULT 0",
                "focus_area": "VARCHAR(100)"
            }
            for col, col_type in new_columns.items():
                try:
                    cursor.execute(f"SHOW COLUMNS FROM training LIKE '{col}'")
                    if not cursor.fetchone():
                        cursor.execute(f"ALTER TABLE training ADD COLUMN {col} {col_type}")
                        # 为 external_id 添加索引以提高查询速度
                        if col == "external_id":
                            cursor.execute("ALTER TABLE training ADD INDEX idx_external_id (external_id)")
                        print(f"✅ 已为 training 表添加字段: {col}")
                except Exception as e:
                    print(f"⚠️ 字段 {col} 检查或添加跳过: {e}")

        conn.commit()
        print("✅ 'training' 数据库环境初始化/检查完成。")
    except Exception as e:
        print(f"❌ 初始化 'training' 表失败: {e}")
    finally:
        conn.close()

# 确保在模块加载时初始化表
init_training_db()

def save_training_data_to_db(user_id: int, training_data: dict):
    """
    保存用户的训练数据到 MySQL 的 'training' 表。
    使用 external_id 或名称+日期进行智能更新（UPSERT）。
    """
    conn = get_db_connection()
    try:
        external_id = training_data.get("external_id")
        exercise_name = training_data.get("exercise_name")
        sets = training_data.get("sets")
        reps = training_data.get("reps")
        duration = training_data.get("duration", 0)
        focus_area = training_data.get("focus_area")
        
        # 处理 extra_data (exercise_sets)
        extra_data = training_data.get("exercise_sets")
        
        # 权重智能提取：如果 top-level weight 为空或 0，则从 sets 详情中抓取第一个有重量的
        weight = training_data.get("weight")
        if (not weight or float(weight) == 0) and isinstance(extra_data, list):
            for s in extra_data:
                # 处理字典或模型对象格式
                s_weight = s.get("weight") if isinstance(s, dict) else getattr(s, "weight", 0)
                if s_weight and float(s_weight) > 0:
                    weight = s_weight
                    break

        if isinstance(extra_data, (list, dict)):
            extra_data = json.dumps(extra_data, ensure_ascii=False)
        
        # 确保 weight 是 float 或 None
        if weight is not None:

            try:
                weight = float(weight)
            except (ValueError, TypeError):
                weight = None

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 寻找现有记录：优先使用 external_id，其次使用名称+日期
            existing_record = None
            if external_id:
                cursor.execute("SELECT id FROM training WHERE external_id = %s LIMIT 1", (external_id,))
                existing_record = cursor.fetchone()
            
            if not existing_record:
                check_sql = """
                SELECT id FROM training 
                WHERE user_id = %s AND exercise_name = %s AND DATE(log_date) = CURDATE()
                LIMIT 1
                """
                cursor.execute(check_sql, (user_id, exercise_name))
                existing_record = cursor.fetchone()

            if existing_record:
                # 2. 如果存在，执行更新
                record_id = existing_record["id"]
                update_sql = """
                UPDATE training 
                SET exercise_name = %s, sets = %s, reps = %s, weight = %s, 
                    extra_data = %s, duration = %s, focus_area = %s, log_date = NOW()
                WHERE id = %s
                """
                cursor.execute(update_sql, (
                    exercise_name, sets, reps, weight, 
                    extra_data, duration, focus_area, record_id
                ))
                print(f"🔄 更新了用户 {user_id} 的训练记录 '{exercise_name}' (ID: {record_id})")

            else:
                # 3. 如果不存在，执行插入
                insert_sql = """
                INSERT INTO training (
                    user_id, external_id, exercise_name, sets, reps, 
                    weight, extra_data, duration, focus_area, log_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(insert_sql, (
                    user_id, external_id, exercise_name, sets, reps, 
                    weight, extra_data, duration, focus_area
                ))
                print(f"✅ 用户 {user_id} 的新训练记录 '{exercise_name}' 已入库")
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ 保存用户 {user_id} 训练数据失败: {e}")
        return False
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
            SELECT id, external_id, exercise_name, sets, reps, weight, 
                   extra_data, duration, focus_area, log_date 
            FROM training 
            WHERE user_id = %s AND DATE(log_date) = %s 
            ORDER BY log_date ASC
            """
            cursor.execute(sql, (user_id, date_str))
            results = cursor.fetchall()
            
            # 数据格式化处理
            for row in results:
                if row["log_date"]:
                    row["log_date"] = row["log_date"].strftime("%Y-%m-%d %H:%M:%S")
                
                # 如果 extra_data 是 JSON 字符串，解析为 Python 对象，方便 API 返回
                if row.get("extra_data") and isinstance(row["extra_data"], str):
                    try:
                        row["extra_data"] = json.loads(row["extra_data"])
                    except:
                        pass
            
            return results
    except Exception as e:
        print(f"❌ 查询用户 {user_id} 在 {date_str} 的训练数据失败: {e}")
        return []
    finally:
        conn.close()



