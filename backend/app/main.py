from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.routers import assistant, progress  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_if_empty(db)

app = FastAPI(title="LearnSelfAI")

app.include_router(progress.router)
app.include_router(assistant.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
