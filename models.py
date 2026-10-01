"""
Pydantic models for PocketSmart AI.
Defines request/response schemas for auth, and the three budget planners.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------
class RegisterUser(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    password: str


class UserInDB(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    hashed_password: str
    disabled: bool = False


class UserPublic(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# ---------------------------------------------------------------------------
# Planner input models
# ---------------------------------------------------------------------------
class HomeBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0)
    num_lights: int = 0
    num_fans: int = 0
    num_furniture: int = 0
    num_dining_tables: int = 0
    has_living_room: bool = False
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = None


class PartyBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0)
    num_guests: int = Field(..., gt=0)
    party_type: str
    venue_type: Optional[str] = None
    needs_catering: bool = True
    needs_decoration: bool = True
    needs_entertainment: bool = True
    additional_requirements: Optional[str] = None


class JewelryBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0)
    occasion: str
    preferences: Optional[str] = None


# ---------------------------------------------------------------------------
# Session / history models
# ---------------------------------------------------------------------------
class UserSession(BaseModel):
    username: str
    login_time: str
    last_activity: str
    token: str
    user_data: Dict[str, Any] = {}


class HistoryItem(BaseModel):
    id: str
    username: str
    timestamp: str
    recommendation_type: str
    input_summary: Dict[str, Any]
    result_summary: Dict[str, Any]
    full_result: Dict[str, Any]
