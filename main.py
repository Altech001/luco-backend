import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import httpx

from database.maindb import Base, engine
from routes.contacts import contacts, groups
from routes.authclerk import auth_router
from routes.templates import templates
from routes.sendsms import sendsms
from routes.schedulesms import start_scheduler, shutdown_scheduler, schedule
from routes.developer import developer_api
from routes.devsms import devsms

import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keep-alive settings
PING_INTERVAL = 600
APP_URL = "https://luco-backend.onrender.com"

async def keep_alive():
    """Task that pings the app URL periodically to keep it alive."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                logger.info(f"Sending keep-alive ping to {APP_URL}/health")
                response = await client.get(f"{APP_URL}/health")
                logger.info(f"Keep-alive response: {response.status_code}")
            except asyncio.CancelledError:
                logger.info("Keep-alive task cancelled")
                break
            except Exception as e:
                logger.error(f"Keep-alive ping failed: {str(e)}")
            
            await asyncio.sleep(PING_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown"""
    # Startup
    logger.info("Starting application...")
    
    # Start the scheduler
    start_scheduler()
    logger.info("✓ Scheduler started")
    
    # Start keep-alive task
    keep_alive_task = None
    if APP_URL:
        keep_alive_task = asyncio.create_task(keep_alive())
        logger.info("✓ Keep-alive task started")
    else:
        logger.warning("APP_URL not set - keep-alive disabled")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Cancel keep-alive task
    if keep_alive_task:
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
        logger.info("✓ Keep-alive task stopped")
    
    # Shutdown scheduler
    shutdown_scheduler()
    logger.info("✓ Scheduler stopped")

# Create tables
Base.metadata.create_all(engine)

# Initialize FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="Bits API"
)

origins = [
    "https://lucosms-ui-three.vercel.app",
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for keep-alive pings"""
    return {
        "status": "ok",
        "service": "Bits API"
    }

# Include routers
app.include_router(router=sendsms)
app.include_router(router=auth_router)

# Contacts
app.include_router(router=contacts)
app.include_router(router=groups)
app.include_router(router=templates)

# Schedule
app.include_router(router=schedule)

# Developer
app.include_router(router=devsms)
app.include_router(router=developer_api)