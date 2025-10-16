from fastapi import APIRouter

router = APIRouter()

@router.get("/ready")
def ready():
    return {"status": "ok"}

@router.get("/live")
def live():
    return {"status": "ok"}




