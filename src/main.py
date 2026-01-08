from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Collab AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


class Thread(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class Space(BaseModel):
    id: str
    name: str


class FileMeta(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int


class Message(BaseModel):
    id: str
    thread_id: Optional[str] = None
    space_id: Optional[str] = None
    role: Literal["user", "assistant"]
    kind: Literal["text", "file"]
    content: Optional[str] = None
    file: Optional[FileMeta] = None
    created_at: str


class ThreadCreate(BaseModel):
    title: str = Field(..., min_length=1)


class ThreadUpdate(BaseModel):
    title: str = Field(..., min_length=1)


class MessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    kind: Literal["text", "file"]
    content: Optional[str] = None
    file_id: Optional[str] = None


class MessagesCreateRequest(BaseModel):
    thread_id: Optional[str] = None
    space_id: Optional[str] = None
    messages: List[MessageCreate]


threads: Dict[str, Thread] = {}
spaces: Dict[str, Space] = {
    "space-1": Space(id="space-1", name="AI Research"),
    "space-2": Space(id="space-2", name="Docs"),
}
messages_by_thread: Dict[str, List[Message]] = {}
messages_by_space: Dict[str, List[Message]] = {}
files: Dict[str, FileMeta] = {}
file_blobs: Dict[str, bytes] = {}


def sorted_messages(items: List[Message]) -> List[Message]:
    return sorted(items, key=lambda msg: msg.created_at)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/threads")
def list_threads():
    return {"threads": list(threads.values())}


@app.post("/threads")
def create_thread(payload: ThreadCreate):
    thread_id = str(uuid4())
    now = utc_now_iso()
    thread = Thread(id=thread_id, title=payload.title, created_at=now, updated_at=now)
    threads[thread_id] = thread
    return {"thread": thread}


@app.patch("/threads/{thread_id}")
def update_thread(thread_id: str, payload: ThreadUpdate):
    thread = threads.get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread.title = payload.title
    thread.updated_at = utc_now_iso()
    threads[thread_id] = thread
    return {"thread": thread}


@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    threads.pop(thread_id)
    messages_by_thread.pop(thread_id, None)
    return {"ok": True}


@app.get("/spaces")
def list_spaces():
    return {"spaces": list(spaces.values())}


@app.get("/threads/{thread_id}/messages")
def list_thread_messages(thread_id: str):
    if thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = messages_by_thread.get(thread_id, [])
    return {"messages": sorted_messages(messages)}


@app.get("/spaces/{space_id}/messages")
def list_space_messages(space_id: str):
    if space_id not in spaces:
        raise HTTPException(status_code=404, detail="Space not found")
    messages = messages_by_space.get(space_id, [])
    return {"messages": sorted_messages(messages)}


@app.post("/messages")
def create_messages(payload: MessagesCreateRequest):
    if payload.thread_id and payload.space_id:
        raise HTTPException(
            status_code=400, detail="Provide either thread_id or space_id, not both"
        )
    if not payload.thread_id and not payload.space_id:
        raise HTTPException(status_code=400, detail="thread_id or space_id is required")

    if payload.thread_id and payload.thread_id not in threads:
        raise HTTPException(status_code=404, detail="Thread not found")
    if payload.space_id and payload.space_id not in spaces:
        raise HTTPException(status_code=404, detail="Space not found")

    new_messages: List[Message] = []
    for incoming in payload.messages:
        file_meta: Optional[FileMeta] = None
        content: Optional[str] = None
        if incoming.kind == "text":
            if not incoming.content:
                raise HTTPException(status_code=400, detail="Text messages need content")
            content = incoming.content
        if incoming.kind == "file":
            if not incoming.file_id:
                raise HTTPException(status_code=400, detail="File messages need file_id")
            file_meta = files.get(incoming.file_id)
            if not file_meta:
                raise HTTPException(status_code=404, detail="File not found")

        message = Message(
            id=str(uuid4()),
            thread_id=payload.thread_id,
            space_id=payload.space_id,
            role=incoming.role,
            kind=incoming.kind,
            content=content,
            file=file_meta,
            created_at=utc_now_iso(),
        )
        new_messages.append(message)

    has_file = any(msg.kind == "file" for msg in new_messages)
    has_text = any(msg.kind == "text" for msg in new_messages)
    if has_file and has_text:
        new_messages.append(
            Message(
                id=str(uuid4()),
                thread_id=payload.thread_id,
                space_id=payload.space_id,
                role="assistant",
                kind="text",
                content="Got it. I received your files and message.",
                created_at=utc_now_iso(),
            )
        )

    if payload.thread_id:
        messages_by_thread.setdefault(payload.thread_id, []).extend(new_messages)
    if payload.space_id:
        messages_by_space.setdefault(payload.space_id, []).extend(new_messages)

    return {"messages": sorted_messages(new_messages)}


@app.post("/files")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    file_id = str(uuid4())
    meta = FileMeta(
        id=file_id,
        name=file.filename or file_id,
        mime_type=file.content_type or "application/octet-stream",
        size=len(content),
    )
    files[file_id] = meta
    file_blobs[file_id] = content
    return {"file": meta}
