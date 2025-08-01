from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Security, Form, Request
from sqlalchemy.orm import Session
from app.models.news import News as NewsModel
from app.models.user import User
from app.schemas.news import NewsResponse
from app.database import get_db
from app.core.security import get_current_active_user
from datetime import datetime
import os
from fastapi.security import OAuth2PasswordBearer
from supabase import create_client, Client
from typing import List
import uuid
import logging
from urllib.parse import urljoin
from app.models.user import User as UserModel
from app.models.news import News
import httpx

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def require_admin(
    current_user: User = Security(get_current_active_user, scopes=["admin"])
):
    return current_user

def get_supabase_client(token: str = None) -> Client:
    """Crea y configura el cliente Supabase"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("Supabase URL or KEY not configured")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error"
        )
    
    client = create_client(supabase_url, supabase_key)
    
    if token:
        try:
            # Configura el token de autenticación
            client.postgrest.auth(token)
        except Exception as auth_error:
            logger.error(f"Supabase auth error: {str(auth_error)}")
            raise HTTPException(
                status_code=401,
                detail="Authentication error"
            )
    
    return client

@router.post("/news/", response_model=NewsResponse)
async def create_news(
    title: str = Form(...),
    subtitle: str = Form(...),
    image_description: str = Form(...),
    body: str = Form(...),
    image: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint para crear noticias con imágenes.
    - Sube imágenes a Supabase Storage
    - Almacena metadatos en PostgreSQL
    - Usa autenticación JWT
    """
    # Configuración Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE")
    bucket_name = os.getenv("SUPABASE_BUCKET", "newsimages")

    if not all([supabase_url, supabase_key]):
        raise HTTPException(
            status_code=500,
            detail="Configuración de Supabase incompleta"
        )

    try:
        # 1. Validar imagen
        allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        max_size = 5 * 1024 * 1024  # 5MB
        
        file_content = await image.read()
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Tipo de imagen no soportado. Formatos permitidos: JPEG, PNG, WEBP, GIF"
            )
        if len(file_content) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Imagen demasiado grande. Tamaño máximo: {max_size//(1024*1024)}MB"
            )

        # 2. Generar nombre único para el archivo
        file_ext = os.path.splitext(image.filename)[1].lower() or f".{image.content_type.split('/')[1]}"
        file_name = f"{uuid.uuid4()}{file_ext}"
        file_path = f"news/{file_name}"

        # 3. Subir imagen a Supabase Storage
        try:
            upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{file_path}"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": image.content_type,
                "x-upsert": "true"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    upload_url,
                    content=file_content,
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Error al subir imagen: {error_detail}"
                    )

        except httpx.RequestError as req_error:
            logger.error(f"Error de conexión con Supabase: {str(req_error)}")
            raise HTTPException(
                status_code=503,
                detail="Error al conectar con el servicio de almacenamiento"
            )
        except Exception as upload_error:
            logger.error(f"Error al subir imagen: {str(upload_error)}")
            raise HTTPException(
                status_code=500,
                detail="Error interno al procesar la imagen"
            )

        # 4. Crear registro en base de datos
        image_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{file_path}"
        
        try:
            db_news = News(
                title=title.strip(),
                subtitle=subtitle.strip(),
                image_url=image_url,
                image_description=image_description.strip(),
                body=body.strip(),
                date=datetime.now(),
                user_id=current_user.id  # UUID del usuario
            )
            
            db.add(db_news)
            db.commit()
            db.refresh(db_news)
            
            return db_news
            
        except Exception as db_error:
            db.rollback()
            # Eliminar imagen subida si falla la creación en DB
            try:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f"{supabase_url}/storage/v1/object/{bucket_name}/{file_path}",
                        headers={
                            "Authorization": f"Bearer {supabase_key}",
                            "apikey": supabase_key
                        }
                    )
            except Exception:
                logger.error("No se pudo eliminar la imagen fallida")
            
            logger.error(f"Error en base de datos: {str(db_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Error al guardar la noticia en la base de datos"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor"
        )

@router.put("/news/{news_id}", response_model=NewsResponse)
async def update_news(
    news_id: int,
    title: str = Form(None),
    subtitle: str = Form(None),
    image_description: str = Form(None),
    body: str = Form(None),
    image: UploadFile = File(None),
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Actualiza una noticia existente.
    - Admin puede actualizar cualquier noticia
    - Usuarios normales solo pueden actualizar sus propias noticias
    - Todos los campos son opcionales
    - Permite actualizar la imagen
    """
    # Configuración Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE")
    bucket_name = os.getenv("SUPABASE_BUCKET", "newsimages")

    # Obtener la noticia existente
    db_news = db.query(News).filter(News.id == news_id).first()
    if not db_news:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")

    # Verificar permisos
    if current_user.role != "admin":  # Usamos role (singular) en lugar de roles
        if db_news.user_id != current_user.id:  # Y no es el autor
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para actualizar esta noticia"
            )

    try:
        image_url = db_news.image_url
        
        # Procesar nueva imagen si se proporciona
        if image:
            # Validar imagen
            allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
            max_size = 5 * 1024 * 1024  # 5MB
            
            file_content = await image.read()
            if image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail="Tipo de imagen no soportado"
                )
            if len(file_content) > max_size:
                raise HTTPException(
                    status_code=400,
                    detail="Imagen demasiado grande (máximo 5MB)"
                )

            # Generar nuevo nombre de archivo
            file_ext = os.path.splitext(image.filename)[1].lower() or f".{image.content_type.split('/')[1]}"
            file_name = f"{uuid.uuid4()}{file_ext}"
            file_path = f"news/{file_name}"

            # Subir nueva imagen
            try:
                upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{file_path}"
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": image.content_type,
                    "x-upsert": "true"
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        upload_url,
                        content=file_content,
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=response.status_code,
                            detail="Error al subir nueva imagen"
                        )

                image_url = f"{supabase_url}/storage/v1/object/public/{bucket_name}/{file_path}"
                
                # Eliminar imagen anterior si existe y es diferente
                if db_news.image_url and db_news.image_url != image_url:
                    try:
                        old_file_path = db_news.image_url.split("/object/public/")[1]
                        async with httpx.AsyncClient() as client:
                            await client.delete(
                                f"{supabase_url}/storage/v1/object/{bucket_name}/{old_file_path}",
                                headers={
                                    "Authorization": f"Bearer {supabase_key}",
                                    "apikey": supabase_key
                                }
                            )
                    except Exception:
                        logger.error("No se pudo eliminar la imagen anterior")

            except Exception as upload_error:
                logger.error(f"Error al subir imagen: {str(upload_error)}")
                raise HTTPException(
                    status_code=500,
                    detail="Error al procesar la imagen"
                )

        # Actualizar campos
        update_data = {
            "title": title.strip() if title else db_news.title,
            "subtitle": subtitle.strip() if subtitle else db_news.subtitle,
            "image_url": image_url,
            "image_description": image_description.strip() if image_description else db_news.image_description,
            "body": body.strip() if body else db_news.body
        }

        for key, value in update_data.items():
            setattr(db_news, key, value)

        db.commit()
        db.refresh(db_news)
        
        return db_news

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar noticia: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno al actualizar la noticia"
        )

@router.get("/news/", response_model=List[NewsResponse])
def read_news(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        return db.query(NewsModel).offset(skip).limit(limit).all()
    except Exception as e:
        logger.error(f"Error obteniendo noticias: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al recuperar las noticias"
        )

@router.get("/news/{news_id}", response_model=NewsResponse)
def read_single_news(
    news_id: int,
    db: Session = Depends(get_db)
):
    try:
        news = db.query(NewsModel).filter(NewsModel.id == news_id).first()
        if not news:
            raise HTTPException(status_code=404, detail="Noticia no encontrada")
        return news
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error obteniendo noticia {news_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al recuperar la noticia"
        )

@router.delete("/news/{news_id}")
def delete_news(
    news_id: int,
    current_user: User = Depends(require_admin),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        # Obtener la noticia
        db_news = db.query(NewsModel).filter(NewsModel.id == news_id).first()
        if not db_news:
            raise HTTPException(status_code=404, detail="Noticia no encontrada")
        
        # Configurar Supabase
        supabase = get_supabase_client(token)
        bucket_name = os.getenv("SUPABASE_BUCKET", "newsimages")
        
        # Eliminar imagen de Supabase Storage si existe
        if db_news.image_url:
            try:
                # Extraer path del URL
                storage_prefix = f"{os.getenv('SUPABASE_URL')}/storage/v1/object/public/{bucket_name}/"
                if db_news.image_url.startswith(storage_prefix):
                    file_path = db_news.image_url[len(storage_prefix):]
                    supabase.storage.from_(bucket_name).remove([file_path])
            except Exception as storage_error:
                logger.error(f"Error eliminando imagen: {str(storage_error)}")
                # Continuar aunque falle la eliminación de la imagen
        
        # Eliminar de la base de datos
        db.delete(db_news)
        db.commit()
        
        return {"message": "Noticia eliminada exitosamente"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error eliminando noticia: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error al eliminar la noticia"
        )