import pymysql

# 1. 连接数据库
conn = pymysql.connect(
    host="localhost",
    user="root",         # 你的MySQL用户名
    password="12345678",   # 你的MySQL密码
    database="smartfit",  # 库名
    charset="utf8mb4"
)
cursor = conn.cursor()

# ======================
# 2. 写入 user 表
# ======================
user_sql = """
INSERT INTO user (nick_name, sex)
VALUES (%s, %s)
"""
user_data = [
    ("张三", 0),
    ("李四", 1),
    ("王五", 0)
]
# 批量插入
cursor.executemany(user_sql, user_data)
conn.commit()
print("用户表写入完成")

# 获取刚插入的用户ID（用于关联订单）
cursor.execute("SELECT id FROM user WHERE nick_name='张三'")
user_id = cursor.fetchone()[0]
print(f"用户ID: {user_id}")

# # ======================
# # 3. 写入 order 表（关联 user）
# # ======================
# order_sql = """
# INSERT INTO `order` (user_id, goods, price)
# VALUES (%s, %s, %s)
# """
# order_data = [
#     (user_id, "手机", 2999.00),
#     (user_id, "耳机", 399.00)
# ]

# cursor.executemany(order_sql, order_data)
# conn.commit()
# print("订单表写入完成，已关联用户ID")

# # ======================
# # 4. 关联查询验证
# # ======================
# join_sql = """
# SELECT u.name, o.goods, o.price
# FROM user u
# LEFT JOIN `order` o ON u.id = o.user_id
# """
# cursor.execute(join_sql)
# for row in cursor.fetchall():
#     print(row)

# 关闭
cursor.close()
conn.close()