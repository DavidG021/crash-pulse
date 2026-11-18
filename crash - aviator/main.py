import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client

load_dotenv()

# ==========================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# ==========================================
app = FastAPI(title="CrashPulse Risk Engine", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://enzxwyyjetvtzdelxoyn.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. GESTOR DE CONEXIONES WEBSOCKET (CORREGIDO)
# ==========================================
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
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        # Limpieza activa de sockets desconectados
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

# ==========================================
# 3. MODELOS & LÓGICA ANALÍTICA
# ==========================================
voices = [] # Placeholder
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

# ==========================================
# 4. RUTAS HTTP & SERVIDOR FRONTEND
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>CrashPulse Backend Activo (index.html no encontrado)</h1>"

@app.post("/api/round")
async def register_round(data: RoundData):
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        supabase.table("rounds").insert({
            "multiplier": data.multiplier,
            "created_at": timestamp
        }).execute()

        history_response = supabase.table("rounds").select("*").order("created_at", desc=True).limit(20).execute()
        records = history_response.data or []

        low_streak = calculate_streak(records)
        metrics = calculate_metrics(records)

        risk_alert = None
        if low_streak >= 4:
            risk_alert = f"⚠️ ALERTA DE RIESGO CRÍTICO: {low_streak} rondas seguidas menores a 2.0x"
            supabase.table("audit_logs").insert({
                "event_type": "HIGH_RISK_STREAK",
                "streak_count": low_streak,
                "created_at": timestamp
            }).execute()

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    try:
        response = supabase.table("rounds").select("*").order("created_at", desc=True).limit(20).execute()
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
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 5. ENDPOINT ESTRATÉGICO
# ==========================================
@app.get("/predict-strategy")
def predict_strategy():
    try:
        response = supabase.table("rounds").select("multiplier").order("created_at", desc=True).limit(20).execute()
        rondas = response.data
        
        if not rondas or len(rondas) == 0:
            return {
                "status": "success",
                "message": "Aún no hay suficientes rondas registradas en la base de datos.",
                "recommended_cashout": 1.20,
                "risk_level": "Bajo",
                "indicator_color": "verde"
            }
        
        multiplicadores = [float(r["multiplier"]) for r in rondas if r.get("multiplier") is not None]
        
        if not multiplicadores:
            multiplicadores = [1.50, 2.00, 1.25, 3.10, 1.10]
            
        ultimas_cinco = multiplicadores[-5:]
        promedio_reciente = sum(ultimas_cinco) / len(ultimas_cinco)
        promedio_general = sum(multiplicadores) / len(multiplicadores)
        
        proyeccion_teorica = max(promedio_general * 1.05, 1.40)
        cashout_sugerido = round(proyeccion_teorica * (1 - 0.30), 2)
        cashout_sugerido = max(cashout_sugerido, 1.10)
        
        if promedio_reciente < 1.40:
            riesgo = "Alto (Racha baja reciente - Cuidado con crash temprano)"
            color = "rojo"
        elif promedio_reciente > 2.50:
            riesgo = "Moderado (Posible corrección a la baja próxima)"
            color = "amarillo"
        else:
            riesgo = "Estable (Zona óptima de operación)"
            color = "verde"
            
        return {
            "status": "success",
            "total_rounds_analyzed": len(multiplicadores),
            "recent_average_multiplier": round(promedio_reciente, 2),
            "projected_max_limit": round(proyeccion_teorica, 2),
            "recommended_safe_cashout": cashout_sugerido,
            "risk_evaluation": riesgo,
            "indicator_color": color
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 6. ENDPOINT WEBSOCKET
# ==========================================
@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)