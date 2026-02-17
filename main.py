from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import threading
import time  # 【新增】引入時間模組來產生廣播時間戳

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()

users_db = {}

class GameState:
    def __init__(self):
        self.status = "OPEN"  
        self.players = {}     
        self.prize_pool = []  
        self.total_pool = 0
        self.last_donation = None  # 【新增】記錄最後一次贊助的資訊

game = GameState()

class UserRequest(BaseModel):
    user_id: str

class ActionRequest(BaseModel):
    user_id: str
    amount: int

class AdminRequest(BaseModel):
    secret: str

ADMIN_SECRET = "louis" 

def generate_discrete_pool(total_amount: int, total_tickets: int) -> list:
    if total_tickets == 0: return []
    if total_tickets == 1: return [total_amount]

    base_unit = 10
    total_units = int(total_amount / base_unit)
    remaining_units = total_units - total_tickets
    
    cuts = [random.randint(0, remaining_units) for _ in range(total_tickets - 1)]
    cuts.sort()
    cuts = [0] + cuts + [remaining_units]
    
    pool = [(cuts[i] - cuts[i-1] + 1) * 10 for i in range(1, len(cuts))]
    random.shuffle(pool)
    return pool

def auto_reset_game():
    with state_lock:
        if game.status == "FINISHED":
            game.status = "OPEN"
            game.players = {}
            game.prize_pool = []
            game.total_pool = 0
            game.last_donation = None # 清空廣播
            print("🕒 [系統] 15秒結算期結束，單局已自動重置為 OPEN。")

@app.post("/login")
def login(req: UserRequest):
    with state_lock:
        if req.user_id not in users_db:
            users_db[req.user_id] = {"wallet": 0}
        return {"wallet": users_db[req.user_id]["wallet"]}

@app.post("/recharge")
def recharge_wallet(req: ActionRequest):
    with state_lock:
        if req.amount <= 0: raise HTTPException(status_code=400, detail="充值金額無效")
        if req.user_id not in users_db: users_db[req.user_id] = {"wallet": 0}
        users_db[req.user_id]["wallet"] += req.amount
        return {"msg": f"充值成功", "wallet": users_db[req.user_id]["wallet"]}

@app.post("/bet")
def place_bet(req: ActionRequest):
    with state_lock:
        if game.status != "OPEN": raise HTTPException(status_code=400, detail="目前不在開放階段")
        if req.amount <= 0 or req.amount % 100 != 0: raise HTTPException(status_code=400, detail="數量無效")
        
        user_wallet = users_db.get(req.user_id, {"wallet": 0})
        if user_wallet["wallet"] < req.amount: raise HTTPException(status_code=400, detail="餘額不足，請先充值！")

        users_db[req.user_id]["wallet"] -= req.amount
        if req.user_id not in game.players: game.players[req.user_id] = {"bet": 0, "tickets": 0, "won": 0}
            
        game.players[req.user_id]["bet"] += req.amount
        game.players[req.user_id]["tickets"] += int(req.amount / 100)
        game.total_pool += req.amount

        return { "msg": "購買成功", "wallet": users_db[req.user_id]["wallet"], "tickets": game.players[req.user_id]["tickets"], "total_bet": game.players[req.user_id]["bet"] }

@app.post("/donate")
def donate_pool(req: ActionRequest):
    with state_lock:
        if game.status != "OPEN": raise HTTPException(status_code=400, detail="目前不在開放階段")
        if req.amount <= 0 or req.amount % 100 != 0: raise HTTPException(status_code=400, detail="贊助金額無效")

        user_wallet = users_db.get(req.user_id, {"wallet": 0})
        if user_wallet["wallet"] < req.amount: raise HTTPException(status_code=400, detail="餘額不足！")

        users_db[req.user_id]["wallet"] -= req.amount
        if req.user_id not in game.players: game.players[req.user_id] = {"bet": 0, "tickets": 0, "won": 0}
            
        game.players[req.user_id]["bet"] += req.amount
        game.total_pool += req.amount
        
        # 【新增】記錄最新一筆廣播訊息
        game.last_donation = {
            "user": req.user_id,
            "amount": req.amount,
            "ts": time.time()
        }

        return { "msg": f"感謝贊助！", "wallet": users_db[req.user_id]["wallet"], "total_bet": game.players[req.user_id]["bet"] }

@app.post("/grab")
def grab_envelope(req: UserRequest):
    with state_lock:
        if game.status != "GRABBING": raise HTTPException(status_code=400, detail="目前無法駭入")
            
        player = game.players.get(req.user_id)
        if not player or player["tickets"] <= 0: raise HTTPException(status_code=400, detail="權限不足")
        if not game.prize_pool: raise HTTPException(status_code=400, detail="紅包已經被搶光了")

        player["tickets"] -= 1
        won_amount = game.prize_pool.pop()
        
        player["won"] += won_amount
        users_db[req.user_id]["wallet"] += won_amount

        if not game.prize_pool:
            game.status = "FINISHED"
            threading.Timer(15.0, auto_reset_game).start()

        return { "msg": "奪取成功", "won_amount": won_amount, "tickets_left": player["tickets"], "total_won_so_far": player["won"], "wallet": users_db[req.user_id]["wallet"] }

@app.get("/status")
def get_status(): 
    # 【新增】回傳 last_donation 給前端
    return {
        "status": game.status, 
        "total_pool": game.total_pool, 
        "envelopes_left": len(game.prize_pool),
        "last_donation": game.last_donation
    }

@app.get("/leaderboard")
def get_leaderboard():
    results = []
    for user, data in game.players.items():
        bet = data["bet"]
        won = data["won"]
        profit = won - bet
        roi = (profit / bet * 100) if bet > 0 else 0
        results.append({ "user": user, "bet": bet, "won": won, "profit": profit, "roi": round(roi, 2) })
    results.sort(key=lambda x: x["roi"], reverse=True)
    return {"leaderboard": results}

@app.post("/admin/settle")
def settle_game(req: AdminRequest):
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        if game.status != "OPEN": raise HTTPException(status_code=400, detail="只能在 OPEN 狀態下結算")
        if game.total_pool == 0: raise HTTPException(status_code=400, detail="目前沒有任何資金")
        total_tickets = sum(p["tickets"] for p in game.players.values())
        if total_tickets == 0: raise HTTPException(status_code=400, detail="全場無人持有駭入權限，無法引爆！")
        
        game.status = "LOCKED"
        game.prize_pool = generate_discrete_pool(game.total_pool, total_tickets)
        game.status = "GRABBING"
        return {"msg": "結算完畢", "total_envelopes": len(game.prize_pool)}

@app.post("/admin/reset")
def reset_game(req: AdminRequest):
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        if game.status != "FINISHED":
            for user_id, player_data in game.players.items():
                if user_id in users_db:
                    refund_amount = player_data["bet"]
                    users_db[user_id]["wallet"] += refund_amount

        game.status = "OPEN"
        game.players = {}
        game.prize_pool = []
        game.total_pool = 0
        game.last_donation = None
        return {"msg": "單局已重置，所有投注已退還至玩家錢包。"}

@app.post("/admin/hard_reset")
def hard_reset_game(req: AdminRequest):
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        global users_db
        users_db.clear() 
        game.status = "OPEN"
        game.players = {}
        game.prize_pool = []
        game.total_pool = 0
        game.last_donation = None
        return {"msg": "伺服器已徹底格式化，所有帳戶與資金已銷毀。"}