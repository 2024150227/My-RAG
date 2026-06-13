from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from urllib.parse import quote_plus
from app.config import settings
from app.utils.logger import logger

Base = declarative_base()

class Conversation(Base):
    __tablename__ = 'conversations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_input = Column(Text, nullable=False)
    assistant_output = Column(Text, nullable=False)
    context = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

class MySQLClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connect()
        return cls._instance
    
    def _connect(self):
        try:
            # 密码可能含 @ : / 等特殊字符，必须 URL 编码，否则 SQLAlchemy 解析连接串会出错
            user = quote_plus(settings.MYSQL_USER)
            password = quote_plus(settings.MYSQL_PASSWORD)
            url = (
                f"mysql+pymysql://{user}:{password}"
                f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
            )
            self.engine = create_engine(url, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            logger.info("MySQL连接成功")
        except Exception as e:
            logger.error(f"MySQL连接失败: {str(e)}")
            self.engine = None
    
    def save_conversation(self, session_id: str, user_input: str, assistant_output: str, context: str = None):
        if not self.engine:
            return False
        try:
            session = self.Session()
            conversation = Conversation(
                session_id=session_id,
                user_input=user_input,
                assistant_output=assistant_output,
                context=context
            )
            session.add(conversation)
            session.commit()
            session.close()
            return True
        except Exception as e:
            logger.error(f"MySQL保存失败: {str(e)}")
            return False
    
    def get_conversations(self, session_id: str, limit: int = 100):
        if not self.engine:
            return []
        try:
            session = self.Session()
            conversations = session.query(Conversation)\
                .filter(Conversation.session_id == session_id)\
                .order_by(Conversation.created_at.desc())\
                .limit(limit)\
                .all()
            session.close()
            return [{
                'id': c.id,
                'user_input': c.user_input,
                'assistant_output': c.assistant_output,
                'context': c.context,
                'created_at': c.created_at.isoformat()
            } for c in conversations]
        except Exception as e:
            logger.error(f"MySQL查询失败: {str(e)}")
            return []

mysql_client = MySQLClient()