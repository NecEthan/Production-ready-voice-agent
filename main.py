import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

load_dotenv()

from database import Base, engine
from observability import setup_tracing
from routers import auth_routes, appointment_routes, livekit_routes

setup_tracing()
SQLAlchemyInstrumentor().instrument(engine=engine)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Peptide Voice Agent API")
FastAPIInstrumentor.instrument_app(app)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_routes.router)
app.include_router(livekit_routes.router)
app.include_router(appointment_routes.router)
