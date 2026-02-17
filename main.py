from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()

class GameState:
    def __init__(self):
        self.status = "OPEN"  
        # 玩家資料結構升級，加入 wallet (錢包總資金)
        # {"Neo": {"wallet": 5000, "bet": 0, "tickets": 0, "won": 0}}
        self.players = {}     
        self.prize_pool = []  
        self.total_pool = 0

game = GameState()

# --- 請求資料模型 ---
class JoinRequest(BaseModel):
    user_id: str
    initial_funds: int

class BetRequest(BaseModel):
    user_id: str
    amount: int

class GrabRequest(BaseModel):
    user_id: str

ADMIN_SECRET = "louis123" 

class AdminRequest(BaseModel):
    secret: str

def generate_discrete_pool(total_amount: int) -> list:
    total_tickets = int(total_amount / 100)
    base_unit = 10
    total_units = int(total_amount / base_unit)
    remaining_units = total_units - total_tickets
    
    if total_tickets == 0: return []
    if total_tickets == 1: return [total_amount]

    cuts = [random.randint(0, remaining_units) for _ in range(total_tickets - 1)]
    cuts.sort()
    cuts = [0] + cuts + [remaining_units]
    
    pool = [(cuts[i] - cuts[i-1] + 1) * 10 for i in range(1, len(cuts))]
    random.shuffle(pool)
    return pool

# --- API 路由 ---

@app.get("/status")
def get_status():
    return {
        "status": game.status,
        "total_pool": game.total_pool,
        "envelopes_left": len(game.prize_pool)
    }

@app.post("/join")
def join_game(req: JoinRequest):
    """階段 0：玩家建立帳戶並注入總資金"""
    with state_lock:
        if req.user_id not in game.players:
            if req.initial_funds <= 0:
                raise HTTPException(status_code=400, detail="初始資金必須大於 0")
            game.players[req.user_id] = {
                "wallet": req.initial_funds, 
                "bet": 0, 
                "tickets": 0, 
                "won": 0
            }
        
        # 若玩家已存在，直接回傳他目前的錢包狀態 (支援斷線重連)
        return {"msg": "連線成功", "wallet": game.players[req.user_id]["wallet"]}

@app.post("/bet")
def place_bet(req: BetRequest):
    """階段 1：玩家從錢包扣款進行投注"""
    with state_lock:
        if game.status != "OPEN":
            raise HTTPException(status_code=400, detail="目前不在開放投注階段")
        
        if req.amount <= 0 or req.amount % 100 != 0:
            raise HTTPException(status_code=400, detail="投注金額必須是 100 的倍數")

        player = game.players.get(req.user_id)
        if not player:
            raise HTTPException(status_code=400, detail="找不到帳戶，請先連接系統")

        if player["wallet"] < req.amount:
            raise HTTPException(status_code=400, detail=f"資金不足！錢包餘額僅剩 {player['wallet']}")

        # 扣除錢包，增加本局投注額與次數
        player["wallet"] -= req.amount
        player["bet"] += req.amount
        player["tickets"] += int(req.amount / 100)
        game.total_pool += req.amount

        return {
            "msg": "投注成功", 
            "wallet": player["wallet"],
            "tickets": player["tickets"],
            "total_bet": player["bet"]
        }

@app.post("/grab")
def grab_envelope(req: GrabRequest):
    """階段 3：玩家搶奪資金並即時存入錢包"""
    with state_lock:
        if game.status != "GRABBING":
            raise HTTPException(status_code=400, detail="目前無法搶奪")
            
        player = game.players.get(req.user_id)
        if not player or player["tickets"] <= 0:
            raise HTTPException(status_code=400, detail="權限不足")

        if not game.prize_pool:
            raise HTTPException(status_code=400, detail="資金已被搶空")

        player["tickets"] -= 1
        won_amount = game.prize_pool.pop()
        
        # 贏得的錢直接加回錢包餘額與本局紀錄
        player["won"] += won_amount
        player["wallet"] += won_amount

        if not game.prize_pool:
            game.status = "FINISHED"

        return {
            "msg": "搶奪成功",
            "won_amount": won_amount,
            "tickets_left": player["tickets"],
            "total_won_so_far": player["won"],
            "wallet": player["wallet"]
        }

@app.get("/leaderboard")
def get_leaderboard():
    results = []
    for user, data in game.players.items():
        bet = data["bet"]
        won = data["won"]
        profit = won - bet
        roi = (profit / bet * 100) if bet > 0 else 0
        
        results.append({
            "user": user,
            "wallet": data["wallet"], # 顯示剩餘總資產
            "bet": bet,
            "won": won,
            "profit": profit,
            "roi": round(roi, 2)
        })
    results.sort(key=lambda x: x["roi"], reverse=True)
    return {"leaderboard": results}

# --- 管理員專用 API ---
@app.post("/admin/settle")
def settle_game(req: AdminRequest):
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        if game.status != "OPEN": raise HTTPException(status_code=400, detail="只能在 OPEN 狀態下結算")
        if game.total_pool == 0: raise HTTPException(status_code=400, detail="目前沒有任何投注")
        game.status = "LOCKED"
        game.prize_pool = generate_discrete_pool(game.total_pool)
        game.status = "GRABBING"
        return {"msg": "結算完畢，進入搶奪階段"}

@app.post("/admin/next_round")
def next_round(req: AdminRequest):
    """【新增】開啟下一局：保留玩家與錢包，清空本局投注紀錄"""
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        game.status = "OPEN"
        game.prize_pool = []
        game.total_pool = 0
        for user in game.players:
            game.players[user]["bet"] = 0
            game.players[user]["tickets"] = 0
            game.players[user]["won"] = 0
        return {"msg": "已開啟下一局"}

@app.post("/admin/reset")
def reset_game(req: AdminRequest):
    """徹底格式化系統"""
    if req.secret != ADMIN_SECRET: raise HTTPException(status_code=403, detail="權限不足")
    with state_lock:
        game.status = "OPEN"
        game.players = {}
        game.prize_pool = []
        game.total_pool = 0
        return {"msg": "系統已徹底格式化"}