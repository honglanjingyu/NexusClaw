# demo_test_session_persistence.py
"""
测试 Redis 会话持久化功能
运行: python demo_test_session_persistence.py
"""

import os
import sys
import time
import json
import uuid
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("Redis 会话持久化测试")
print("=" * 70)


# ============================================================
# 测试 1: 检查 Redis 连接
# ============================================================
def demo_test_redis_connection():
    """测试 Redis 连接"""
    print("\n【测试 1】检查 Redis 连接")

    try:
        import redis
        print("  ✅ redis 模块已安装")
    except ImportError:
        print("  ❌ redis 模块未安装，请运行: pip install redis")
        return False

    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True,
            socket_connect_timeout=5
        )
        r.ping()
        print("  ✅ Redis 连接成功")
        print(f"     Host: {os.getenv('REDIS_HOST', 'localhost')}")
        print(f"     Port: {os.getenv('REDIS_PORT', 6379)}")
        print(f"     DB: {os.getenv('REDIS_DB', 0)}")
        return r
    except Exception as e:
        print(f"  ❌ Redis 连接失败: {e}")
        return None


# ============================================================
# 测试 2: 直接使用 Redis 客户端测试会话存储
# ============================================================
def demo_test_redis_direct(redis_client):
    """直接使用 Redis 客户端测试会话存储"""
    print("\n【测试 2】直接使用 Redis 客户端测试会话存储")

    test_session_id = f"test_{uuid.uuid4().hex[:8]}"
    meta_key = f"agent:session:meta:{test_session_id}"
    session_key = f"agent:session:{test_session_id}"

    print(f"  测试会话ID: {test_session_id}")
    print(f"  Meta Key: {meta_key}")
    print(f"  Session Key: {session_key}")

    # 写入元数据
    meta_data = {
        "session_id": test_session_id,
        "user_id": "test_user",
        "created_at": str(time.time()),
        "last_accessed": str(time.time()),
        "turn_count": "0",
        "message_count": "0"
    }

    try:
        # 写入 Hash
        redis_client.hset(meta_key, mapping=meta_data)
        redis_client.expire(meta_key, 3600)
        print("  ✅ 元数据写入成功")

        # 写入消息
        test_message = json.dumps({
            "role": "user",
            "content": "Hello, this is a test message",
            "timestamp": time.time()
        }, ensure_ascii=False)
        redis_client.rpush(session_key, test_message)
        redis_client.expire(session_key, 3600)
        print("  ✅ 消息写入成功")

        # 验证读取
        read_meta = redis_client.hgetall(meta_key)
        print(f"  ✅ 元数据读取成功: {read_meta}")

        read_messages = redis_client.lrange(session_key, 0, -1)
        print(f"  ✅ 消息读取成功: {len(read_messages)} 条")

        return test_session_id
    except Exception as e:
        print(f"  ❌ Redis 操作失败: {e}")
        return None


# ============================================================
# 测试 3: 使用 RedisSessionMemory 类测试
# ============================================================
def demo_test_redis_session_memory():
    """使用 RedisSessionMemory 类测试"""
    print("\n【测试 3】使用 RedisSessionMemory 类测试")

    try:
        from app.memory.redis_session_memory import RedisSessionMemory
    except ImportError as e:
        print(f"  ❌ 导入 RedisSessionMemory 失败: {e}")
        return None

    memory = RedisSessionMemory()
    print("  ✅ RedisSessionMemory 初始化成功")

    # 创建会话
    test_session_id = f"test_{uuid.uuid4().hex[:8]}"
    print(f"  测试会话ID: {test_session_id}")

    # 获取或创建会话
    created_id = memory.get_or_create_session(test_session_id, user_id="test_user")
    print(f"  get_or_create_session 返回: {created_id}")
    print(f"  ID 匹配: {created_id == test_session_id}")

    # 添加消息
    memory.add_message(test_session_id, "user", "这是第一条测试消息")
    memory.add_message(test_session_id, "assistant", "这是第一条回复")
    memory.add_message(test_session_id, "user", "这是第二条测试消息")
    memory.add_message(test_session_id, "assistant", "这是第二条回复")
    print("  ✅ 添加了 4 条消息")

    # 获取会话信息
    info = memory.get_session_info(test_session_id)
    if info:
        print(f"  ✅ 会话信息获取成功")
        print(f"     message_count: {info.get('message_count')}")
        print(f"     turn_count: {info.get('turn_count')}")
    else:
        print(f"  ❌ 会话信息获取失败")
        return None

    # 获取对话历史
    history = memory.get_conversation_history(test_session_id)
    print(f"  ✅ 对话历史获取成功: {len(history)} 条消息")
    for i, msg in enumerate(history):
        print(f"     [{i + 1}] {msg['role']}: {msg['content'][:50]}...")

    return test_session_id


# ============================================================
# 测试 4: 模拟重启（新建实例）
# ============================================================
def demo_test_restart_persistence(original_session_id):
    """模拟重启，测试会话是否持久化"""
    print("\n【测试 4】模拟重启（新建实例）测试持久化")

    try:
        from app.memory.redis_session_memory import RedisSessionMemory
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        return False

    # 创建新实例（模拟重启）
    print("  🔄 创建新的 RedisSessionMemory 实例（模拟重启）...")
    memory2 = RedisSessionMemory()

    # 检查原会话是否存在
    info = memory2.get_session_info(original_session_id)
    if info:
        print(f"  ✅ 重启后会话存在")
        print(f"     message_count: {info.get('message_count')}")
    else:
        print(f"  ❌ 重启后会话不存在")
        return False

    # 获取历史消息
    history = memory2.get_conversation_history(original_session_id)
    print(f"  ✅ 重启后获取到 {len(history)} 条消息")

    for i, msg in enumerate(history):
        print(f"     [{i + 1}] {msg['role']}: {msg['content'][:50]}...")

    # 验证消息数量是否正确
    if len(history) == 4:
        print("  🎉 持久化测试通过！消息数量正确")
        return True
    else:
        print(f"  ❌ 消息数量不正确: 期望 4 条，实际 {len(history)} 条")
        return False


# ============================================================
# 测试 5: URL Session ID 恢复测试
# ============================================================
def demo_test_url_session_recovery():
    """测试使用 URL 中的 session_id 恢复会话"""
    print("\n【测试 5】URL Session ID 恢复测试")

    try:
        from app.memory.redis_session_memory import RedisSessionMemory
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        return False

    memory = RedisSessionMemory()

    # 模拟一个从 URL 获取的 session_id
    url_session_id = f"url_test_{uuid.uuid4().hex[:8]}"
    print(f"  📝 URL 中的 session_id: {url_session_id}")

    # 先创建并添加消息
    created_id = memory.get_or_create_session(url_session_id, user_id="web_user")
    print(f"  get_or_create_session 返回: {created_id}")
    print(f"  ID 匹配: {created_id == url_session_id}")

    # 添加消息
    memory.add_message(url_session_id, "user", "从 URL 恢复的会话消息")
    memory.add_message(url_session_id, "assistant", "这是从 URL 恢复的回复")
    print("  ✅ 消息已添加")

    # 获取历史（模拟从 URL 恢复）
    history = memory.get_conversation_history(url_session_id)
    print(f"  ✅ 通过 URL session_id 获取历史: {len(history)} 条消息")

    # 验证会话信息
    info = memory.get_session_info(url_session_id)
    if info:
        print(f"  ✅ 会话信息: message_count={info.get('message_count')}")
        return True
    else:
        print(f"  ❌ 会话信息获取失败")
        return False


# ============================================================
# 测试 6: 检查 Redis 中的实际数据
# ============================================================
def demo_check_redis_data(redis_client):
    """检查 Redis 中的实际数据"""
    print("\n【测试 6】检查 Redis 中的实际数据")

    # 查找所有 agent:session 相关的 key
    meta_keys = redis_client.keys("agent:session:meta:*")
    session_keys = redis_client.keys("agent:session:*")
    # 过滤掉 meta keys
    session_keys = [k for k in session_keys if ":meta:" not in k]

    print(f"  📊 Redis 中的会话数据:")
    print(f"     元数据 keys: {len(meta_keys)}")
    print(f"     消息 keys: {len(session_keys)}")

    if meta_keys:
        print("\n  会话列表:")
        for key in meta_keys[:5]:  # 最多显示 5 个
            meta = redis_client.hgetall(key)
            session_id = key.replace("agent:session:meta:", "")
            msg_key = f"agent:session:{session_id}"
            msg_count = redis_client.llen(msg_key)
            print(f"     - {session_id}: user={meta.get('user_id')}, messages={msg_count}")

    return len(meta_keys)


# ============================================================
# 测试 7: 清理测试数据
# ============================================================
def demo_cleanup_test_data(redis_client, test_session_ids):
    """清理测试数据"""
    print("\n【测试 7】清理测试数据")

    cleaned = 0
    for session_id in test_session_ids:
        if session_id:
            meta_key = f"agent:session:meta:{session_id}"
            session_key = f"agent:session:{session_id}"

            if redis_client.exists(meta_key):
                redis_client.delete(meta_key)
                cleaned += 1
            if redis_client.exists(session_key):
                redis_client.delete(session_key)
                cleaned += 1

    print(f"  ✅ 清理了 {cleaned} 个测试 key")
    return cleaned


# ============================================================
# 主测试函数
# ============================================================
def demo_run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("开始运行所有测试")
    print("=" * 70)

    test_results = {}
    test_session_ids = []

    # 测试 1: Redis 连接
    redis_client = demo_test_redis_connection()
    test_results['redis_connection'] = redis_client is not None

    if not redis_client:
        print("\n❌ Redis 连接失败，无法继续测试")
        print("   请确保 Redis 服务已启动: docker-compose up -d redis")
        return

    # 测试 2: 直接 Redis 操作
    session_id = demo_test_redis_direct(redis_client)
    test_results['redis_direct'] = session_id is not None
    if session_id:
        test_session_ids.append(session_id)

    # 测试 3: RedisSessionMemory 类
    session_id2 = demo_test_redis_session_memory()
    test_results['redis_session_memory'] = session_id2 is not None
    if session_id2:
        test_session_ids.append(session_id2)

    # 测试 4: 重启持久化
    if session_id2:
        result = demo_test_restart_persistence(session_id2)
        test_results['restart_persistence'] = result
    else:
        test_results['restart_persistence'] = False
        print("\n【测试 4】跳过（需要测试 3 成功）")

    # 测试 5: URL 恢复
    result = demo_test_url_session_recovery()
    test_results['url_recovery'] = result

    # 测试 6: 检查 Redis 数据
    key_count = demo_check_redis_data(redis_client)
    test_results['redis_data'] = key_count > 0

    # 测试 7: 清理数据
    demo_cleanup_test_data(redis_client, test_session_ids)

    # 打印测试结果汇总
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    for test_name, passed in test_results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")

    all_passed = all(test_results.values())
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有测试通过！会话持久化功能正常")
    else:
        print("⚠️ 部分测试失败，请检查上述输出")
    print("=" * 70)


# ============================================================
# 单独测试会话验证接口
# ============================================================
def demo_test_session_verify():
    """测试会话验证接口（需要 API 服务运行）"""
    print("\n【单独测试】会话验证接口测试")
    print("  注意：此测试需要 API 服务运行在 http://localhost:8002")

    import requests

    test_session_id = f"verify_test_{uuid.uuid4().hex[:8]}"
    print(f"  测试会话ID: {test_session_id}")

    # 先创建会话
    try:
        response = requests.get(
            f"http://localhost:8002/api/v1/session/create",
            params={"user_id": "test_user"}
        )
        if response.status_code == 200:
            data = response.json()
            created_id = data.get("session_id")
            print(f"  ✅ 创建会话成功: {created_id}")
            test_session_id = created_id
        else:
            print(f"  ❌ 创建会话失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 创建会话异常: {e}")
        return False

    # 验证会话
    try:
        response = requests.get(
            f"http://localhost:8002/api/v1/session/{test_session_id}/info"
        )
        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ 验证会话响应: {data}")
            if data.get("success") and data.get("info"):
                print(f"  ✅ 会话验证成功")
                return True
            else:
                print(f"  ❌ 会话验证失败: success={data.get('success')}")
                return False
        else:
            print(f"  ❌ 验证会话失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 验证会话异常: {e}")
        return False


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试会话持久化功能")
    parser.add_argument("--verify", action="store_true", help="测试会话验证接口（需要 API 服务）")
    parser.add_argument("--quick", action="store_true", help="快速测试（只测试核心功能）")
    args = parser.parse_args()

    if args.verify:
        demo_test_session_verify()
    elif args.quick:
        # 快速测试：只测试核心功能
        redis_client = demo_test_redis_connection()
        if redis_client:
            session_id = demo_test_redis_session_memory()
            if session_id:
                demo_test_restart_persistence(session_id)
            demo_cleanup_test_data(redis_client, [session_id])
    else:
        demo_run_all_tests()