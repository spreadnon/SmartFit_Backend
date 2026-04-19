"""MySQL数据库连接与管理"""
import pymysql
import json
from typing import Optional, List, Dict, Any
from workout.core.config import settings


class MySQLClient:
    """MySQL连接管理（单例）"""
    _instance = None
    _initialized = False
    
    # 数据库配置
    DB_CONFIG = {
        "host": getattr(settings, 'DB_HOST', 'localhost'),
        "user": getattr(settings, 'DB_USER', 'root'),
        "password": getattr(settings, 'DB_PASS', '12345678'),
        "database": getattr(settings, 'DB_NAME', 'smartfit'),
        "charset": "utf8mb4"
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _get_connection(self):
        """获取数据库连接"""
        return pymysql.connect(**self.DB_CONFIG)
    
    def init_tables(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                # 创建搜索历史表
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
                
                # 检查并增加 user_id 字段
                try:
                    cursor.execute("SHOW COLUMNS FROM search_history LIKE 'user_id'")
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE search_history ADD COLUMN user_id INT AFTER id")
                        print("✅ 已为 search_history 表添加 user_id 字段")
                except Exception as e:
                    pass
                
                # 创建用户表
                create_users_table = """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    apple_sub VARCHAR(255) NOT NULL UNIQUE,
                    email VARCHAR(255),
                    name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
                cursor.execute(create_users_table)

                # 创建训练日志表
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
                    INDEX idx_user_date (user_id, log_date),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
                cursor.execute(create_training_table)
                
                conn.commit()
                print("✅ 数据库环境初始化成功")
        except Exception as e:
            print(f"❌ 数据库初始化失败：{e}")
        finally:
            conn.close()
    
    def save_search_history(
        self, user_id: int, search_str: str, search_respond: Any
    ) -> bool:
        """保存搜索历史"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO search_history (user_id, search_str, search_respond) VALUES (%s, %s, %s)"
                
                if isinstance(search_respond, (dict, list)):
                    search_respond = json.dumps(search_respond, ensure_ascii=False)
                
                cursor.execute(sql, (user_id, search_str, search_respond))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 数据库保存失败：{e}")
            return False
        finally:
            conn.close()
    
    def get_search_history(
        self, user_id: int, search_str: str
    ) -> Optional[Dict[str, Any]]:
        """根据用户ID和搜索词获取历史记录"""
        conn = self._get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = """SELECT search_respond FROM search_history 
                        WHERE user_id = %s AND search_str = %s 
                        ORDER BY created_at DESC LIMIT 1"""
                cursor.execute(sql, (user_id, search_str))
                result = cursor.fetchone()
                
                if result and result.get('search_respond'):
                    try:
                        return json.loads(result['search_respond'])
                    except:
                        return result['search_respond']
            return None
        except Exception as e:
            print(f"⚠️ 数据库查询失败：{e}")
            return None
        finally:
            conn.close()
    
    def get_user_by_apple_sub(self, apple_sub: str) -> Optional[Dict[str, Any]]:
        """通过Apple sub查询用户"""
        conn = self._get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = "SELECT id, apple_sub, email, name FROM users WHERE apple_sub = %s"
                cursor.execute(sql, (apple_sub,))
                return cursor.fetchone()
        except Exception as e:
            print(f"❌ 查询用户失败: {e}")
            return None
        finally:
            conn.close()
    
    def create_user(self, apple_sub: str, email: str = None, name: str = None) -> Optional[int]:
        """创建新用户"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO users (apple_sub, email, name) VALUES (%s, %s, %s)"
                cursor.execute(sql, (apple_sub, email, name))
                user_id = cursor.lastrowid
            conn.commit()
            return user_id
        except Exception as e:
            print(f"❌ 注册用户失败: {e}")
            return None
        finally:
            conn.close()

    def save_training_record(self, user_id: int, training_data: dict) -> bool:
        """保存单条训练记录（UPSERT：先按 external_id 查，再按当天同名动作查）"""
        conn = self._get_connection()
        try:
            external_id   = training_data.get("external_id")
            exercise_name = training_data.get("exercise_name")
            sets          = training_data.get("sets")
            reps          = training_data.get("reps")
            duration      = training_data.get("duration", 0)
            focus_area    = training_data.get("focus_area")
            extra_data    = training_data.get("exercise_sets")
            weight        = training_data.get("weight")

            if isinstance(extra_data, (list, dict)):
                extra_data = json.dumps(extra_data, ensure_ascii=False)

            if weight is not None:
                try:
                    weight = float(weight)
                except (ValueError, TypeError):
                    weight = None

            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                existing = None

                # 1. 按 external_id 查
                if external_id:
                    cursor.execute(
                        "SELECT id FROM training WHERE external_id = %s LIMIT 1",
                        (external_id,)
                    )
                    existing = cursor.fetchone()

                # 2. 按当天同名动作查
                if not existing:
                    cursor.execute(
                        """SELECT id FROM training
                           WHERE user_id = %s AND exercise_name = %s
                             AND DATE(log_date) = CURDATE()
                           LIMIT 1""",
                        (user_id, exercise_name)
                    )
                    existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """UPDATE training
                           SET exercise_name = %s, sets = %s, reps = %s, weight = %s,
                               extra_data = %s, duration = %s, focus_area = %s, log_date = NOW()
                           WHERE id = %s""",
                        (exercise_name, sets, reps, weight,
                         extra_data, duration, focus_area, existing["id"])
                    )
                else:
                    cursor.execute(
                        """INSERT INTO training
                               (user_id, external_id, exercise_name, sets, reps,
                                weight, extra_data, duration, focus_area, log_date)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                        (user_id, external_id, exercise_name, sets, reps,
                         weight, extra_data, duration, focus_area)
                    )

            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 保存用户 {user_id} 训练数据失败: {e}")
            return False
        finally:
            conn.close()

    def fetch_training_records_by_date(self, user_id: int, date_str: str) -> List[Dict[str, Any]]:
        """查询指定日期的训练记录"""
        conn = self._get_connection()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    """SELECT id, external_id, exercise_name, sets, reps, weight,
                              extra_data, duration, focus_area, log_date
                       FROM training
                       WHERE user_id = %s AND DATE(log_date) = %s
                       ORDER BY log_date ASC""",
                    (user_id, date_str)
                )
                results = cursor.fetchall()
                for row in results:
                    if row.get("log_date"):
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


# 全局MySQL客户端实例
mysql_client = MySQLClient()

# 启动时初始化表
mysql_client.init_tables()


# 兼容旧接口的函数
save_to_mysql = mysql_client.save_search_history
get_from_mysql = mysql_client.get_search_history
get_user_by_apple_sub = mysql_client.get_user_by_apple_sub
create_user = mysql_client.create_user
