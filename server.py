import os
import sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Mizze Key Store API")

def get_db():
    return sqlite3.connect("keys.db")

class ClaimRequest(BaseModel):
    user_id: int
    plan_name: str

@app.get("/")
async def root():
    return {"status": "Mizze Backend is running smoothly!"}

# API cấp key tự động cho Mini App (nếu gọi trực tiếp qua HTTP)
@app.post("/api/claim-key")
async def claim_key(data: ClaimRequest):
    with get_db() as conn:
        plan = conn.execute("SELECT id, name, duration_hours FROM key_prices WHERE name=?", (data.plan_name,)).fetchone()
        if not plan:
            raise HTTPException(status_code=400, detail="Gói không tồn tại.")
        
        plan_id, name_p, duration_h = plan
        stock_item = conn.execute("SELECT id, key_code FROM key_stock WHERE plan_id=? AND is_used=0 LIMIT 1", (plan_id,)).fetchone()
        
        if not stock_item:
            raise HTTPException(status_code=400, detail=f"Kho key gói {name_p} đã hết.")
        
        stock_id, code = stock_item
        conn.execute("UPDATE key_stock SET is_used=1 WHERE id=?", (stock_id,))
        
        expires = datetime.now() + timedelta(hours=duration_h)
        conn.execute("INSERT INTO keys (key_code, user_id, plan_id, expires_at) VALUES (?, ?, ?, ?)", (code, data.user_id, plan_id, expires))
        conn.commit()
        
        return {
            "success": True,
            "key_code": code,
            "plan_name": name_p,
            "expires_at": expires.strftime('%d/%m/%Y %H:%M')
        }