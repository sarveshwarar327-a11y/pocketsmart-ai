# PocketSmart AI: Your Smart Budget & Recommendation Assistant

A GenAI-powered, cross-platform recommendation system that delivers personalized,
budget-based suggestions across three planners — **Home Interior**, **Party Planning**,
and **Jewelry** — using **Google Gemini** for reasoning and (for jewelry) multimodal
image analysis. Recommendations link out to Indian shopping/service platforms
(Amazon, Flipkart, IKEA, Myntra, Ajio, Swiggy, Zomato, BigBasket, BookMyShow,
MakeMyTrip, OYO, NoBroker, BlueStone, Tanishq, Caratlane, Melorra, Meesho).

## Features

- 🔐 **Authentication** — register, login, logout, JWT-based sessions with auto-expiry (30 min inactivity)
- 🏠 **Home Interior Budget Planner** — budget + room/item quantities → AI-generated, itemized furniture/lighting/decor plan with shopping links
- 🎉 **Party Budget Planner** — budget + guest count + event type → catering/decoration/entertainment/venue plan
- 💎 **Jewelry Budget Planner** — budget + occasion + optional outfit photo upload → AI outfit color/style analysis and matching jewelry picks (multimodal)
- 🕓 **Recommendation History** — every generated plan is saved per-user and viewable later
- 💰 All budgets/prices are handled in **INR (₹)**
- 📱 Clean, responsive HTML/CSS/JS frontend (Jinja2 templates), no build step required

## Technology Stack

| Layer      | Technology                                             |
|------------|---------------------------------------------------------|
| Backend    | FastAPI (Python), Uvicorn                                |
| AI Engine  | Google Gemini (`gemini-1.5-flash` via `google-generativeai`) |
| Auth       | JWT (`python-jose`) + `passlib`/bcrypt password hashing  |
| Frontend   | Jinja2 templates, vanilla HTML/CSS/JavaScript             |
| Storage    | JSON-file-backed persistence (`data/users.json`, `data/history.json`) for accounts & recommendation history |

## Requirements / Prerequisites

- Python 3.10+
- A Google AI Studio account and a **Gemini API key** — get one free at
  [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- pip (comes with Python)

## Folder Structure

```
pocketsmart-ai/
├── app.py                 # FastAPI app: routes, auth flow, planner endpoints
├── auth.py                # Password hashing, JWT issuing/validation, sessions
├── gemini_utils.py        # Gemini prompt orchestration + shopping-link builders
├── models.py               # Pydantic request/response schemas
├── database.py             # JSON-file persistence for users & history
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── data/                    # Auto-created: users.json, history.json
├── static/
│   ├── styles.css
│   └── uploads/             # Auto-created: uploaded outfit images
└── templates/
    ├── base.html
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── home_planner.html
    ├── party_planner.html
    ├── jewelry_planner.html
    └── history.html
```

## Installation

### Step 1 — Create the project folder and files
Create a folder named `pocketsmart-ai` and place all the files above inside it,
matching the folder structure exactly (including the `templates/` and `static/`
subfolders).

### Step 2 — Create a virtual environment (recommended)
```bash
cd pocketsmart-ai
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```

## Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env        # macOS/Linux
   copy .env.example .env      # Windows
   ```
2. Get a Gemini API key from [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   (sign in with a Google account → **Get API key** → **Create API key** → copy it).
3. Open `.env` and fill in:
   ```
   GOOGLE_API_KEY=your_actual_gemini_api_key
   GEMINI_MODEL=gemini-1.5-flash
   SECRET_KEY=any_long_random_string
   ```
   Generate a strong `SECRET_KEY` quickly with:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

**Important:** `app.py` (via `gemini_utils.py`) will refuse to start if `GOOGLE_API_KEY`
(or `GEMINI_API_KEY`) is missing — this is intentional, since every planner depends on it.

## Database / Storage Setup

No external database is required. On first run, the app automatically creates a
`data/` folder containing `users.json` (registered accounts) and `history.json`
(saved recommendations). Uploaded outfit images are stored under `static/uploads/`.
Nothing further to configure.

## How to Run

### Step 1 — Activate your virtual environment (if not already active)
```bash
source venv/bin/activate     # macOS/Linux
venv\Scripts\activate        # Windows
```

### Step 2 — Start the backend server
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
or simply:
```bash
python app.py
```

### Step 3 — Open the application
Navigate to **http://127.0.0.1:8000** in your browser. The frontend is served
directly by FastAPI/Jinja2 — there is no separate frontend server to start.

## How to Use the Application

1. Open the home page and click **Get Started** to create an account.
2. Sign in — you'll land on the **Dashboard**.
3. Choose a planner:
   - **Home Budget Planner** — enter your total budget, item quantities, and rooms → **Generate Recommendations**.
   - **Party Budget Planner** — enter budget, guest count, event/venue type, and needs → **Generate Budget Plan**.
   - **Jewelry Budget Planner** — enter budget, occasion, style preferences, and optionally upload an outfit photo → **Get Recommendations**.
4. Each plan shows a budget summary, category-by-category item breakdown with
   estimated prices, and clickable shopping links to relevant platforms.
5. Visit **History** anytime to review or re-open any past recommendation.

## Troubleshooting

| Issue | Likely Cause / Fix |
|---|---|
| `ValueError: No Google/Gemini API key found...` on startup | `.env` is missing or `GOOGLE_API_KEY` isn't set — see **Environment Setup**. |
| `500 Error generating recommendations` | Gemini couldn't produce valid JSON (rate limit, invalid key, or model overload). Check your API key/quota and try again. |
| Login redirects back to `/login` in a loop | Your browser is blocking cookies for `localhost`, or the `SECRET_KEY` changed between requests (restart the server after editing `.env`). |
| `ModuleNotFoundError` for any package | Re-run `pip install -r requirements.txt` inside your active virtual environment. |
| Uploaded jewelry image not analyzed | Confirm the file is a common image format (JPG/PNG) and under a few MB. |
| Port already in use | Run on a different port: `uvicorn app:app --reload --port 8001`. |

## Important Configuration Details

- **JWT tokens** expire after 30 minutes; expired/blacklisted tokens are cleared by a background task every 5 minutes.
- **CORS** is open (`allow_origins=["*"]`) for local development — restrict this to your real frontend origin before deploying publicly.
- **Passwords** are hashed with bcrypt via `passlib` and never stored in plain text.
- **All currency values** are treated as INR (₹) throughout prompts, storage, and the UI.
- Switch models by changing `GEMINI_MODEL` in `.env` (e.g. to `gemini-1.5-pro`) without touching code.
