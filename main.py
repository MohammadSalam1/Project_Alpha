from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
from contextlib import asynccontextmanager

from database import Device, Check, SessionLocal, get_db

def ping_ip(ip_address: str) -> bool:
    # Run one ICMP ping using the Windows ping command.
    # This returns True if the host responds and False otherwise.
    result = subprocess.run(
        ["ping", "-n", "1", ip_address],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.returncode == 0

def scan_devices():
    # Background job that runs on a schedule and checks every enabled device.
    print("Scan is DONE")
    db = SessionLocal()
    try:
        # Only check devices that are currently enabled.
        devices = db.query(Device).filter(Device.enabled == True).all()
        for device in devices:
            # Store the ping result as a history row.
            is_up = ping_ip(device.ip_address)
            check = Check(device_id=device.id, is_up=is_up)
            db.add(check)
        db.commit()
    finally:
        # Always close the database session, even if pinging fails.
        db.close()

# Scheduler is created once and started/stopped with the app lifecycle.
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Periodic scheduler that runs the network scan in the background.
    # This turns the app into a simple monitoring tool instead of a manual checker.
    scheduler.add_job(scan_devices, 'interval', seconds=60, next_run_time=datetime.now())
    scheduler.start()
    
    yield
    
    scheduler.shutdown()

# Main FastAPI application instance.
app = FastAPI(lifespan=lifespan)
# Jinja2 template directory used for rendering the dashboard page.
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # Load all devices from the database.
    devices = db.query(Device).all()

    # Attach the latest check result to each device so the template can show status.
    # These fields are added dynamically for display only.
    for device in devices:
        latest = db.query(Check).filter(Check.device_id == device.id).order_by(desc(Check.checked_at)).first()
        device.last_up = latest.is_up if latest else None
        device.last_checked = latest.checked_at if latest else None

    # Render the dashboard with the current device list.
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "devices": devices}
    )

@app.get("/devices/{device_id}", response_class=HTMLResponse)
def device_history(device_id: int, request: Request, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id==device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # last 50 checks, newest first
    checks = (
        db.query(Check)
        .filter(Check.device_id ==  device_id)
        .order_by(desc(Check.checked_at))
        .limit(50)
        .all()
    )
    
    # uptime % over the loaded window. None if no checks yet.
    if checks:
        up_count = sum(1 for c in checks if c.is_up)
        uptime_pct = round(100 * up_count / len(checks), 1)
    else:
        uptime_pct = None
    
    return templates.TemplateResponse(
        "device.html",
        {
        "request": request,
        "device": device,
        "checks": checks,
        "uptime_pct": uptime_pct,
        },
    )

@app.post("/add-device")
def add_device(
        name: str = Form(...),
        ip_address: str = Form(...),
        db: Session = Depends(get_db)
):
    # Create a new monitored device from the submitted form data.
    device = Device(name=name, ip_address=ip_address, enabled=True)
    db.add(device)
    db.commit()
    db.refresh(device)
    
    # Immediate first check to the dashboard isn't pending for up to 60s
    is_up = ping_ip(device.ip_address)
    db.add(Check(device_id=device.id, is_up=is_up))
    db.commit()

    # Redirect back to the dashboard after saving.
    return RedirectResponse(url="/", status_code=303)

