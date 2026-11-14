from fastapi import FastAPI

app = FastAPI(title="Memory Band")


@app.get("/")
def home():
    return {"message": "Memory Band backend is running"}