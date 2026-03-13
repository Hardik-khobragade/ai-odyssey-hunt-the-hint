# ⚡ Hunt the Hint — FastAPI Version

Marvel/Ultron themed two-round quiz game for AI Odyssey.
Built with FastAPI + native WebSockets. No Flask, no Socket.IO.

---

## 🚀 Quick Start

```bash
pip install -r requirements.txt
python main.py          # dev server at http://localhost:5000
```

**Production (50+ users):**
```bash
uvicorn main:app --host 0.0.0.0 --port 5000 --workers 1
```
> Keep `--workers 1` — WebSocket state is in-memory and not shared across processes.

---

## 📁 Folder Structure

```
hunt-the-hint/
├── main.py               ← FastAPI app (all routes + WebSocket)
├── requirements.txt
├── .env                  ← passwords (don't commit this)
├── data/
│   ├── questions.json    ← edit questions here or via admin UI
│   └── game_state.json   ← auto-created, live game state
├── static/
│   ├── js/
│   │   └── ws.js         ← shared WebSocket client helper
│   └── images/
│       ├── r2_q1.png     ← YOUR Round 2 images go here
│       ├── r2_q2.png
│       └── ...
└── templates/
    ├── base.html
    ├── register.html
    ├── game.html
    ├── leaderboard.html
    ├── admin_login.html
    └── admin.html
```

---

## 🖼️ Image Rendering — Why It's Fast Now

**Root causes of slow image loading and the fixes applied:**

| Problem | Fix |
|---------|-----|
| Images downloaded fresh every page load | `Cache-Control: public, max-age=3600` — browser caches for 1 hour |
| Layout jumps while image loads | CSS skeleton loader holds the space (16:9 ratio reserved) |
| Images load one by one | JavaScript preloads all Round 2 images the moment round starts |
| `loading="lazy"` deferred off-screen images | Changed to `loading="eager"` + `decoding="async"` |
| No visual feedback while loading | Animated shimmer skeleton replaces blank space |

**You don't need a CDN or database for images.** FastAPI's `StaticFiles` serves them
efficiently. Just make sure your PNG/JPG files are reasonably sized:
- Recommended: compress images to **< 500 KB** each using tools like TinyPNG or Squoosh
- Ideal dimensions: 900×500px or similar wide format

---

## 🔑 URLs

| URL | Who uses it |
|-----|------------|
| `/register` | Teams — enter team name |
| `/game` | Teams — active game interface |
| `/leaderboard` | Anyone — show on projector |
| `/admin` | You — control panel |
| `/admin/login` | You — password login |

**Default admin password:** `ultron@admin2024`  
Change in `.env`:
```
ADMIN_PASSWORD=your_password_here
SECRET_KEY=any_random_long_string
```

---

## 🎮 Event Day Flow

1. Start server: `uvicorn main:app --host 0.0.0.0 --port 5000 --workers 1`
2. Open `/admin` on your laptop, `/leaderboard` on projector
3. Tell teams: `http://<your-ip>:5000/register`
4. When everyone's registered → **START ROUND 1**
5. After time's up → **END ROUND** → optionally **REVEAL ANSWERS**
6. → **START ROUND 2** → repeat
7. → **END GAME** → projector shows final rankings

---

## ✏️ Adding Questions

**Via Admin UI** (easiest):
Go to `/admin` → Question Editor tab → add/edit → Save

**Via JSON** (`data/questions.json`):

Round 1:
```json
{ "text": "Tony built an IRON suit to escape.", "answer": "iron", "hint": "Stark's material" }
```

Round 2:
```json
{ "image_url": "/static/images/r2_q1.png", "answer": "arc", "hint": "Look at the energy core" }
```

- `answer` is always **lowercase**
- Matching is **case-insensitive**
- Max **10 questions per round** = max 200 total points