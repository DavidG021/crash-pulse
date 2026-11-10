import os
import asyncio
import traceback
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client

app = FastAPI(title="CrashPulse Risk Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://enzxwyyjetvtzdelxoyn.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_rBN2yKMibGZvG0Xx1BwcYg_jPtKpF3K")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

class RoundData(BaseModel):
    multiplier: float = Field(..., gt=0, description="Multiplicador de la ronda (ej. 1.85)")

def calculate_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"bearish_pct": 0.0, "moving_avg": 0.0}
    last_20 = records[:20]
    total = len(last_20)
    bearish_count = sum(1 for r in last_20 if float(r.get("multiplier", 0)) < 2.0)
    moving_avg = sum(float(r.get("multiplier", 0)) for r in last_20) / total
    return {
        "bearish_pct": round((bearish_count / total) * 100, 1),
        "moving_avg": round(moving_avg, 2)
    }

def calculate_streak(records: List[Dict[str, Any]]) -> int:
    streak = 0
    for r in records:
        if float(r.get("multiplier", 0)) < 2.0:
            streak += 1
        else:
            break
    return streak

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>CrashPulse Backend Activo</h1>"

@app.post("/api/round")
async def register_round(data: RoundData):
    try:
        timestamp = datetime.utcnow().isoformat()
        
        # Inserción en Supabase
        insert_response = supabase.table("game_rounds").insert({
            "multiplier": data.multiplier,
            "created_at": timestamp
        }).execute()

        # Consulta del historial
        history_response = supabase.table("game_rounds").select("*").order("created_at", desc=True).limit(20).execute()
        records = history_response.data or []

        low_streak = calculate_streak(records)
        metrics = calculate_metrics(records)

        risk_alert = None
        if low_streak >= 4:
            risk_alert = f"⚠️ ALERTA DE RIESGO CRÍTICO: {low_streak} rondas seguidas menores a 2.0x"

        payload = {
            "multiplier": data.multiplier,
            "timestamp": timestamp,
            "low_streak": low_streak,
            "bearish_pct": metrics["bearish_pct"],
            "moving_avg": metrics["moving_avg"],
            "risk_alert": risk_alert
        }
        await manager.broadcast(payload)
        return {"status": "success", "data": payload}

    except Exception as e:
        print("\n================ ERROR DETECTADO ================")
        traceback.print_exc()
        print("=================================================\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    try:
        response = supabase.table("game_rounds").select("*").order("created_at", desc=True).limit(20).execute()
        records = response.data or []
        
        chronological_records = list(reversed(records))
        metrics = calculate_metrics(records)
        current_streak = calculate_streak(records)

        return {
            "status": "success",
            "data": chronological_records,
            "metrics": metrics,
            "current_streak": current_streak
        }
    except Exception as e:
        print("\n================ ERROR EN HISTORIAL ================")
        traceback.print_exc()
        print("===================================================\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)