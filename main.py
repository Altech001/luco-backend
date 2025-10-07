from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
# from contextlib import asynccontextmanager
from database.maindb import Base, engine

from routes.contacts import contacts, groups
from routes.authclerk import auth_router
from routes.templates import templates
from routes.sendsms import sendsms
from routes.schedulesms import start_scheduler, shutdown_scheduler, schedule
from routes.developer import developer_api
from routes.devsms import devsms



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(engine)


app = FastAPI(
    title="Bits API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()
    
    

@app.get("/health")
async def health_check():
    return {
        "status": "ok"
    }



app.include_router(router=sendsms)
app.include_router(auth_router)

#=========Contacts ================
app.include_router(router=contacts)
app.include_router(router=groups)
app.include_router(router=templates)

#========= Schedule ===============

app.include_router(router=schedule)

#========== Developer ==============
app.include_router(router=devsms)
app.include_router(router=developer_api)




