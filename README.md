# Collab AI Backend

Minimal FastAPI backend for the chat UI, using in-memory storage for threads,
spaces, messages, and files.

## Run

```bash
cd src
uvicorn main:app --reload --port 8000
```

The API enables CORS for `http://localhost:3000`.
