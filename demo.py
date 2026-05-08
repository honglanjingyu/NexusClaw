
# 清空所有会话数据
import redis
r = redis.Redis(host='172.20.48.1', port=6379, db=0, decode_responses=True)
keys = r.keys('agent:session:*')
for key in keys:
    r.delete(key)
    print(f"删除: {key}")
print("所有会话数据已清空")