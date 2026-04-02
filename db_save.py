# db_save.py
import pymysql
import json

def save_to_mysql(user_data):
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

        # 2. 检查表结构（如果不存在则创建，确保与 smartfit 库中一致）
        # 注意：smartfit 库中已有该表，字段为 id, search_str, search_respond
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS search_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            search_str VARCHAR(100) NOT NULL,
            search_respond TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        cursor.execute(create_table_sql)
        
        # 3. 插入数据
        # 仅插入 search_str，因为此时可能还没有 AI 响应
        sql = "INSERT INTO search_history (search_str,search_respond) VALUES (%s,%s)"
        
        # ✅ 修复：字典不能直接作为 SQL 参数，需序列化为 JSON 字符串
        data_list = []
        for d in user_data:
            search_str = d.get("search_str", "")
            search_respond = d.get("search_respond", "")
            
            # 如果 search_respond 是 dict 或 list，转为 JSON 字符串
            if isinstance(search_respond, (dict, list)):
                search_respond = json.dumps(search_respond, ensure_ascii=False)
            
            data_list.append((search_str, search_respond))
        
        cursor.executemany(sql, data_list)
        conn.commit()
        print(f"✅ 数据已保存到 smartfit 数据库的 search_history 表中！记录数: {len(data_list)}")

    except Exception as e:
        print(f"❌ 数据库保存到 smartfit 失败：{e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
def get_from_mysql(search_str):
    """
    根据搜索关键词从 MySQL 中查找最近的响应。
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
        
        # 查找最近的一条记录
        sql = "SELECT search_respond FROM search_history WHERE search_str = %s ORDER BY created_at DESC LIMIT 1"
        cursor.execute(sql, (search_str,))
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
