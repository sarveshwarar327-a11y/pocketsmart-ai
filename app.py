"""
app.py
PocketSmart AI - Your Smart Budget & Recommendation Assistant
FastAPI application entry point.
"""
import os
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import (
    FastAPI, HTTPException, Depends, File, UploadFile, Form, Request, status
)
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv

from models import (
    RegisterUser, UserInDB, HomeBudgetInput, PartyBudgetInput, JewelryBudgetInput,
)
import auth
import database
from auth import (
    users_db, blacklisted_tokens, active_sessions,
    get_password_hash, authenticate_user, create_access_token,
    get_token, get_current_active_user, get_optional_user,
    ACCESS_TOKEN_EXPIRE_MINUTES, persist_users,
)
from gemini_utils import (
    get_home_recommendations, get_party_recommendations, get_jewelry_recommendations,
    save_upload_file,
)

# ---------------------------------------------------------------------------
# Environment & app setup
# ---------------------------------------------------------------------------
load_dotenv()

app = FastAPI(title="PocketSmart AI: Your Smart Budget & Recommendation Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory (file-backed) recommendation history: username -> list of dict
user_recommendations: dict = database.load_history()


def save_to_history(username: str, recommendation_type: str, input_data: dict, result: dict) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "username": username,
        "timestamp": datetime.utcnow().isoformat(),
        "recommendation_type": recommendation_type,
        "input_summary": input_data,
        "result_summary": {
            "total_budget": result.get("total_budget"),
            "remaining_budget": result.get("remaining_budget"),
        },
        "full_result": result,
    }
    user_recommendations.setdefault(username, []).append(entry)
    database.save_history(user_recommendations)
    return entry


# ---------------------------------------------------------------------------
# Public / landing pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page introducing PocketSmart AI."""
    user = await get_optional_user(request)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page."""
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("register.html", {"request": request})


# ---------------------------------------------------------------------------
# Auth: register / token / logout
# ---------------------------------------------------------------------------
@app.post("/register")
async def register_user(
    username: str = Form(...),
    email: str = Form(...),
    full_name: Optional[str] = Form(None),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Handle new user registration by accepting and securely storing user credentials."""
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")

    try:
        user_record = RegisterUser(username=username, email=email, full_name=full_name, password=password)
    except Exception:
        raise HTTPException(status_code=400, detail="Please enter a valid email address")

    hashed = get_password_hash(user_record.password)
    users_db[username] = UserInDB(
        username=username, email=email, full_name=full_name, hashed_password=hashed
    ).dict()
    persist_users()

    return RedirectResponse(url="/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get an access token (also used by the login form)."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)

    # Blacklist any previous token for this user, then track the new session
    if user.username in active_sessions:
        old_token = active_sessions[user.username]["token"]
        blacklisted_tokens.add(old_token)
        existing_user_data = active_sessions[user.username].get("user_data", {})
    else:
        existing_user_data = {}

    active_sessions[user.username] = {
        "username": user.username,
        "login_time": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat(),
        "token": access_token,
        "user_data": existing_user_data,
    }

    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout(request: Request):
    """Log out the user by blacklisting their token and clearing the session."""
    token = await get_token(request)

    if token:
        blacklisted_tokens.add(token)
        try:
            from jose import jwt
            payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            username = payload.get("sub")
            if username and username in active_sessions:
                del active_sessions[username]
        except Exception:
            pass

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response


# ---------------------------------------------------------------------------
# Protected pages
# ---------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    recent = sorted(user_recommendations.get(user.username, []), key=lambda x: x["timestamp"], reverse=True)[:5]
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "recent": recent})


@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request):
    """Home budget planner page."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("home_planner.html", {"request": request, "user": user})


@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request):
    """Party budget planner page."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("party_planner.html", {"request": request, "user": user})


@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request):
    """Jewelry budget planner page."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("jewelry_planner.html", {"request": request, "user": user})


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """History page to view past recommendations."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("history.html", {"request": request, "user": user})


# ---------------------------------------------------------------------------
# Planner generation endpoints (protected API routes)
# ---------------------------------------------------------------------------
@app.post("/home-budget")
async def plan_home_budget(
    budget_input: HomeBudgetInput,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate home budget recommendations."""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].setdefault("user_data", {})["last_home_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "requirements": {
                "lights": budget_input.num_lights,
                "fans": budget_input.num_fans,
                "furniture": budget_input.num_furniture,
                "dining_tables": budget_input.num_dining_tables,
            },
        }

    result = get_home_recommendations(budget_input)

    save_to_history(
        username=current_user.username,
        recommendation_type="home",
        input_data=budget_input.dict(),
        result=result,
    )
    return result


@app.post("/party-budget")
async def plan_party_budget(
    budget_input: PartyBudgetInput,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate party budget recommendations."""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].setdefault("user_data", {})["last_party_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "party_type": budget_input.party_type,
            "guests": budget_input.num_guests,
        }

    result = get_party_recommendations(budget_input)

    save_to_history(
        username=current_user.username,
        recommendation_type="party",
        input_data=budget_input.dict(),
        result=result,
    )
    return result


@app.post("/jewelry-budget")
async def plan_jewelry_budget(
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate jewelry budget recommendations with an optional outfit image."""
    budget_input = JewelryBudgetInput(
        total_budget=total_budget, occasion=occasion, preferences=preferences
    )

    image_path = None
    if image and image.filename:
        image_path = save_upload_file(image)

    if current_user.username in active_sessions:
        active_sessions[current_user.username].setdefault("user_data", {})["last_jewelry_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "occasion": budget_input.occasion,
            "has_image": image_path is not None,
        }

    result = get_jewelry_recommendations(budget_input, image_path)

    input_data = budget_input.dict()
    if image and image.filename:
        input_data["image"] = image.filename

    save_to_history(
        username=current_user.username,
        recommendation_type="jewelry",
        input_data=input_data,
        result=result,
    )
    return result


# ---------------------------------------------------------------------------
# History / session-info endpoints
# ---------------------------------------------------------------------------
@app.get("/recommendation-history")
async def get_recommendation_history(current_user: UserInDB = Depends(get_current_active_user)):
    """Get the user's recommendation history."""
    if current_user.username not in user_recommendations:
        return {"history": []}

    history = sorted(
        user_recommendations[current_user.username], key=lambda x: x["timestamp"], reverse=True
    )
    history_data = [
        {
            "id": item["id"],
            "timestamp": item["timestamp"],
            "type": item["recommendation_type"],
            "input": item["input_summary"],
            "summary": item["result_summary"],
        }
        for item in history
    ]
    return {"history": history_data}


@app.get("/recommendation-details/{recommendation_id}")
async def get_recommendation_details(
    recommendation_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Get the full details of a specific recommendation."""
    if current_user.username not in user_recommendations:
        raise HTTPException(status_code=404, detail="No recommendations found")

    for item in user_recommendations[current_user.username]:
        if item["id"] == recommendation_id:
            return {
                "id": item["id"],
                "timestamp": item["timestamp"],
                "type": item["recommendation_type"],
                "input": item["input_summary"],
                "full_result": item["full_result"],
            }

    raise HTTPException(status_code=404, detail="Recommendation not found")


@app.get("/session-info")
async def get_session_info(current_user: UserInDB = Depends(get_current_active_user)):
    """Get the current user's session information."""
    if current_user.username in active_sessions:
        session = active_sessions[current_user.username]
        login_time = datetime.fromisoformat(session["login_time"])
        return {
            "username": session["username"],
            "login_time": session["login_time"],
            "last_activity": session["last_activity"],
            "session_duration": int((datetime.utcnow() - login_time).total_seconds() // 60),
            "user_data": session["user_data"],
        }
    raise HTTPException(status_code=404, detail="No active session found")


@app.post("/session-data")
async def update_session_data(
    data: dict,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Update the user's session data."""
    if current_user.username in active_sessions:
        active_sessions[current_user.username]["user_data"].update(data)
        active_sessions[current_user.username]["last_activity"] = datetime.utcnow().isoformat()
        return {"message": "Session data updated", "data": active_sessions[current_user.username]["user_data"]}
    raise HTTPException(status_code=404, detail="No active session found")


# ---------------------------------------------------------------------------
# Startup: background task to clean expired sessions
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def setup_session_cleanup():
    """Background task to clean up expired (inactive) sessions."""

    async def cleanup_expired_sessions():
        while True:
            current_time = datetime.utcnow()
            expired_usernames = []
            for username, session in list(active_sessions.items()):
                last_activity = datetime.fromisoformat(session["last_activity"])
                if (current_time - last_activity).total_seconds() > 1800:  # 30 minutes
                    expired_usernames.append(username)

            for username in expired_usernames:
                if username in active_sessions:
                    print(f"Removing expired session for {username}")
                    del active_sessions[username]

            await asyncio.sleep(300)  # check every 5 minutes

    asyncio.create_task(cleanup_expired_sessions())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("Starting PocketSmart AI Budget Planner...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
