from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import Appointment, User
from schemas import AppointmentResponse

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Appointment).filter(Appointment.user_id == user.id).all()
