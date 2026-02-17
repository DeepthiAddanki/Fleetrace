import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


from fastapi import FastAPI
from src.routes.auth import router as auth_router


app = FastAPI(title="FleetTrace")

app.include_router(auth_router)