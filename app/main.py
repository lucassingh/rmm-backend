from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import news, auth, users  # Cambiado a import relativo
from .database import Base, engine
from fastapi.staticfiles import StaticFiles
import os

# Ruta absoluta para archivos estáticos
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.include_router(auth.router, prefix="/auth")
app.include_router(users.router, prefix="/users")
app.include_router(news.router, prefix="/api")