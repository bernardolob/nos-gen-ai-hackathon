from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List

app = FastAPI()

# Allow frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RejectedVersion(BaseModel):
    attempt: int
    text: str
    reason: str


# In-memory storage for the session
history: List[RejectedVersion] = []
current_attempt = 1


def get_masked_text(attempt_num: int) -> str:
    """
    Simulates the masked text coming from another process/colleague.
    In the future, this function will call the real anonymization module.
    """
    return f"""Admission Report - Lisbon Medical Center (Attempt {attempt_num})
Name: * *
Date of Birth: */*/*
NIF: *
Medical History: The patient * * attended the consultation..."""


@app.get("/api/current")
def get_current():
    return {
        "attempt": current_attempt,
        "text": get_masked_text(current_attempt),
        "history": history,
    }


@app.post("/api/reject")
def reject_version(version: RejectedVersion):
    global current_attempt
    history.append(version)
    current_attempt += 1
    return {
        "attempt": current_attempt,
        "text": get_masked_text(current_attempt),
        "history": history,
    }


@app.post("/api/approve")
def approve_version():
    return {"status": "approved"}


if __name__ == "__main__":
    print("Starting API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
