# Bubble Tea Vocab Café — Cross-Device Cloud Login (v13)

A full Year 4–6 UASA word-completion game with online student accounts, **without student email addresses**.

## What students see

- Register **Student ID** (e.g., `class6a001`) and **6–8 digit PIN**. No email is requested.
- Choose Shop Manager name, Shop Name, character and year only the first time.
- Log in from **the same hosted game URL** on a different computer, tablet or phone.
- Resume Study Tracker, Easy / Medium / Hard, high scores, Coins, unlocked teas, Weak Words, and English Certificate.
- `☁️ Saved` confirms cloud sync. `⚠️ Not synced` means their latest changes are not yet uploaded.
- Student ID is not case sensitive. PIN is stored **only as a salted PBKDF2-SHA256 hash** on the server. No PIN is stored in the browser.

## What you need to activate cross-device access

A web server with **HTTPS** and **persistent database storage**. The HTML file alone cannot synchronize across devices. This zip contains the actual Python backend, database schema, and game client.

### 1. Test locally on a computer

Python 3.10+:

```bash
cd boba_cloud_v13
python -m pip install -r requirements.txt
# Windows PowerShell: $env:BOBA_COOKIE_SECURE="false"
# macOS/Linux: export BOBA_COOKIE_SECURE=false
uvicorn server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 on that computer. Local test accounts will be written to `data/boba_cloud.sqlite3`.

For local LAN testing on different devices, bind to `0.0.0.0` and open the computer's LAN IP. **Do not expose plain HTTP to the public Internet.**

### 2. Deploy online

The project has a `Dockerfile` compatible with many Docker hosting services or a VPS.

#### Deploy to Render

The included `render.yaml` configures a Docker web service with a persistent 1 GB disk mounted at `/data`. Push this project to a GitHub repository, connect that repository in Render, and create a Blueprint from `render.yaml`. Keep the service on a paid plan that supports persistent disks; Render's free web services do not provide persistent disks. The Blueprint sets `BOBA_DATA_DIR=/data` and enables secure cookies for HTTPS.

- Deploy the project as a **web service**, with one application instance (SQLite isn't designed to share a database file across replicas).
- Attach a **persistent storage volume mounted at `/data`**. Set environment variable `BOBA_DATA_DIR=/data`.
- Set `BOBA_COOKIE_SECURE=true`, and use **HTTPS**. Your host must route traffic to application port `8000`, or set environment variable `PORT` to its assigned port.
- Keep the app running. Do not store the database on an ephemeral container filesystem.
- Open `https://YOUR-GAME-DOMAIN/` from all student devices. They will all use that server database.

**Important:** Hosting providers may charge for persistent storage. If a hosting service does not support a persistent disk, this SQLite deployment is not suitable for live use as students could lose progress after a restart. A PostgreSQL deployment is an alternative, but is not included in this version.

### 3. PIN forgotten?

No email reset is needed. The teacher/server administrator can run:

```bash
python reset_student_pin.py class6a001
```

Enter and confirm a new 6–8 digit PIN when prompted. Never send PINs over class group chats. Students should keep their credentials private.

### 4. Old version local saves

- A student using the *same browser* and Student ID as v12 will be asked, **on initial cloud account creation**, whether to import that student's previous local progress.
- Use `Download Backup` / `Import Backup` to transfer a supported JSON backup into the logged-in cloud account when required. Imports merge completed achievements rather than automatically erasing them.
- Older browser-only profiles are **not automatically available on different devices** until imported/synced.

### 5. Student-data precautions

- Student accounts need **no email**. Use a class code or pseudonymous Student ID rather than a child's full legal name in the account identifier.
- Personalize certificate names only as needed. Keep the server and database access restricted to authorized teachers/administrators.
- Back up `/data/boba_cloud.sqlite3` regularly. The server retains learning progress across sessions; account deletion/data retention policies must be decided and operated by the school.
- Login PINs are rate-limited, salted and hashed. This is a starter educational project and still requires normal security review and hosting configuration before broad public deployment.

## Student features preserved

- Year 4 **UNIT** 1–10, Year 5 Unit 1–8, Year 6 Unit 1–10.
- Study: Chinese meaning, illustration/icon, phonetic, audio and example.
- Easy: remove 2–3 letters; tapping an already selected letter again removes it.
- Medium: enter 3–4 missing letters.
- Hard: English description + first letter and one space per remaining letter; **no pronunciation, audio, Chinese or picture clues**.
- Earn Coins only on first passing of each level: Easy 40, Medium 60, Hard 100; pass >= 12/15. No earning Coins by selling drinks.
- Coins unlock 18 drinks; collecting them all awards a themed **English** operating certificate with manager, shop and date.
- Course Progress separated by Year and Unit with stage status.
- Café BGM and button click audio.

## Technical notes

API paths: `POST /api/register`, `POST /api/login`, `GET /api/me`, `PUT /api/progress`, `POST /api/logout`, `GET /api/health`.

- Per-user cookie sessions are HttpOnly, SameSite=Lax and Secure on HTTPS (set via environment variable).
- Save requests use optimistic versions. When two devices save simultaneously the client merges progress and retries rather than silently overwriting new level completions.
- Cloud sync requires Internet. A browser-side unsynced draft is retained and retried when that browser connects again.
- The game client is `static/index.html` and **must be served through the server**. Opening `static/index.html` as a file is not a cloud login.

### Files

- `static/index.html` – full playable game and cloud-login UI.
- `server.py` – account authentication, sessions, save API, SQLite data persistence.
- `reset_student_pin.py` – teacher/admin PIN reset from server console.
- `Dockerfile`, `docker-compose.yml`, `requirements.txt` – run/deploy configuration.
