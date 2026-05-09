# app/db/database.py
"""数据库管理模块"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import text
from loguru import logger
from datetime import datetime

from .models import Base, User, UserSession, get_engine
from .config import DATABASE_URL


class DatabaseManager:
    """数据库管理器 - 单例模式"""

    _instance = None
    _engine = None
    _session_local = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._engine = get_engine(DATABASE_URL)
        self._session_local = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)
        self._initialized = True
        self._init_db()

        logger.info("DatabaseManager 初始化完成")

    def _init_db(self):
        """初始化数据库表"""
        try:
            Base.metadata.create_all(bind=self._engine)
            logger.info("数据库表初始化完成")
        except Exception as e:
            logger.error(f"数据库表初始化失败: {e}")
            raise

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self._session_local()

    # ========== 用户管理 ==========

    # app/db/database.py (修改 create_user 方法)

    def create_user(self, username: str, password: str) -> Optional[User]:
        """
        创建新用户
        Returns:
            User: 创建的用户对象，失败返回 None
        """
        db = self.get_session()
        try:
            # 检查用户名是否已存在
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                logger.warning(f"用户名已存在: {username}")
                return None

            user = User(username=username)
            user.set_password(password)  # 使用新的 set_password 方法

            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info(f"用户创建成功: {username}, id={user.id}")
            return user

        except Exception as e:
            db.rollback()
            logger.error(f"创建用户失败: {e}")
            return None
        finally:
            db.close()

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        验证用户
        Returns:
            User: 验证成功返回用户对象，否则返回 None
        """
        db = self.get_session()
        try:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                logger.warning(f"用户不存在: {username}")
                return None

            if not user.verify_password(password):  # 使用新的 verify_password 方法
                logger.warning(f"密码错误: {username}")
                return None

            if not user.is_active:
                logger.warning(f"用户已禁用: {username}")
                return None

            logger.info(f"用户验证成功: {username}")
            return user

        except Exception as e:
            logger.error(f"验证用户失败: {e}")
            return None
        finally:
            db.close()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        db = self.get_session()
        try:
            return db.query(User).filter(User.id == user_id).first()
        finally:
            db.close()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        db = self.get_session()
        try:
            return db.query(User).filter(User.username == username).first()
        finally:
            db.close()

    # ========== 会话管理 ==========

    def associate_session(self, user_id: int, session_id: str) -> bool:
        """
        关联用户与会话
        Returns:
            bool: 是否成功
        """
        db = self.get_session()
        try:
            # 检查是否已存在关联
            existing = db.query(UserSession).filter(
                UserSession.user_id == user_id,
                UserSession.session_id == session_id
            ).first()

            if existing:
                # 更新最后访问时间
                existing.last_accessed = datetime.now()
                db.commit()
                return True

            # 创建新关联
            user_session = UserSession(user_id=user_id, session_id=session_id)
            db.add(user_session)
            db.commit()

            logger.info(f"关联会话: user_id={user_id}, session_id={session_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"关联会话失败: {e}")
            return False
        finally:
            db.close()

    def verify_session_access(self, user_id: int, session_id: str) -> bool:
        """
        验证用户是否有权访问该会话
        Returns:
            bool: 是否有权访问
        """
        if not session_id:
            return False

        db = self.get_session()
        try:
            user_session = db.query(UserSession).filter(
                UserSession.user_id == user_id,
                UserSession.session_id == session_id
            ).first()

            return user_session is not None

        except Exception as e:
            logger.error(f"验证会话访问失败: {e}")
            return False
        finally:
            db.close()

    def get_user_sessions(self, user_id: int) -> List[str]:
        """获取用户的所有会话ID"""
        db = self.get_session()
        try:
            sessions = db.query(UserSession.session_id).filter(
                UserSession.user_id == user_id
            ).order_by(UserSession.last_accessed.desc()).all()

            return [s[0] for s in sessions]

        except Exception as e:
            logger.error(f"获取用户会话失败: {e}")
            return []
        finally:
            db.close()

    def remove_session_association(self, user_id: int, session_id: str) -> bool:
        """移除用户与会话的关联"""
        db = self.get_session()
        try:
            db.query(UserSession).filter(
                UserSession.user_id == user_id,
                UserSession.session_id == session_id
            ).delete()
            db.commit()
            logger.info(f"移除会话关联: user_id={user_id}, session_id={session_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"移除会话关联失败: {e}")
            return False
        finally:
            db.close()


# 全局单例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager