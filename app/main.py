from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import news, auth, users
from .database import Base, engine
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

load_dotenv()

static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Orígenes base fijos + variables de entorno
base_origins = [
    "https://redmisionesmundiales.org",  # Sin www
    "http://localhost:5173",
]

# Variables de entorno
env_origins = [
    os.getenv("LOCAL_URL"),
    os.getenv("PRODUCTION_URL"), 
    os.getenv("LOCAL_LANDING_URL"),
    os.getenv("PRODUCTION_LANDING_URL"),
    os.getenv("PRODUCTION_REAL_URL"),
]

# Combinar y limpiar
allowed_origins = list(set(
    base_origins + 
    [origin for origin in env_origins if origin is not None]
))

print(f"🌐 Allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.include_router(auth.router, prefix="/auth")
app.include_router(users.router, prefix="/users")
app.include_router(news.router, prefix="/api")