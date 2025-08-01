from app.database import Base, engine
from app.models.news import News

Base.metadata.create_all(bind=engine)