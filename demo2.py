# check_redis_keys.py
"""检查 Redis 中的会话数据"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("Redis 会话数据检查")
print("=" * 70)

# 显示配置
print("\n📋 Redis 配置:")
print(f"   REDIS_HOST: {os.getenv('REDIS_HOST', 'localhost')}")
print(f"   REDIS_PORT: {os.getenv('REDIS_PORT', 6379)}")
print(f"   REDIS_DB: {os.getenv('REDIS_DB', 0)}")
print(f"   REDIS_PASSWORD: {'*' * len(os.getenv('REDIS_PASSWORD', '')) if os.getenv('REDIS_PASSWORD') else '(未设置)'}")

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("\n❌ redis 模块未安装")
    sys.exit(1)

if REDIS_AVAILABLE:
    try:
        # 连接 Redis
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True,
            socket_connect_timeout=5
        )

        # 测试连接
        client.ping()
        print("\n✅ Redis 连接成功")

        # ============================================================
        # 1. 查看所有 key
        # ============================================================
        print("\n" + "=" * 70)
        print("1. 所有 Key (KEYS *)")
        print("=" * 70)

        all_keys = client.keys("*")
        print(f"   总数: {len(all_keys)}")

        if all_keys:
            print("\n   Key 列表:")
            for key in sorted(all_keys)[:50]:  # 最多显示 50 个
                # 获取 key 类型
                key_type = client.type(key)
                ttl = client.ttl(key)
                print(f"   - {key} (type={key_type}, ttl={ttl}s)")

            if len(all_keys) > 50:
                print(f"   ... 还有 {len(all_keys) - 50} 个 key 未显示")
        else:
            print("\n   ⚠️ 数据库为空")

        # ============================================================
        # 2. 查看 agent 相关的 key
        # ============================================================
        print("\n" + "=" * 70)
        print("2. Agent 相关 Key (KEYS agent:*)")
        print("=" * 70)

        agent_keys = client.keys("agent:*")
        print(f"   总数: {len(agent_keys)}")

        if agent_keys:
            print("\n   Agent Key 列表:")
            for key in sorted(agent_keys):
                key_type = client.type(key)
                ttl = client.ttl(key)
                print(f"   - {key} (type={key_type}, ttl={ttl}s)")

                # 如果是 hash 类型，显示字段
                if key_type == 'hash':
                    fields = client.hgetall(key)
                    print(f"     字段数: {len(fields)}")
                    # 显示前几个字段
                    for field, value in list(fields.items())[:3]:
                        value_preview = str(value)[:50]
                        print(f"       {field}: {value_preview}...")
                # 如果是 list 类型，显示长度
                elif key_type == 'list':
                    length = client.llen(key)
                    print(f"     长度: {length}")
        else:
            print("\n   ⚠️ 没有找到 agent: 前缀的 key")

        # ============================================================
        # 3. 查看会话元数据
        # ============================================================
        print("\n" + "=" * 70)
        print("3. 会话元数据 Key (KEYS agent:session:meta:*)")
        print("=" * 70)

        meta_keys = client.keys("agent:session:meta:*")
        print(f"   总数: {len(meta_keys)}")

        if meta_keys:
            print("\n   会话元数据列表:")
            for key in sorted(meta_keys):
                session_id = key.replace("agent:session:meta:", "")
                meta = client.hgetall(key)

                print(f"\n   📌 会话: {session_id}")
                print(f"      Key: {key}")
                print(f"      user_id: {meta.get('user_id', 'N/A')}")
                print(f"      turn_count: {meta.get('turn_count', 0)}")
                print(f"      message_count: {meta.get('message_count', 0)}")
                print(f"      created_at: {meta.get('created_at', 'N/A')}")
                if meta.get('created_at'):
                    import time

                    created_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(meta['created_at'])))
                    print(f"      创建时间: {created_time}")
                print(f"      last_accessed: {meta.get('last_accessed', 'N/A')}")

                # 检查对应的会话消息 key
                session_key = f"agent:session:{session_id}"
                if client.exists(session_key):
                    msg_count = client.llen(session_key)
                    print(f"      消息数量: {msg_count}")

                    # 显示前几条消息
                    if msg_count > 0:
                        messages = client.lrange(session_key, 0, 2)
                        print(f"      消息预览:")
                        for i, msg_json in enumerate(messages[:3]):
                            try:
                                import json

                                msg = json.loads(msg_json)
                                print(f"        [{i + 1}] {msg.get('role')}: {msg.get('content', '')[:50]}...")
                            except:
                                print(f"        [{i + 1}] {msg_json[:50]}...")
                else:
                    print(f"      ⚠️ 消息 key 不存在: {session_key}")
        else:
            print("\n   ⚠️ 没有找到会话元数据 key")

        # ============================================================
        # 4. 查看会话消息 key
        # ============================================================
        print("\n" + "=" * 70)
        print("4. 会话消息 Key (KEYS agent:session:*)")
        print("=" * 70)

        session_keys = [k for k in client.keys("agent:session:*")
                        if not k.endswith(":meta:") and ":meta:" not in k]
        print(f"   总数: {len(session_keys)}")

        if session_keys:
            print("\n   会话消息 Key 列表:")
            for key in sorted(session_keys)[:10]:
                msg_count = client.llen(key)
                ttl = client.ttl(key)
                print(f"   - {key} (消息数={msg_count}, ttl={ttl}s)")

        # ============================================================
        # 5. 查找测试会话
        # ============================================================
        print("\n" + "=" * 70)
        print("5. 查找测试会话 (my_test_session_001)")
        print("=" * 70)

        test_session = "my_test_session_001"
        test_meta_key = f"agent:session:meta:{test_session}"
        test_session_key = f"agent:session:{test_session}"

        print(f"   期望的 meta key: {test_meta_key}")
        print(f"   期望的 session key: {test_session_key}")

        if client.exists(test_meta_key):
            print(f"\n   ✅ 会话元数据存在!")
            meta = client.hgetall(test_meta_key)
            print(f"      内容: {meta}")
        else:
            print(f"\n   ❌ 会话元数据不存在!")

        if client.exists(test_session_key):
            print(f"   ✅ 会话消息 key 存在!")
            msg_count = client.llen(test_session_key)
            print(f"      消息数: {msg_count}")

            if msg_count > 0:
                messages = client.lrange(test_session_key, 0, -1)
                print(f"      消息内容:")
                for i, msg_json in enumerate(messages):
                    try:
                        import json

                        msg = json.loads(msg_json)
                        print(f"        [{i + 1}] {msg.get('role')}: {msg.get('content')}")
                    except:
                        print(f"        [{i + 1}] {msg_json}")
        else:
            print(f"   ❌ 会话消息 key 不存在!")

        # ============================================================
        # 6. 测试写入操作
        # ============================================================
        print("\n" + "=" * 70)
        print("6. 测试 Redis 写入操作")
        print("=" * 70)

        test_write_key = "test:write:test_key"
        try:
            # 写入
            client.set(test_write_key, "test_value")
            print(f"   ✅ 写入成功: {test_write_key}")

            # 读取
            value = client.get(test_write_key)
            print(f"   ✅ 读取成功: {value}")

            # 删除
            client.delete(test_write_key)
            print(f"   ✅ 删除成功")

            print("\n   Redis 写入功能正常")
        except Exception as e:
            print(f"   ❌ 写入失败: {e}")

        # ============================================================
        # 总结
        # ============================================================
        print("\n" + "=" * 70)
        print("检查总结")
        print("=" * 70)

        if meta_keys:
            print(f"✅ 发现 {len(meta_keys)} 个会话元数据")
        else:
            print("❌ 没有找到任何会话元数据 - 会话持久化可能未工作")

        if agent_keys:
            print(f"✅ 发现 {len(agent_keys)} 个 agent 相关 key")
        else:
            print("❌ 没有找到任何 agent 相关 key")

        # 关闭连接
        client.close()

    except Exception as e:
        print(f"\n❌ Redis 连接失败: {e}")
        print("\n请检查:")
        print("  1. Redis 服务是否运行: redis-cli ping")
        print("  2. .env 中的 REDIS_HOST 和 REDIS_PORT 是否正确")
        print("  3. 防火墙是否阻止了连接")