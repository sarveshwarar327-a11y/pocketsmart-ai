"""
gemini_utils.py
Core AI service layer for PocketSmart AI.

Handles:
 - Gemini client configuration
 - Prompt construction for Home / Party / Jewelry planners
 - Parsing structured JSON out of the model's text response
 - Attaching platform-specific shopping links to every recommended item
 - Saving uploaded outfit images for the (multimodal) Jewelry planner
"""
import os
import re
import json
import shutil
import urllib.parse
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

from PIL import Image
from fastapi import HTTPException, UploadFile

from models import HomeBudgetInput, PartyBudgetInput, JewelryBudgetInput

# ---------------------------------------------------------------------------
# Gemini configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError(
        "No Google/Gemini API key found in environment variables. "
        "Please set GOOGLE_API_KEY in your .env file."
    )

genai.configure(api_key=API_KEY)

# "Gemini 1.5 Flash Pro" in the spec maps to the gemini-1.5-flash model family.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
model = genai.GenerativeModel(MODEL_NAME)

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def extract_json_from_response(text: str) -> dict:
    """Extract and parse the first JSON object found in a Gemini text response,
    tolerating markdown code fences around it."""
    if not text:
        raise ValueError("Empty response from AI model")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in AI response")

    json_str = cleaned[start : end + 1]
    return json.loads(json_str)


def save_upload_file(upload_file: UploadFile) -> str:
    """Persist an uploaded outfit image to static/uploads and return its path."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", upload_file.filename or "upload.png")
    filename = f"{timestamp}_{safe_name}"
    dest_path = os.path.join(UPLOAD_DIR, filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    return dest_path


def usd_to_inr(amount_usd: float, exchange_rate: float = 83.0) -> float:
    """Convert USD to INR (kept for compatibility with budgets entered in USD)."""
    return amount_usd * exchange_rate


def _search_url(base: str, query: str) -> str:
    return base.format(q=urllib.parse.quote_plus(query))


# ---------------------------------------------------------------------------
# Platform link templates
# ---------------------------------------------------------------------------
HOME_PLATFORM_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "ikea": "https://www.ikea.com/in/en/search/?q={q}",
    "myntra": "https://www.myntra.com/search?q={q}",
    "ajio": "https://www.ajio.com/search/?text={q}",
}

PARTY_PLATFORM_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "bigbasket": "https://www.bigbasket.com/ps/?q={q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "zomato": "https://www.zomato.com/search?q={q}",
    "bookmyshow": "https://in.bookmyshow.com/search?q={q}",
    "myntra": "https://www.myntra.com/search?q={q}",
    "meesho": "https://www.meesho.com/search?q={q}",
    "google": "https://www.google.com/search?q={q}",
    "booking": "https://www.booking.com/search.html?ss={q}",
    "makemytrip": "https://www.makemytrip.com/hotels/hotel-listing/?searchText={q}",
    "oyorooms": "https://www.oyorooms.com/search/?location={q}",
    "nobroker": "https://www.nobroker.in/property/search?searchTerm={q}",
}

PARTY_CATEGORY_PLATFORMS = {
    "venue": ["google", "booking", "makemytrip", "oyorooms", "nobroker"],
    "catering": ["swiggy", "zomato"],
    "food": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
    "drinks": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
    "decoration": ["amazon", "flipkart", "meesho", "myntra"],
    "entertainment": ["bookmyshow", "amazon", "flipkart"],
    "gifts": ["amazon", "flipkart", "myntra", "meesho"],
    "photography": ["google", "amazon", "flipkart"],
    "music": ["amazon", "flipkart", "bookmyshow"],
    "games": ["amazon", "flipkart"],
    "accessories": ["amazon", "flipkart", "myntra", "meesho"],
    "transportation": ["makemytrip", "google"],
    "return_gifts": ["amazon", "flipkart", "myntra", "meesho"],
    "contingency": ["amazon", "flipkart", "google"],
}
PARTY_DEFAULT_PLATFORMS = ["amazon", "flipkart", "google"]

JEWELRY_PLATFORM_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "bluestone": "https://www.bluestone.com/search.html?query={q}",
    "tanishq": "https://www.tanishq.co.in/search?q={q}",
    "caratlane": "https://www.caratlane.com/search?q={q}",
    "melorra": "https://www.melorra.com/search?q={q}",
    "meesho": "https://www.meesho.com/search?q={q}",
}


def _add_home_links(item: dict) -> None:
    search_terms = item.get("search_terms", "")
    if not search_terms:
        return
    item["shopping_links"] = {
        name: _search_url(url, search_terms) for name, url in HOME_PLATFORM_URLS.items()
    }


def _add_party_links(item: dict, category_name: str) -> None:
    search_terms = item.get("search_terms", "")
    if not search_terms:
        return
    platforms = PARTY_CATEGORY_PLATFORMS.get(category_name.lower(), PARTY_DEFAULT_PLATFORMS)
    item["shopping_links"] = {
        name: _search_url(PARTY_PLATFORM_URLS[name], search_terms)
        for name in platforms
        if name in PARTY_PLATFORM_URLS
    }


def _add_jewelry_links(item: dict) -> None:
    search_terms = item.get("search_terms", "")
    if not search_terms:
        return
    item["shopping_links"] = {
        name: _search_url(url, search_terms) for name, url in JEWELRY_PLATFORM_URLS.items()
    }


def _build_calculation_table(budget_breakdown: list, total_budget: float, key: str = "calculation_table") -> dict:
    categories: dict = {}
    for category in budget_breakdown:
        cat_name = category.get("category", "Misc")
        if cat_name not in categories:
            categories[cat_name] = {"category": cat_name, "items_count": 0, "total_cost": 0.0, "percentage_of_budget": 0.0}
        for item in category.get("items", []):
            categories[cat_name]["items_count"] += 1
            categories[cat_name]["total_cost"] += float(item.get("estimated_price", 0) or 0)

    if total_budget > 0:
        for cat in categories.values():
            cat["percentage_of_budget"] = round((cat["total_cost"] / total_budget) * 100, 2)

    return {key: list(categories.values())}


# ---------------------------------------------------------------------------
# 1. Home Interior Planner
# ---------------------------------------------------------------------------
def get_home_recommendations(budget_input: HomeBudgetInput) -> dict:
    """Generate home interior recommendations within budget, in INR, for the Indian market."""
    try:
        prompt = f"""
I need interior design product recommendations for a home in India with a total budget of Rs.{budget_input.total_budget:.2f}.

Requirements:
- {budget_input.num_lights} lights/lighting fixtures
- {budget_input.num_fans} ceiling fans
- {budget_input.num_furniture} furniture pieces
- {budget_input.num_dining_tables} dining tables

Additional rooms to consider:
{"- Living room" if budget_input.has_living_room else ""}
{"- Kitchen" if budget_input.has_kitchen else ""}
{"- Bedroom" if budget_input.has_bedroom else ""}

Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with product recommendations **available in India**.
Use **Indian brands and pricing**. Include **search terms** suitable for Indian shopping platforms.

Format your response strictly as JSON with the following structure and nothing else:
{{
  "total_budget": {budget_input.total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "lighting",
      "allocation": 0.0,
      "items": [
        {{
          "name": "",
          "description": "",
          "estimated_price": 0.0,
          "quantity": 0,
          "search_terms": ""
        }}
      ]
    }}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": []
}}

Ensure total costs stay within budget. Include search terms for each item to find on shopping
websites like Flipkart, Amazon India, IKEA, Myntra and Ajio.
"""
        response = model.generate_content(prompt)
        result = extract_json_from_response(response.text)

        for category in result.get("budget_breakdown", []):
            for item in category.get("items", []):
                _add_home_links(item)

        result.update(_build_calculation_table(result.get("budget_breakdown", []), result.get("total_budget", budget_input.total_budget)))
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


# ---------------------------------------------------------------------------
# 2. Party Planner
# ---------------------------------------------------------------------------
def get_party_recommendations(budget_input: PartyBudgetInput) -> dict:
    """Generate party planning recommendations within budget, in INR, for the Indian market."""
    try:
        prompt = f"""
I need party planning recommendations for India with a total budget of Rs.{budget_input.total_budget:.2f}.

Party details:
- Type: {budget_input.party_type}
- Number of guests: {budget_input.num_guests}
- Venue type: {budget_input.venue_type or "Not specified"}
- Catering needed: {"Yes" if budget_input.needs_catering else "No"}
- Decoration needed: {"Yes" if budget_input.needs_decoration else "No"}
- Entertainment needed: {"Yes" if budget_input.needs_entertainment else "No"}

Additional requirements: {budget_input.additional_requirements or "None"}

Please provide a detailed budget breakdown with specific recommendations available in India using INR prices.
Use Indian brands, services, and typical cost expectations.

Format your response strictly as JSON with the following structure and nothing else:
{{
  "total_budget": {budget_input.total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "venue",
      "allocation": 0.0,
      "items": [
        {{
          "name": "",
          "description": "",
          "estimated_price": 0.0,
          "quantity": 0,
          "search_terms": ""
        }}
      ]
    }}
  ],
  "venue_suggestions": [
    {{
      "name": "",
      "type": "",
      "capacity": 0,
      "estimated_cost": 0.0,
      "search_terms": ""
    }}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": []
}}

Ensure all costs are in INR and total does not exceed the given budget.
Provide search terms suitable for Indian websites such as BookMyShow, Swiggy, Zomato, etc.
"""
        response = model.generate_content(prompt)
        result = extract_json_from_response(response.text)

        for category in result.get("budget_breakdown", []):
            cat_name = category.get("category", "")
            for item in category.get("items", []):
                _add_party_links(item, cat_name)

        for venue in result.get("venue_suggestions", []):
            search_terms = venue.get("search_terms", "")
            if search_terms:
                venue["search_links"] = {
                    name: _search_url(PARTY_PLATFORM_URLS[name], search_terms)
                    for name in ["google", "booking", "makemytrip", "oyorooms", "nobroker"]
                }

        result.update(
            _build_calculation_table(
                result.get("budget_breakdown", []),
                result.get("total_budget", budget_input.total_budget),
                key="calculation_table_inr",
            )
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


# ---------------------------------------------------------------------------
# 3. Jewelry Planner (multimodal: text + optional outfit image)
# ---------------------------------------------------------------------------
def get_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> dict:
    """Generate jewelry recommendations based on an optional uploaded outfit image and budget, in INR."""
    try:
        base_prompt = f"""
I need jewelry recommendations for India with a total budget of Rs.{budget_input.total_budget:.2f}.

Occasion: {budget_input.occasion}
Preferences: {budget_input.preferences or "Not specified"}
Provide only India-relevant styles, availability, and price ranges in INR.
"""

        if image_path:
            img = Image.open(image_path)
            prompt = base_prompt + """
An image of the outfit is uploaded. Suggest jewelry that complements it, considering color, design, and occasion appropriateness.

Format the output strictly as JSON and nothing else:
{
  "outfit_analysis": {
    "colors": [],
    "style": "",
    "formality": ""
  },
  "total_budget": 0.0,
  "jewelry_recommendations": [
    {
      "item_type": "",
      "description": "",
      "style": "",
      "estimated_price": 0.0,
      "search_terms": ""
    }
  ],
  "remaining_budget": 0.0,
  "styling_tips": []
}

Make sure prices are in INR and stay within budget.
Include Indian-friendly search terms for shopping.
"""
            response = model.generate_content([prompt, img])
        else:
            prompt = base_prompt + """
Format the output strictly as JSON and nothing else:
{
  "total_budget": 0.0,
  "jewelry_recommendations": [
    {
      "item_type": "",
      "description": "",
      "style": "",
      "estimated_price": 0.0,
      "search_terms": ""
    }
  ],
  "remaining_budget": 0.0,
  "styling_tips": []
}

Keep prices in INR and relevant to Indian brands.
"""
            response = model.generate_content(prompt)

        result = extract_json_from_response(response.text)

        for item in result.get("jewelry_recommendations", []):
            _add_jewelry_links(item)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")
