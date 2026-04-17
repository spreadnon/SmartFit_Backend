# db_save.py
import pymysql
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 数据库连接配置
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

def init_db():
    """
    初始化数据库表结构，在服务启动时运行一次即可。
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 创建搜索历史表
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS search_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                search_str VARCHAR(100) NOT NULL,
                search_respond TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_search (user_id, search_str)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(create_table_sql)
            
            # 2. 检查并增加 user_id 字段 (针对已存在的旧表进行增量更新)
            try:
                cursor.execute("SHOW COLUMNS FROM search_history LIKE 'user_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE search_history ADD COLUMN user_id INT AFTER id")
                    print("✅ 已为 search_history 表添加 user_id 字段")
            except Exception as e:
                print(f"⚠️ 字段检查跳过: {e}")
                
            conn.commit()
            print("✅ 数据库环境初始化成功")
    except Exception as e:
        print(f"❌ 数据库初始化失败：{e}")
    finally:
        conn.close()

# 模块加载时执行初始化 (或者在 app 启动时调用)
init_db()

def save_to_mysql(user_id, user_data):
    """
    接收数据，写入 MySQL。
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO search_history (user_id, search_str, search_respond) VALUES (%s, %s, %s)"
            
            data_list = []
            for d in user_data:
                search_str = d.get("search_str", "")
                search_respond = d.get("search_respond", "")
                
                if isinstance(search_respond, (dict, list)):
                    search_respond = json.dumps(search_respond, ensure_ascii=False)
                
                data_list.append((user_id, search_str, search_respond))
            
            cursor.executemany(sql, data_list)
        conn.commit()
        print(f"✅ 成功保存 {len(data_list)} 条搜索记录 (用户 {user_id})")
        return True
    except Exception as e:
        print(f"❌ 数据库保存失败：{e}")
        return False
    finally:
        conn.close()

def get_from_mysql(user_id, search_str):
    """
    根据用户 ID 和搜索关键词从 MySQL 中查找最近的响应。
    """
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 查找该用户最近的一条记录
            sql = "SELECT search_respond FROM search_history WHERE user_id = %s AND search_str = %s ORDER BY created_at DESC LIMIT 1"
            cursor.execute(sql, (user_id, search_str))
            result = cursor.fetchone()
            
            if result:
                # 使用 DictCursor，可以直接通过 key 访问
                respond_val = result.get('search_respond')
                if respond_val:
                    try:
                        return json.loads(respond_val)
                    except:
                        return respond_val
        return None

    except Exception as e:
        print(f"⚠️ 数据库查询失败：{e}")
        return None
    finally:
        conn.close()
