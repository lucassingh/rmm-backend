from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User as UserModel, UserRole
from app.schemas.user import (
    UserCreate, 
    User as UserSchema, 
    Token,
)
from app.core.security import get_password_hash, verify_password, create_access_token, verify_token
from app.models.user import User as UserModel 
from fastapi import Depends, HTTPException
from app.core.security import logger

router = APIRouter(tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/register", response_model=UserSchema)
async def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    # Verificar si ya existe en la base de datos local
    db_user = db.query(UserModel).filter(UserModel.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        # Verificar si es el primer usuario (admin automático)
        user_count = db.query(UserModel).count()
        is_first_user = user_count == 0
        
        # Crear usuario en tu base de datos
        hashed_password = get_password_hash(user_data.password)
        
        db_user = UserModel(
            email=user_data.email,
            hashed_password=hashed_password,
            role=UserRole.ADMIN.value if is_first_user else user_data.role.value,
            is_active=True
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {
        "id": str(db_user.id),
        "email": db_user.email,
        "role": db_user.role,
        "is_active": db_user.is_active
    }

    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login", response_model=Token)
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # Buscar usuario en tu base de datos
    user = db.query(UserModel).filter(UserModel.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Crear token JWT sin depender de Supabase Auth
    access_token = create_access_token(
        data={"sub": user.email, "scopes": ["user"] if user.role == UserRole.USER else ["admin", "user"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/verify")
async def verify_token_endpoint(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user = verify_token(token, db)
    
    # Si llegamos aquí, el token es válido
    return {
        "status": "valid",
        "user": {
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }
    }