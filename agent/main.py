from fastapi import FastAPI

app = FastAPI(title="Kobo Agent (placeholder)")


@app.get("/")
def read_root():
    return {"status": "kobo agent placeholder"}
