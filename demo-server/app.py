from fastapi import FastAPI
import os
import socket

app = FastAPI(
    title="KubeTroubleshoot Demo Server",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "application": "KubeTroubleshoot Demo Server",
        "status": "running",
        "hostname": socket.gethostname()
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/info")
def info():
    return {
        "hostname": socket.gethostname(),
        "environment": os.getenv("ENVIRONMENT", "unknown")
    }