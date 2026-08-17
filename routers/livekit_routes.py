import os

from fastapi import APIRouter, Depends, Query
from livekit.api import AccessToken, VideoGrants

from dependencies import get_current_user
from models import User

router = APIRouter(tags=["livekit"])

LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
LIVEKIT_URL = os.environ["LIVEKIT_URL"]


@router.get("/token")
def get_token(
    room: str = Query(default="demo"),
    user: User = Depends(get_current_user),
):
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(user.id)
        .with_name(user.email)
        .with_grants(VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    return {"token": token, "url": LIVEKIT_URL}
