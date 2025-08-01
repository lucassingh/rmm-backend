from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100))
    subtitle = Column(String(200))
    image_url = Column(String(200))
    image_description = Column(String(200))
    body = Column(Text)
    date = Column(DateTime)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))