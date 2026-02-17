from fastapi import FastAPI
from src.routes.auth import router as auth_router


app = FastAPI(title="FleetTrace")

app.include_router(auth_router)