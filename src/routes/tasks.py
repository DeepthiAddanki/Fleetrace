from fastapi import APIRouter



router = APIRouter()

@router.get('/tasks')
def hello():
    return "Hello"