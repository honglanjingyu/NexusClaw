# check_db.py
import sys
sys.path.insert(0, '.')

from app.db.config import DATABASE_URL
from app.db.models import Base, get_engine
from app.db.database import get_db_manager

print(f"数据库 URL: {DATABASE_URL}")

# 创建表
engine = get_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)
print("✅ 数据库表创建完成")

# 测试连接
db = get_db_manager()
print("✅ 数据库连接成功")

# 尝试注册一个用户
user = db.create_user("testuser", "test123456")
if user:
    print(f"✅ 测试用户创建成功: {user.username}")
else:
    print("❌ 用户创建失败")