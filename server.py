"""Bubble Tea Vocab Café cloud login: email-free Student ID + PIN.
Host this server with persistent storage and HTTPS for cross-device accounts.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("BOBA_DATA_DIR", str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "boba_cloud.sqlite3"
COOKIE = "boba_student_session"
COOKIE_SECURE = os.environ.get("BOBA_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
SESSION_LIFETIME = 7 * 86400
KDF_ITERATIONS = 320_000
MAX_SAVE_BYTES = 1_500_000
MAX_AUTH_ATTEMPTS = 8
AUTH_WINDOW = 15 * 60
AUTH_LOCK = threading.Lock()
ATTEMPTS: dict[str, list[float]] = {}
app = FastAPI(title="Boba Vocab Cloud Save", docs_url=None, redoc_url=None, openapi_url=None)


def conn():
    db = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    with conn() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS students(
                username TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                progress_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL REFERENCES students(username) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(username);
        """)

init_db()


class AuthData(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    pin: str = Field(min_length=6, max_length=8)


class ProgressData(BaseModel):
    version: int = Field(ge=0)
    state: dict


def valid_username(value: str):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,23}", value))


def student_key(value: str):
    return value.strip().lower()


def check_pin(pin: str):
    return bool(re.fullmatch(r"[0-9]{6,8}", pin))


def pw_hash(pin: str, salt_hex: str):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), KDF_ITERATIONS).hex()


def limit_key(request: Request, username: str):
    # App should be placed behind a trusted HTTPS reverse proxy.
    return (request.client.host if request.client else "unknown") + "|" + username


def is_throttled(key: str):
    with AUTH_LOCK:
        now = time.monotonic()
        old = [t for t in ATTEMPTS.get(key, []) if now-t < AUTH_WINDOW]
        ATTEMPTS[key] = old
        return len(old) >= MAX_AUTH_ATTEMPTS


def fail_attempt(key: str):
    with AUTH_LOCK:
        ATTEMPTS.setdefault(key, []).append(time.monotonic())


def clear_attempts(key: str):
    with AUTH_LOCK:
        ATTEMPTS.pop(key, None)


def set_session(resp: Response, db: sqlite3.Connection, username: str):
    token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    db.execute("INSERT INTO sessions(token_hash,username,expires_at) VALUES(?,?,?)", (token_hash,username,now+SESSION_LIFETIME))
    resp.set_cookie(COOKIE,token,httponly=True,secure=COOKIE_SECURE,samesite="lax",path="/",max_age=SESSION_LIFETIME)


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401,"Please log in")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with conn() as db:
        row = db.execute("""
            SELECT st.username,st.display_name,st.progress_json,st.version
              FROM sessions se JOIN students st ON st.username=se.username
              WHERE se.token_hash=? AND se.expires_at>?
        """, (token_hash,int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401,"Session expired. Please log in again")
    return row


def record(row):
    return {"username":row["username"],"displayName":row["display_name"],
            "state":json.loads(row["progress_json"]),"version":row["version"]}


def default_progress():
    return {"gender":"girl","manager":"","shop":"Bubble Tea Vocab Café","coins":0,
            "current":"Y6U1","progress":{},"unlockedTeas":["classic"],
            "certificate":None,"audio":{"music":True,"sfx":True}}


@app.get("/api/health")
def health():
    return {"ok":True,"mode":"cloud","emailRequired":False}


@app.post("/api/register",status_code=201)
def register(body: AuthData,request: Request,response:Response):
    username = student_key(body.username)
    if not valid_username(body.username.strip()) or not check_pin(body.pin):
        raise HTTPException(400,"Use a 3–24 character Student ID and a 6–8 digit PIN")
    key = limit_key(request,username)
    if is_throttled(key):
        raise HTTPException(429,"Too many attempts. Try again in 15 minutes")
    salt = secrets.token_hex(16)
    saved = default_progress()
    try:
        with conn() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO students(username,display_name,salt,pin_hash,progress_json,created_at) VALUES(?,?,?,?,?,?)",
                       (username,body.username.strip(),salt,pw_hash(body.pin,salt),json.dumps(saved,ensure_ascii=False),int(time.time())))
            set_session(response,db,username)
            db.commit()
    except sqlite3.IntegrityError:
        fail_attempt(key)
        raise HTTPException(409,"Student ID already exists. Please log in")
    clear_attempts(key)
    return {"username":username,"displayName":body.username.strip(),"state":saved,"version":0}


@app.post("/api/login")
def login(body:AuthData,request:Request,response:Response):
    username=student_key(body.username)
    key=limit_key(request,username)
    if is_throttled(key):
        raise HTTPException(429,"Too many attempts. Try again in 15 minutes")
    with conn() as db:
        row=db.execute("SELECT * FROM students WHERE username=?",(username,)).fetchone()
        valid = bool(row and hmac.compare_digest(pw_hash(body.pin,row["salt"]),row["pin_hash"]))
        if not valid:
            fail_attempt(key)
            raise HTTPException(401,"Incorrect Student ID or PIN")
        if row["display_name"] == username:
            db.execute("UPDATE students SET display_name=? WHERE username=?", (body.username.strip(), username))
            row = db.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()
        set_session(response,db,username)
        result=record(row)
    clear_attempts(key)
    return result


@app.get("/api/me")
def me(request:Request):
    return record(current_user(request))


@app.put("/api/progress")
async def progress(body:ProgressData, request:Request):
    me=current_user(request)
    raw=json.dumps(body.state,ensure_ascii=False,separators=(",",":"))
    if len(raw.encode())>MAX_SAVE_BYTES:
        raise HTTPException(413,"Progress file is too large")
    if body.state.get("progress") is None or not isinstance(body.state.get("progress"),dict):
        raise HTTPException(400,"Invalid progress format")
    with conn() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT version,progress_json FROM students WHERE username=?",(me["username"],)).fetchone()
        if body.version!=row["version"]:
            db.rollback()
            return JSONResponse(status_code=409,content={"error":"Version conflict","version":row["version"],"state":json.loads(row["progress_json"])})
        next_version=body.version+1
        db.execute("UPDATE students SET progress_json=?,version=? WHERE username=?",(raw,next_version,me["username"]))
        db.commit()
    return {"saved":True,"version":next_version}


@app.post("/api/logout")
def logout(request:Request,response:Response):
    token=request.cookies.get(COOKIE)
    if token:
        with conn() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE,path="/",secure=COOKIE_SECURE,samesite="lax")
    return {"ok":True}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html",media_type="text/html")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
