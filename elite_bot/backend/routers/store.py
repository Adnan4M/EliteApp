"""Character/skin store endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.models import AppUser, Skin, UserSkin, UserXp
from database import SessionLocal

router = APIRouter(prefix="/store", tags=["store"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from fastapi import Header
from typing import Optional

from backend.security import decode_token


def _get_token(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return authorization[7:]


def _get_user(token: str = Depends(_get_token), db: Session = Depends(get_db)) -> AppUser:
    uid = decode_token(token)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.get(AppUser, uid)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---- endpoints ------------------------------------------------------------

@router.get("/skins")
def list_skins(
    db: Session = Depends(get_db),
    user: AppUser = Depends(_get_user),
):
    """Return all skins with ownership and active status for current user."""
    owned_ids = {us.skin_id for us in db.query(UserSkin).filter_by(user_id=user.id).all()}
    skins = db.query(Skin).order_by(Skin.sort_order).all()
    return [
        {
            "id": s.id,
            "name_ar": s.name_ar,
            "emoji": s.emoji,
            "bg_color": s.bg_color,
            "price_xp": s.price_xp,
            "gender": s.gender,
            "owned": s.id in owned_ids or s.price_xp == 0,
            "active": s.id == user.active_skin_id,
        }
        for s in skins
    ]


@router.get("/my-skins")
def my_skins(
    db: Session = Depends(get_db),
    user: AppUser = Depends(_get_user),
):
    """Return only skins the user owns (including free defaults)."""
    owned_ids = {us.skin_id for us in db.query(UserSkin).filter_by(user_id=user.id).all()}
    skins = db.query(Skin).order_by(Skin.sort_order).all()
    result = []
    for s in skins:
        if s.price_xp == 0 or s.id in owned_ids:
            result.append({
                "id": s.id,
                "name_ar": s.name_ar,
                "emoji": s.emoji,
                "bg_color": s.bg_color,
                "price_xp": s.price_xp,
                "gender": s.gender,
                "active": s.id == user.active_skin_id,
            })
    return result


@router.post("/buy/{skin_id}")
def buy_skin(
    skin_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(_get_user),
):
    skin = db.get(Skin, skin_id)
    if not skin:
        raise HTTPException(status_code=404, detail="Skin not found")
    if skin.price_xp == 0:
        raise HTTPException(status_code=400, detail="This skin is free")

    # Check not already owned
    existing = db.query(UserSkin).filter_by(user_id=user.id, skin_id=skin_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already owned")

    xp_row = db.query(UserXp).filter_by(user_id=user.id).first()
    current_xp = xp_row.xp if xp_row else 0
    if current_xp < skin.price_xp:
        raise HTTPException(
            status_code=402,
            detail=f"لا يوجد XP كافٍ. تحتاج {skin.price_xp} ولديك {current_xp}",
        )

    # Deduct XP
    if xp_row:
        xp_row.xp -= skin.price_xp
    db.add(UserSkin(user_id=user.id, skin_id=skin_id))
    db.commit()
    return {"ok": True, "xp_remaining": xp_row.xp if xp_row else 0}


@router.post("/equip/{skin_id}")
def equip_skin(
    skin_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(_get_user),
):
    skin = db.get(Skin, skin_id)
    if not skin:
        raise HTTPException(status_code=404, detail="Skin not found")

    # Must own it (or it's free)
    if skin.price_xp > 0:
        owned = db.query(UserSkin).filter_by(user_id=user.id, skin_id=skin_id).first()
        if not owned:
            raise HTTPException(status_code=403, detail="لم تشترِ هذا الشكل بعد")

    user.active_skin_id = skin_id
    db.commit()
    return {"ok": True, "active_skin_id": skin_id}


@router.post("/gender")
def set_gender(
    body: dict,
    db: Session = Depends(get_db),
    user: AppUser = Depends(_get_user),
):
    """Set the user's gender (male / female). Sets default skin if none active."""
    gender = body.get("gender")
    if gender not in ("male", "female"):
        raise HTTPException(status_code=400, detail="gender must be 'male' or 'female'")

    user.gender = gender

    # If no skin equipped yet, auto-equip the gender default
    if not user.active_skin_id:
        default = (
            db.query(Skin)
            .filter(Skin.gender == gender, Skin.price_xp == 0)
            .order_by(Skin.sort_order)
            .first()
        )
        if default:
            user.active_skin_id = default.id

    db.commit()
    return {"ok": True, "gender": user.gender, "active_skin_id": user.active_skin_id}
