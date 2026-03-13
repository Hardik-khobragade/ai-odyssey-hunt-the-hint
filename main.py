import json
import os
import time
import asyncio
import hmac
import hashlib
import base64
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ultron@admin2024")
SECRET_KEY     = os.getenv("SECRET_KEY",     "ultron-hunt-secret-2024")
DATA_FILE      = "data/game_state.json"
QUESTIONS_FILE = "data/questions.json"
IMAGES_DIR     = "static/images"

# ─── WebSocket Manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections = [c for c in self.connections if c is not ws]

    async def broadcast(self, event: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()
_timer_task: Optional[asyncio.Task] = None

# ─── Auto-freeze background task ─────────────────────────────────────────────
async def auto_freeze_round():
    """Sleeps until round timer expires, then auto-submits all pending teams."""
    state = get_state()
    rn    = state["current_round"]
    dur   = state.get(f"round{rn}_duration", 300)
    start = state.get("round_start_time", time.time())
    remaining = dur - (time.time() - start)
    if remaining > 0:
        await asyncio.sleep(remaining)

    state = get_state()
    # Only act if the round is still active (wasn't manually ended)
    if not state["round_active"] or state["current_round"] != rn:
        return

    questions = get_questions().get(f"round{rn}", [])
    for team_name, t in state["teams"].items():
        done_key = f"round{rn}_done"
        if not t.get(done_key):
            saved_ans = t.get(f"round{rn}_draft", {})
            score = 0
            for i, q in enumerate(questions):
                user_ans = saved_ans.get(str(i), "").strip().lower()
                correct  = q.get("answer", "").strip().lower()
                if user_ans == correct or user_ans == correct.replace(" ", ""):
                    score += 10
            t[done_key]                 = True
            t[f"round{rn}_score"]       = score
            t[f"round{rn}_submit_time"] = time.time()
            t["score"]                  = t.get("round1_score", 0) + t.get("round2_score", 0)

    state["round_active"] = False
    save_state(state)
    await manager.broadcast({"type": "game_event",
                              "data": {"type": "round_ended", "round": rn, "auto": True}})
    await manager.broadcast({"type": "leaderboard_update", "data": build_leaderboard(state)})

def start_timer(app_ref=None):
    global _timer_task
    if _timer_task and not _timer_task.done():
        _timer_task.cancel()
    _timer_task = asyncio.create_task(auto_freeze_round())

# ─── App lifecycle ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    if not os.path.exists(QUESTIONS_FILE):
        save_json(QUESTIONS_FILE, {"round1": [], "round2": []})
    if not os.path.exists(DATA_FILE):
        save_state(default_state())
    else:
        s = get_state()
        if s.get("round_active"):   # resume timer if server restarted mid-round
            start_timer()
    yield
    if _timer_task and not _timer_task.done():
        _timer_task.cancel()

app = FastAPI(lifespan=lifespan)

class ImageCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/static/images/"):
            resp.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        return resp

app.add_middleware(ImageCacheMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Data helpers ─────────────────────────────────────────────────────────────
def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def default_state() -> dict:
    return {
        "current_round": 0, "round_active": False,
        "round_start_time": None,
        "round1_start_time": None, "round2_start_time": None,
        "round1_duration": 300, "round2_duration": 300,
        "round1_revealed": False, "round2_revealed": False,
        "teams": {},
    }

def get_state() -> dict:
    s = load_json(DATA_FILE)
    for k, v in default_state().items():
        s.setdefault(k, v)
    return s

def save_state(s: dict):
    save_json(DATA_FILE, s)

def get_questions() -> dict:
    return load_json(QUESTIONS_FILE)

def build_leaderboard(state: dict) -> dict:
    teams = []
    for name, d in state["teams"].items():
        r1_start = state.get("round1_start_time") or 0
        r2_start = state.get("round2_start_time") or 0
        r1_t = (d.get("round1_submit_time") or 0) - r1_start if d.get("round1_done") else 9_999_999
        r2_t = (d.get("round2_submit_time") or 0) - r2_start if d.get("round2_done") else 9_999_999
        teams.append({
            "name":          name,
            "score":         d.get("score", 0),
            "round1_score":  d.get("round1_score", 0),
            "round2_score":  d.get("round2_score", 0),
            "round1_done":   d.get("round1_done", False),
            "round2_done":   d.get("round2_done", False),
            "round1_time":   round(r1_t, 1) if r1_t < 9_999_999 else None,
            "round2_time":   round(r2_t, 1) if r2_t < 9_999_999 else None,
            "tiebreak":      r1_t + r2_t,
        })
    teams.sort(key=lambda x: (-x["score"], x["tiebreak"]))
    for i, t in enumerate(teams):
        t["rank"] = i + 1

    rn  = state["current_round"]
    dur = state.get(f"round{rn}_duration", 0) if rn in (1, 2) else 0
    start = state.get("round_start_time")
    elapsed   = (time.time() - start) if start and state.get("round_active") else 0
    remaining = max(0, dur - elapsed) if state.get("round_active") else 0

    return {
        "teams": teams,
        "current_round":   state["current_round"],
        "round_active":    state["round_active"],
        "round1_revealed": state.get("round1_revealed", False),
        "round2_revealed": state.get("round2_revealed", False),
        "timer": {
            "duration":   dur,
            "remaining":  round(remaining, 1),
            "start_time": start,
        }
    }

# ─── Cookie auth ──────────────────────────────────────────────────────────────
def _sign(v: str) -> str:
    sig = hmac.new(SECRET_KEY.encode(), v.encode(), hashlib.sha256).digest()
    return v + "." + base64.urlsafe_b64encode(sig).decode()

def _verify(cookie: str) -> Optional[str]:
    if not cookie or "." not in cookie:
        return None
    value, _, sig_b64 = cookie.rpartition(".")
    try:
        sig = base64.urlsafe_b64decode(sig_b64)
        expected = hmac.new(SECRET_KEY.encode(), value.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(sig, expected):
            return value
    except Exception:
        pass
    return None

def set_team_cookie(r: Response, team: str):
    r.set_cookie("team", _sign(team), httponly=True, samesite="lax", max_age=86400)

def get_team(team: Optional[str] = Cookie(default=None)) -> Optional[str]:
    return _verify(team) if team else None

def set_admin_cookie(r: Response):
    r.set_cookie("admin", _sign("1"), httponly=True, samesite="lax", max_age=3600 * 8)

def get_admin(admin: Optional[str] = Cookie(default=None)) -> bool:
    return _verify(admin) == "1" if admin else False

# ─── Pydantic models ──────────────────────────────────────────────────────────
class LoginBody(BaseModel):
    password: str

class RegisterBody(BaseModel):
    team_name: str

class ControlBody(BaseModel):
    action: str
    duration: Optional[int] = None

class SubmitBody(BaseModel):
    round: int
    answers: dict

class DraftBody(BaseModel):
    round: int
    answers: dict

class RemoveTeamBody(BaseModel):
    team: str

class UpdateScoreBody(BaseModel):
    team: str
    round: int
    score: int

# ─── Admin routes ─────────────────────────────────────────────────────────────
@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/register", status_code=302)

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@app.post("/admin/login")
async def admin_login(body: LoginBody, response: Response):
    if body.password == ADMIN_PASSWORD:
        set_admin_cookie(response)
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Invalid password")

@app.get("/admin/logout", response_class=RedirectResponse)
async def admin_logout(response: Response):
    response.delete_cookie("admin")
    return RedirectResponse(url="/admin/login", status_code=302)

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, is_admin: bool = Depends(get_admin)):
    if not is_admin:
        return RedirectResponse(url="/admin/login", status_code=302)
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/admin/state")
async def admin_state_api(is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    state = get_state()
    return {"state": state, "questions": get_questions(), "leaderboard": build_leaderboard(state)}

@app.post("/admin/control")
async def admin_control(body: ControlBody, is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    state  = get_state()
    action = body.action

    if action == "start_round1":
        dur = body.duration or state.get("round1_duration", 300)
        now = time.time()
        state.update({
            "current_round": 1, "round_active": True,
            "round_start_time": now, "round1_start_time": now,
            "round1_duration": dur, "round1_revealed": False,
        })
        save_state(state)
        start_timer()
        await manager.broadcast({"type": "game_event", "data": {
            "type": "round_started", "round": 1,
            "duration": dur, "start_time": now,
        }})

    elif action == "start_round2":
        dur = body.duration or state.get("round2_duration", 300)
        now = time.time()
        state.update({
            "current_round": 2, "round_active": True,
            "round_start_time": now, "round2_start_time": now,
            "round2_duration": dur, "round2_revealed": False,
        })
        save_state(state)
        start_timer()
        await manager.broadcast({"type": "game_event", "data": {
            "type": "round_started", "round": 2,
            "duration": dur, "start_time": now,
        }})

    elif action == "end_round":
        rn = state["current_round"]
        # Auto-submit pending teams with their drafts
        questions = get_questions().get(f"round{rn}", [])
        for tname, t in state["teams"].items():
            dk = f"round{rn}_done"
            if not t.get(dk):
                draft = t.get(f"round{rn}_draft", {})
                score = sum(
                    10 for i, q in enumerate(questions)
                    if (draft.get(str(i), "").strip().lower() in
                        [q.get("answer","").strip().lower(),
                         q.get("answer","").strip().lower().replace(" ","")])
                )
                t[dk] = True
                t[f"round{rn}_score"]       = score
                t[f"round{rn}_submit_time"] = time.time()
                t["score"] = t.get("round1_score", 0) + t.get("round2_score", 0)
        state["round_active"] = False
        save_state(state)
        if _timer_task and not _timer_task.done():
            _timer_task.cancel()
        await manager.broadcast({"type": "game_event",
                                  "data": {"type": "round_ended", "round": rn}})
        await manager.broadcast({"type": "leaderboard_update",
                                  "data": build_leaderboard(state)})

    elif action == "reveal_answers":
        # ✅ BUG FIX: ONLY sets revealed flag — does NOT touch round_active or current_round
        rn = state["current_round"]
        state[f"round{rn}_revealed"] = True
        save_state(state)
        qs = get_questions().get(f"round{rn}", [])
        await manager.broadcast({"type": "game_event", "data": {
            "type": "answers_revealed", "round": rn,
            "answers": [{"id": i, "answer": q.get("answer", "")} for i, q in enumerate(qs)]
        }})

    elif action == "add_time":
        if state["round_active"] and state.get("round_start_time"):
            rn  = state["current_round"]
            new_dur = state.get(f"round{rn}_duration", 300) + 60
            state[f"round{rn}_duration"] = new_dur
            save_state(state)
            start_timer()   # restart with extended duration
            await manager.broadcast({"type": "game_event", "data": {
                "type": "time_added", "round": rn,
                "duration": new_dur, "start_time": state["round_start_time"],
            }})

    elif action == "end_game":
        state.update({"current_round": 3, "round_active": False})
        save_state(state)
        if _timer_task and not _timer_task.done():
            _timer_task.cancel()
        await manager.broadcast({"type": "game_event", "data": {"type": "game_ended"}})

    elif action == "reset_game":
        state = default_state()
        save_state(state)
        if _timer_task and not _timer_task.done():
            _timer_task.cancel()
        await manager.broadcast({"type": "game_event", "data": {"type": "game_reset"}})

    return {"ok": True, "state": get_state(), "leaderboard": build_leaderboard(get_state())}

@app.post("/admin/update_score")
async def admin_update_score(body: UpdateScoreBody, is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    state = get_state()
    if body.team not in state["teams"]:
        raise HTTPException(status_code=404, detail="Team not found")
    t = state["teams"][body.team]
    t[f"round{body.round}_score"] = body.score
    t["score"] = t.get("round1_score", 0) + t.get("round2_score", 0)
    save_state(state)
    await manager.broadcast({"type": "leaderboard_update", "data": build_leaderboard(state)})
    return {"ok": True}

@app.get("/admin/questions")
async def get_questions_api(is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    return get_questions()

@app.post("/admin/questions")
async def save_questions_api(request: Request, is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    data = await request.json()
    save_json(QUESTIONS_FILE, data)
    return {"ok": True}

@app.post("/admin/remove_team")
async def remove_team_api(body: RemoveTeamBody, is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    state = get_state()
    state["teams"].pop(body.team, None)
    save_state(state)
    await manager.broadcast({"type": "leaderboard_update", "data": build_leaderboard(state)})
    return {"ok": True}

@app.get("/admin/images")
async def list_images(is_admin: bool = Depends(get_admin)):
    if not is_admin:
        raise HTTPException(status_code=403)
    exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    files = [f"/static/images/{f}" for f in sorted(os.listdir(IMAGES_DIR))
             if os.path.splitext(f)[1].lower() in exts] if os.path.exists(IMAGES_DIR) else []
    return {"images": files}

# ─── Team routes ──────────────────────────────────────────────────────────────
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(body: RegisterBody, response: Response):
    name = body.team_name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Team name must be at least 2 characters")
    if len(name) > 30:
        raise HTTPException(status_code=400, detail="Team name too long (max 30 chars)")
    state = get_state()
    if name not in state["teams"]:
        state["teams"][name] = {
            "score": 0, "round1_done": False, "round2_done": False,
            "round1_score": 0, "round2_score": 0,
            "round1_draft": {}, "round2_draft": {},
            "registered_at": datetime.now().isoformat(),
        }
        save_state(state)
        await manager.broadcast({"type": "leaderboard_update", "data": build_leaderboard(state)})
    set_team_cookie(response, name)
    return {"ok": True}

@app.get("/game", response_class=HTMLResponse)
async def game_page(request: Request, team: Optional[str] = Depends(get_team)):
    if not team:
        return RedirectResponse(url="/register", status_code=302)
    return templates.TemplateResponse("game.html", {"request": request, "team_name": team})

@app.get("/game/status")
async def game_status(team: Optional[str] = Depends(get_team)):
    if not team:
        raise HTTPException(status_code=401, detail="Not registered")
    state     = get_state()
    questions = get_questions()
    td        = state["teams"].get(team, {})
    rn        = state["current_round"]
    dur       = state.get(f"round{rn}_duration", 0) if rn in (1, 2) else 0
    start     = state.get("round_start_time")
    elapsed   = (time.time() - start) if start and state.get("round_active") else 0
    remaining = max(0, dur - elapsed) if state.get("round_active") else 0

    resp: dict = {
        "current_round":   rn,
        "round_active":    state["round_active"],
        "team":            team,
        "team_data":       td,
        "round1_revealed": state.get("round1_revealed", False),
        "round2_revealed": state.get("round2_revealed", False),
        "timer": {"duration": dur, "remaining": round(remaining, 1), "start_time": start},
    }

    if rn == 1 and not td.get("round1_done"):
        qs = questions.get("round1", [])
        resp["questions"] = [{"id": i, "text": q["text"], "hint": q.get("hint", "")} for i, q in enumerate(qs)]
        resp["draft"] = td.get("round1_draft", {})
    elif rn == 2 and not td.get("round2_done"):
        qs = questions.get("round2", [])
        resp["questions"] = [{"id": i, "image_url": q["image_url"], "hint": q.get("hint", "")} for i, q in enumerate(qs)]
        resp["draft"] = td.get("round2_draft", {})
    return resp

@app.post("/game/draft")
async def save_draft(body: DraftBody, team: Optional[str] = Depends(get_team)):
    """Silently auto-saves answers every few seconds for auto-freeze."""
    if not team:
        raise HTTPException(status_code=401)
    state = get_state()
    rn    = body.round
    if state["current_round"] != rn or not state["round_active"]:
        return {"ok": False}
    t = state["teams"].get(team, {})
    if t.get(f"round{rn}_done"):
        return {"ok": False}
    state["teams"].setdefault(team, {})
    state["teams"][team][f"round{rn}_draft"] = body.answers
    save_state(state)
    return {"ok": True}

@app.post("/game/submit")
async def submit_answers(body: SubmitBody, team: Optional[str] = Depends(get_team)):
    if not team:
        raise HTTPException(status_code=401)
    state = get_state()
    rn    = body.round

    if state["current_round"] != rn:
        raise HTTPException(status_code=400, detail="Wrong round")
    done_key = f"round{rn}_done"
    if state["teams"].get(team, {}).get(done_key):
        raise HTTPException(status_code=400, detail="Already submitted")

    questions = get_questions().get(f"round{rn}", [])
    score, results = 0, []
    for i, q in enumerate(questions):
        user_ans = body.answers.get(str(i), "").strip().lower()
        correct  = q.get("answer", "").strip().lower()
        ok = user_ans == correct or user_ans == correct.replace(" ", "")
        if ok:
            score += 10
        results.append({"id": i, "correct": ok, "answer": correct})

    t = state["teams"].setdefault(team, {"score": 0, "round1_done": False, "round2_done": False,
                                          "round1_score": 0, "round2_score": 0})
    t[done_key]                   = True
    t[f"round{rn}_score"]         = score
    t[f"round{rn}_submit_time"]   = time.time()
    t[f"round{rn}_draft"]         = body.answers
    t["score"]                    = t.get("round1_score", 0) + t.get("round2_score", 0)
    save_state(state)
    await manager.broadcast({"type": "leaderboard_update", "data": build_leaderboard(state)})
    return {"ok": True, "score": score, "results": results, "total": t["score"]}

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    return templates.TemplateResponse("leaderboard.html", {"request": request})

@app.get("/leaderboard/data")
async def leaderboard_data():
    return build_leaderboard(get_state())

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    state = get_state()
    try:
        await ws.send_json({"type": "leaderboard_update", "data": build_leaderboard(state)})
        if state.get("round_active"):
            rn  = state["current_round"]
            dur = state.get(f"round{rn}_duration", 0)
            start = state.get("round_start_time")
            elapsed = (time.time() - start) if start else 0
            await ws.send_json({"type": "game_event", "data": {
                "type": "round_started", "round": rn,
                "duration": dur, "start_time": start,
                "remaining": round(max(0, dur - elapsed), 1),
            }})
        async for _ in ws.iter_json():
            pass
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)