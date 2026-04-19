import os
import pymysql
import json
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASS", "12345678"),
    "database": os.getenv("DB_NAME", "smartfit"),
    "charset": "utf8mb4"
}


def get_db_connection():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset=DB_CONFIG["charset"]
    )


def init_training_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            create_training_table = """
            CREATE TABLE IF NOT EXISTS training (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                external_id VARCHAR(50),
                exercise_name VARCHAR(255) NOT NULL,
                sets INT NOT NULL,
                reps VARCHAR(50) NOT NULL,
                weight DECIMAL(10, 2),
                extra_data JSON,
                duration INT DEFAULT 0,
                focus_area VARCHAR(100),
                log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_external_id (external_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(create_training_table)
            conn.commit()
            print("✅ 'training' 数据库环境初始化/检查完成。")
    except Exception as e:
        print(f"❌ 初始化 'training' 表失败: {e}")
    finally:
        conn.close()


# Ensure table exists on import
init_training_db()


def save_training_record(user_id: int, training_data: dict):
    conn = get_db_connection()
    try:
        external_id = training_data.get("external_id")
        exercise_name = training_data.get("exercise_name")
        sets = training_data.get("sets")
        reps = training_data.get("reps")
        duration = training_data.get("duration", 0)
        focus_area = training_data.get("focus_area")
        extra_data = training_data.get("exercise_sets")
        weight = training_data.get("weight")

        if isinstance(extra_data, (list, dict)):
            extra_data = json.dumps(extra_data, ensure_ascii=False)

        if weight is not None:
            try:
                weight = float(weight)
            except (ValueError, TypeError):
                weight = None

        success = False
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
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
                success = True
            else:
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
                success = True

        if success:
            conn.commit()
        return success
    except Exception as e:
        print(f"❌ 保存用户 {user_id} 训练数据失败: {e}")
        return False
    finally:
        conn.close()


def fetch_training_records_by_date(user_id: int, date_str: str):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
            SELECT id, external_id, exercise_name, sets, reps, weight,
                   extra_data, duration, focus_area, log_date
            FROM training
            WHERE user_id = %s AND DATE(log_date) = %s
            ORDER BY log_date ASC
            """
            cursor.execute(sql, (user_id, date_str))
            results = cursor.fetchall()
            for row in results:
                if row["log_date"]:
                    row["log_date"] = row["log_date"].strftime("%Y-%m-%d %H:%M:%S")
                if row.get("extra_data") and isinstance(row["extra_data"], str):
                    try:
                        row["extra_data"] = json.loads(row["extra_data"])
                    except Exception:
                        pass
            return results
    except Exception as e:
        print(f"❌ 查询用户 {user_id} 在 {date_str} 的训练数据失败: {e}")
        return []
    finally:
        conn.close()
