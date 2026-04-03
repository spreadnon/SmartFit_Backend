# db_save.py
import pymysql
import json

def save_to_mysql(user_id, user_data):
    """
    接收数据，写入 MySQL。
    使用项目主数据库 'smartfit' 中的 'search_history' 表。
    """
    conn = None
    cursor = None
    try:
        # 1. 连接到 smartfit 数据库
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password="12345678",
            database="smartfit",  # 统一使用项目数据库
            charset="utf8mb4"
        )
        cursor = conn.cursor()

        # 2. 检查表结构（如果不存在则创建，增加 user_id 关联）
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS search_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            search_str VARCHAR(100) NOT NULL,
            search_respond TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_sql)
        
        # 检查是否需要增加 user_id 字段 (针对已存在的旧表)
        try:
            cursor.execute("SHOW COLUMNS FROM search_history LIKE 'user_id'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE search_history ADD COLUMN user_id INT AFTER id")
        except:
            pass

        # 3. 插入数据
        sql = "INSERT INTO search_history (user_id, search_str, search_respond) VALUES (%s, %s, %s)"
        
        data_list = []
        for d in user_data:
            search_str = d.get("search_str", "")
            search_respond = d.get("search_respond", "")
            
            # 如果 search_respond 是 dict 或 list，转为 JSON 字符串
            if isinstance(search_respond, (dict, list)):
                search_respond = json.dumps(search_respond, ensure_ascii=False)
            
            data_list.append((user_id, search_str, search_respond))
        
        cursor.executemany(sql, data_list)
        conn.commit()
        print(f"✅ 数据已关联用户 {user_id} 保存到 search_history 表中！记录数: {len(data_list)}")

    except Exception as e:
        print(f"❌ 数据库保存失败：{e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_from_mysql(user_id, search_str):
    """
    根据用户 ID 和搜索关键词从 MySQL 中查找最近的响应。
    """
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password="12345678",
            database="smartfit",
            charset="utf8mb4"
        )
        cursor = conn.cursor()
        
        # 查找该用户最近的一条记录
        sql = "SELECT search_respond FROM search_history WHERE user_id = %s AND search_str = %s ORDER BY created_at DESC LIMIT 1"
        cursor.execute(sql, (user_id, search_str))
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                # 将 TEXT/JSON 字符串还原为 Python 字典/列表
                return json.loads(result[0])
            except:
                return result[0]  # 如果不是 JSON，直接返回字符串
        return None

    except Exception as e:
        print(f"⚠️ 数据库查询失败：{e}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
