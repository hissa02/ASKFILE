from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv
import logging

# Google Auth imports
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
import google.auth.exceptions

load_dotenv()

# Configurações
SECRET_KEY = os.getenv("SECRET_KEY", "bM613IFEBDOdAoputAckOOEh-rTwZSs932aAoyw2YfU")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

logger = logging.getLogger(__name__)

# Configuração de criptografia
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

router = APIRouter()

# Modelos Pydantic
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None

class GoogleLoginRequest(BaseModel):
    google_token: str
    google_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: Optional[bool] = None

# Banco de dados em memória (para o AskFile simples)
users_db = {
    "admin@askfile.com": {
        "id": 1,
        "name": "Admin AskFile",
        "email": "admin@askfile.com",
        "hashed_password": pwd_context.hash("admin123"),
        "created_at": datetime.now()
    },
    "demo@askfile.com": {
        "id": 2,
        "name": "Usuário Demo",
        "email": "demo@askfile.com", 
        "hashed_password": pwd_context.hash("demo123"),
        "created_at": datetime.now()
    }
}

next_user_id = 3

# Funções auxiliares
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(email: str):
    return users_db.get(email)

def authenticate_user(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = get_user_by_email(email=token_data.email)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    return current_user

# Endpoints
@router.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate):
    if get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já está registrado"
        )
    
    if len(user_data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve ter pelo menos 6 caracteres"
        )
    
    if len(user_data.name.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O nome deve ter pelo menos 2 caracteres"
        )
    
    global next_user_id
    
    new_user = {
        "id": next_user_id,
        "name": user_data.name.strip(),
        "email": user_data.email.lower(),
        "hashed_password": get_password_hash(user_data.password),
        "created_at": datetime.now()
    }
    
    users_db[user_data.email.lower()] = new_user
    next_user_id += 1
    
    logger.info(f"Novo usuário registrado: {user_data.email}")
    
    return UserResponse(
        id=new_user["id"],
        name=new_user["name"],
        email=new_user["email"],
        created_at=new_user["created_at"]
    )

@router.post("/", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username.lower(), form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    logger.info(f"Login realizado: {user['email']}")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            created_at=user["created_at"]
        )
    )

@router.post("/google", response_model=Token)
async def google_login(google_data: GoogleLoginRequest):
    try:
        GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        
        if not GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth não configurado"
            )
        
        try:
            idinfo = id_token.verify_oauth2_token(
                google_data.google_token, 
                google_requests.Request(), 
                GOOGLE_CLIENT_ID
            )
            
            google_email = idinfo.get('email')
            google_name = idinfo.get('name')
            google_user_id = idinfo.get('sub')
            
            if not google_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email não fornecido pelo Google"
                )
            
        except Exception as e:
            logger.error(f"Erro na verificação do token Google: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token do Google inválido"
            )
        
        user = get_user_by_email(google_email)
        
        if not user:
            global next_user_id
            user = {
                "id": next_user_id,
                "name": google_name or google_email.split('@')[0],
                "email": google_email,
                "hashed_password": get_password_hash(f"google_auth_{google_user_id}"),
                "created_at": datetime.now(),
                "google_id": google_user_id
            }
            users_db[google_email] = user
            next_user_id += 1
            logger.info(f"Novo usuário criado via Google: {google_email}")
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, expires_delta=access_token_expires
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse(
                id=user["id"],
                name=user["name"],
                email=user["email"],
                created_at=user["created_at"]
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no login Google: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no login com Google"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    return UserResponse(
        id=current_user["id"],
        name=current_user["name"],
        email=current_user["email"],
        created_at=current_user["created_at"]
    )