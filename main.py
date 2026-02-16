from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import threading

app = FastAPI()

# --- 跨網域 (CORS) 設定 ---
# 這是最重要的設定！如果不開，你的 github.io 前端會被瀏覽器阻擋，無法呼叫這個 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 測試期允許所有來源，上線後務必改成你的 github.io 網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 系統全域狀態 (測試用，正式環境應改用 Redis + DB) ---
# 使用 threading.Lock() 來防止極端情況下的併發搶奪問題
state_lock = threading.Lock()

class GameState:
    def __init__(self):
        self.status = "OPEN"  # OPEN, LOCKED, GRABBING
        self.players = {}     # {"Louis": {"bet": 300, "tickets": 3, "won": 0}}
        self.prize_pool = []  # 存放紅包金額的陣列
        self.total_pool = 0

game = GameState()

# --- 請求資料模型 ---
class BetRequest(BaseModel):
    user_id: str
    amount: int

class GrabRequest(BaseModel):
    user_id: str

# --- 核心演算法 (離散區塊切線段法) ---
def generate_discrete_pool(total_amount: int) -> list:
    total_tickets = int(total_amount / 100)
    base_unit = 10
    total_units = int(total_amount / base_unit)
    remaining_units = total_units - total_tickets
    
    if total_tickets == 0:
        return []
    if total_tickets == 1:
        return [total_amount]

    cuts = [random.randint(0, remaining_units) for _ in range(total_tickets - 1)]
    cuts.sort()
    cuts = [0] + cuts + [remaining_units]
    
    pool = [(cuts[i] - cuts[i-1] + 1) * 10 for i in range(1, len(cuts))]
    random.shuffle(pool)
    return pool

# --- API 路由 ---

@app.get("/status")
def get_status():
    """前端輪詢用：查詢目前遊戲狀態"""
    return {
        "status": game.status,
        "total_pool": game.total_pool,
        "envelopes_left": len(game.prize_pool)
    }

@app.post("/bet")
def place_bet(req: BetRequest):
    """階段 1：玩家投注"""
    with state_lock:
        if game.status != "OPEN":
            raise HTTPException(status_code=400, detail="目前不在開放投注階段")
        
        if req.amount <= 0 or req.amount % 100 != 0:
            raise HTTPException(status_code=400, detail="投注金額必須是 100 的倍數")

        if req.user_id not in game.players:
            game.players[req.user_id] = {"bet": 0, "tickets": 0, "won": 0}
            
        game.players[req.user_id]["bet"] += req.amount
        game.players[req.user_id]["tickets"] += int(req.amount / 100)
        game.total_pool += req.amount

        return {
            "msg": "投注成功", 
            "tickets": game.players[req.user_id]["tickets"],
            "total_bet": game.players[req.user_id]["bet"]
        }

@app.post("/admin/settle")
def settle_game():
    """階段 2：管理員觸發結算 (鎖定盤口並產生紅包)"""
    with state_lock:
        if game.status != "OPEN":
            raise HTTPException(status_code=400, detail="只能在 OPEN 狀態下結算")
            
        if game.total_pool == 0:
            raise HTTPException(status_code=400, detail="目前沒有任何投注")

        game.status = "LOCKED"
        game.prize_pool = generate_discrete_pool(game.total_pool)
        game.status = "GRABBING"
        
        return {"msg": "結算完畢，進入搶奪階段", "total_envelopes": len(game.prize_pool)}

@app.post("/grab")
def grab_envelope(req: GrabRequest):
    """階段 3：玩家搶紅包"""
    with state_lock:
        if game.status != "GRABBING":
            raise HTTPException(status_code=400, detail="目前無法搶奪紅包")
            
        player = game.players.get(req.user_id)
        if not player or player["tickets"] <= 0:
            raise HTTPException(status_code=400, detail="次數不足或未參與投注")

        if not game.prize_pool:
            game.status = "OPEN" # 搶完後重置回開放狀態 (簡化邏輯)
            raise HTTPException(status_code=400, detail="紅包已經被搶光了")

        # 扣除次數，取出紅包
        player["tickets"] -= 1
        won_amount = game.prize_pool.pop()
        player["won"] += won_amount

        return {
            "msg": "搶奪成功",
            "won_amount": won_amount,
            "tickets_left": player["tickets"],
            "total_won_so_far": player["won"]
        }