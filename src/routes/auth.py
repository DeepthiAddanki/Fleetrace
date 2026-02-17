from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Body
from datetime import datetime, timezone
from src.config.db import db


router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Helper: get current logged-in user
def get_current_user(request: Request):
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user = db.auth.get_user(token)
        return user
    except Exception:
        # Token expired or invalid
        raise HTTPException(status_code=401, detail="Session expired")


# SIGNUP (DRIVER ONLY)

@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(
        "signup.html",
        {"request": request}
    )

@router.post("/signup")
def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    # Create auth user WITH metadata
    auth = db.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "name": name   
            }
        }
    })

    if not auth.user:
        raise HTTPException(status_code=400, detail="Signup failed")

    user_id = auth.user.id

    # Create driver entry 
    db.table("drivers").insert({
        "id": user_id
    }).execute()

    #  Auto login after signup
    login = db.auth.sign_in_with_password({
    "email": email,
    "password": password
})

    response = RedirectResponse("/driver/onboarding", status_code=302)
    response.set_cookie(
    key="access_token",
    value=login.session.access_token,
    httponly=True,
    path="/"
)

    return response



# SIGNIN (ADMIN / DRIVER)
@router.get("/signin", response_class=HTMLResponse)
def signin_page(request: Request):
    return templates.TemplateResponse(
        "signin.html",
        {"request": request}
    )


@router.post("/signin")
def signin(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    try:

        auth = db.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    
    except Exception:
        return templates.TemplateResponse(
            "signin.html",
            {
                "request": request,
                "error": "Invalid email or password"
            }
        )

    # if not auth.user:
    #     raise HTTPException(status_code=401, detail="Invalid credentials")

    profile = db.table("profiles") \
        .select("role") \
        .eq("id", auth.user.id) \
        .single() \
        .execute()

    role = profile.data["role"]
    redirect_url = "/admin/dashboard" if role == "admin" else "/driver/dashboard"

    response = RedirectResponse(redirect_url, status_code=302)

   
    response.set_cookie(
        key="access_token",
        value=auth.session.access_token,
        httponly=True,
        path="/"
    )

    return response

@router.get("/driver/onboarding", response_class=HTMLResponse)
def driver_onboarding(request: Request):
    user = get_current_user(request)

    role = db.table("profiles") \
        .select("role") \
        .eq("id", user.user.id) \
        .single() \
        .execute().data["role"]

    if role != "driver":
        raise HTTPException(status_code=403)

    # If already onboarded → skip onboarding
    driver = db.table("drivers") \
        .select("is_onboarded") \
        .eq("id", user.user.id) \
        .single() \
        .execute()

    if driver.data and driver.data["is_onboarded"]:
        return RedirectResponse("/driver/dashboard", status_code=302)

    return templates.TemplateResponse(
        "driver-onboarding.html",
        {"request": request}
    )

# ADMIN DASHBOARD

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user = get_current_user(request)
    role = db.table("profiles").select("role").eq("id", user.user.id).single().execute().data["role"]

    if role != "admin":
        raise HTTPException(status_code=403)

    return templates.TemplateResponse("dashboard.html", {"request": request})

# DRIVER DASHBOARD

@router.get("/driver/dashboard", response_class=HTMLResponse)
def driver_dashboard(request: Request):
    user = get_current_user(request)
    user_id = user.user.id

    profile = db.table("profiles") \
        .select("role") \
        .eq("id", user_id) \
        .single() \
        .execute()

    if profile.data["role"] != "driver":
        raise HTTPException(status_code=403)

    #  ONBOARDING GUARD
    driver = db.table("drivers") \
        .select("is_onboarded") \
        .eq("id", user_id) \
        .single() \
        .execute()

    if not driver.data or not driver.data["is_onboarded"]:
        return RedirectResponse("/driver/onboarding", status_code=302)

    # MARK DRIVER ONLINE
    # db.table("drivers").update({
    #     "is_online": True,
    #     "last_seen": "now()"
    # }).eq("id", user_id).execute()

    db.table("drivers").update({
        "is_online": True
    }).eq("id", user.user.id).execute()

    return templates.TemplateResponse(
        "dashboard_driver.html",
        {"request": request}
    )

@router.post("/driver/logout")
def driver_logout(request: Request):
    user = get_current_user(request)

    db.table("drivers").update({
        "is_online": False
    }).eq("id", user.user.id).execute()

    request.session.clear()
    return {"ok": True}


#fetch driver data in driver dashboard
@router.get("/driver/me")
def get_driver_details(request: Request):
    user = get_current_user(request)
    user_id = user.user.id

    driver = db.table("drivers") \
        .select(
            "first_name, last_name, phone_number, license_number, "
            "vehicle_number, vehicle_type, vehicle_model"
        ) \
        .eq("id", user_id) \
        .single() \
        .execute()

    profile = db.table("profiles") \
        .select("name") \
        .eq("id", user_id) \
        .single() \
        .execute()

    return {
        "name": profile.data["name"],
        **driver.data
    }

# GET CURRENT USER INFO
@router.get("/me")
def me(request: Request):
    user = get_current_user(request)

    profile = db.table("profiles") \
        .select("name, role") \
        .eq("id", user.user.id) \
        .single() \
        .execute()

    return {
        "id": user.user.id,
        "name": profile.data["name"],
        "role": profile.data["role"]
    }


# DRIVER: UPDATE VEHICLE LOCATION
@router.post("/driver/update-location")
def update_location(request: Request, data: dict = Body(...)):
    user = get_current_user(request)
    user_id = user.user.id
    lat = data["latitude"]
    lng = data["longitude"]

    db.table("vehicle_locations").upsert({
        "driver_id": user_id,
        "latitude": lat,
        "longitude": lng
    }).execute()

    # Mirror into drivers (for admin dashboard)
    db.table("drivers").update({
        "last_latitude": lat,
        "last_longitude": lng,
        "last_location_at": "now()"
    }).eq("id", user_id).execute()

    return {"message": "Location updated"}


# ADMIN: LIVE VEHICLE LOCATIONS
@router.get("/admin/live-locations")
def live_locations(request: Request):
    user = get_current_user(request)

    role = db.table("profiles") \
        .select("role") \
        .eq("id", user.user.id) \
        .single() \
        .execute()

    if role.data["role"] != "admin":
        raise HTTPException(status_code=403)

    locations = db.table("vehicle_locations") \
        .select("""
            latitude,
            longitude,
            updated_at,
            drivers(
                first_name,
                last_name,
                vehicle_number
            )
        """) \
        .order("updated_at", desc=True) \
        .execute()

    return locations.data


@router.post("/driver/add-vehicle")
def add_vehicle(
    request: Request,
    vehicle_number: str = Form(...)
):
    user = get_current_user(request)

    profile = db.table("profiles") \
        .select("role") \
        .eq("id", user.user.id) \
        .single() \
        .execute()

    if profile.data["role"] != "driver":
        raise HTTPException(status_code=403, detail="Drivers only")

    db.table("vehicles").insert({
        "vehicle_number": vehicle_number,
        "driver_id": user.user.id
    }).execute()

    return {"message": "Vehicle added successfully"}


@router.post("/api/complete-profile")
def complete_driver_profile(request: Request, data: dict = Body(...)):
    user = get_current_user(request)
    user_id = user.user.id

    db.table("drivers") \
      .update({
          "first_name": data["firstName"],
          "last_name": data["lastName"],
          "phone_number": data["phone"],
          "license_number": data["license"],
          "vehicle_number": data["vehicleNumber"],
          "vehicle_type": data["vehicleType"],
          "vehicle_model": data["vehicleModel"],
          "is_onboarded": True
      }) \
      .eq("id", user_id) \
      .execute()

    return {"success": True}

@router.get("/admin/drivers")
def get_all_drivers(request: Request):
    user = get_current_user(request)

    role = db.table("profiles").select("role").eq("id", user.user.id).single().execute()
    if role.data["role"] != "admin":
        raise HTTPException(status_code=403)

    drivers = db.table("drivers").select(
        "id, first_name, last_name, phone_number, vehicle_number, "
        "last_latitude, last_longitude, last_location_at, "
        "is_online, last_seen"
    ).execute()

    return drivers.data

 
@router.post("/driver/heartbeat")
def heartbeat(request: Request):
    user = get_current_user(request)

    db.table("drivers").update({
        "is_online": True,
        "last_seen": "now()"
    }).eq("id", user.user.id).execute()

    return {"status": "alive"}

@router.post("/driver/set-status")
def set_driver_status(request: Request, data: dict = Body(...)):
    user = get_current_user(request)
    user_id = user.user.id

    is_online = data.get("is_online", False)

    db.table("drivers").update({
        "is_online": is_online,
        "last_seen": "now()" if is_online else None
    }).eq("id", user_id).execute()

    return {"success": True, "is_online": is_online}

# =================================================
# RESET PASSWORD (OPTIONAL)
# =================================================
# @router.post("/reset-password")
# def reset_password(email: str = Form(...)):
#     db.auth.reset_password_for_email(email)
#     return {"message": "Password reset link sent"}



# LOGOUT
@router.get("/logout")
def logout():
    response = RedirectResponse("/signin", status_code=302)
    response.delete_cookie("access_token", path = "/")
    return response
