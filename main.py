from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="CI/CD API")

app.include_router(router)

@app.get("/")
def root():
    return {"message": "CI/CD API running 🚀"}