import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from auth_utils import create_access_token, hash_password, verify_password
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import LoginRequest, SignupRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,  # set True in production (HTTPS)
    )
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="token", path="/")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
