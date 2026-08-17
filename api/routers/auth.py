from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend import db as models
from backend.db import get_db, write_audit
from backend.security import hash_password, verify_password
from api.dependencies.auth import create_access_token
from api import schemas

router = APIRouter(
    prefix="/auth",
    tags=['Authentication']
)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """注册新用户：邮箱唯一，密码 bcrypt 加密。"""
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册",
        )

    hashed = hash_password(user.password)
    new_user = models.User(email=user.email, password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    write_audit(db, "user_register", user_id=new_user.id, detail=f"新用户 {user.email}")
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """登录：校验邮箱密码，返回 JWT。"""
    user = db.query(models.User).filter(
        models.User.email == user_credentials.username
    ).first()

    if not user or not verify_password(user_credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="邮箱或密码错误",
        )

    access_token = create_access_token(data={"user_id": str(user.id)})
    write_audit(db, "user_login", user_id=user.id, detail=f"用户 {user.email} 登录")
    return {"access_token": access_token, "token_type": "bearer"}
