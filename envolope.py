<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>搶紅包系統</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            overflow: hidden; /* 防止紅包掉出螢幕外產生捲軸 */
        }
        #app {
            width: 100%;
            max-width: 400px;
            height: 100vh;
            background-color: #fff;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            position: relative;
            text-align: center;
            display: flex;
            flex-direction: column;
        }
        .screen {
            display: none;
            flex: 1;
            padding: 20px;
            flex-direction: column;
            justify-content: center;
        }
        .active {
            display: flex;
        }
        h1 { color: #d32f2f; }
        input {
            padding: 10px;
            font-size: 16px;
            width: 80%;
            margin-bottom: 20px;
            text-align: center;
        }
        button {
            padding: 10px 20px;
            font-size: 18px;
            background-color: #d32f2f;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        button:disabled { background-color: #ccc; }
        
        /* 搶紅包介面專屬設定 */
        #game-area {
            position: relative;
            flex: 1;
            background-color: #ffebee;
            overflow: hidden;
            border-top: 2px solid #d32f2f;
            border-bottom: 2px solid #d32f2f;
        }
        .status-bar {
            padding: 10px;
            background: #fff;
            font-weight: bold;
        }
        
        /* 掉落的紅包 */
        .envelope {
            position: absolute;
            width: 50px;
            height: 70px;
            background-color: #d32f2f;
            color: gold;
            border-radius: 5px;
            display: flex;
            justify-content: center;
            align-items: center;
            font-weight: bold;
            cursor: pointer;
            user-select: none;
            /* 動畫設定 */
            animation: fall linear forwards;
        }
        @keyframes fall {
            from { top: -80px; }
            to { top: 100%; }
        }

        /* 結算浮動視窗 */
        #result-modal {
            display: none;
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 20px;
            border-radius: 10px;
            z-index: 100;
        }
    </style>
</head>
<body>

<div id="app">
    <div id="screen-bet" class="screen active">
        <h1>紅包大挑戰</h1>
        <p>每 100 元可獲得 1 次搶奪機會</p>
        <input type="number" id="bet-amount" placeholder="輸入投注金額 (100的倍數)" step="100" min="100">
        <button id="btn-bet" onclick="submitBet()">確認投注</button>
        <p id="bet-msg" style="color: red;"></p>
    </div>

    <div id="screen-wait" class="screen">
        <h1>等待開局...</h1>
        <p>伺服器正在結算總獎金池</p>
        <p>請勿關閉網頁</p>
    </div>

    <div id="screen-grab" class="screen" style="padding: 0;">
        <div class="status-bar">
            剩餘次數: <span id="display-tickets">0</span> | 已獲金額: <span id="display-won">0</span>
        </div>
        <div id="game-area">
            </div>
    </div>

    <div id="result-modal"></div>
</div>

<script>
    // --- 狀態變數 (前端暫存，實際應依賴後端) ---
    let myTickets = 0;
    let myTotalWon = 0;
    let gameInterval = null;
    let isGrabbing = false; // 防止連點 API

    // --- 畫面切換控制 ---
    function switchScreen(screenId) {
        document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));
        document.getElementById(screenId).classList.add('active');
    }

    // --- 階段 1: 提交投注 ---
    function submitBet() {
        const amountStr = document.getElementById('bet-amount').value;
        const amount = parseInt(amountStr, 10);
        const msgEl = document.getElementById('bet-msg');

        if (isNaN(amount) || amount <= 0 || amount % 100 !== 0) {
            msgEl.innerText = "請輸入 100 的正整數倍！";
            return;
        }

        document.getElementById('btn-bet').disabled = true;
        msgEl.innerText = "連線中...";

        // 模擬向 Server 發送 POST /bet
        setTimeout(() => {
            // 假設 Server 回傳成功，給予對應次數
            myTickets = amount / 100;
            myTotalWon = 0;
            updateStatusBar();
            
            // 進入等待結算畫面
            switchScreen('screen-wait');

            // 模擬 Server 經過 3 秒結算完畢，廣播「開始搶奪」
            setTimeout(() => {
                startGame();
            }, 3000);
            
        }, 1000);
    }

    // --- 階段 3: 遊戲開始 (開始掉落紅包) ---
    function startGame() {
        switchScreen('screen-grab');
        
        // 每 600 毫秒掉落一個紅包
        gameInterval = setInterval(createEnvelope, 600);
    }

    // --- 產生掉落的紅包元素 ---
    function createEnvelope() {
        if (myTickets <= 0) {
            clearInterval(gameInterval);
            return; // 次數用完就不再掉落 (或可繼續掉但不給點)
        }

        const area = document.getElementById('game-area');
        const env = document.createElement('div');
        env.className = 'envelope';
        env.innerText = '🧧';
        
        // 隨機水平位置 (扣除紅包本身寬度避免出界)
        const leftPos = Math.random() * (area.clientWidth - 50);
        env.style.left = leftPos + 'px';
        
        // 隨機掉落速度 (2秒到4秒之間)
        const duration = Math.random() * 2 + 2;
        env.style.animationDuration = duration + 's';

        // 點擊事件
        env.onclick = function() {
            grabEnvelope(env);
        };

        area.appendChild(env);

        // 動畫結束後自動移除 DOM 節點，避免記憶體洩漏
        setTimeout(() => {
            if(env.parentElement) env.remove();
        }, duration * 1000);
    }

    // --- 點擊紅包動作 ---
    function grabEnvelope(envElement) {
        if (myTickets <= 0 || isGrabbing) return;

        // 立刻讓該紅包消失且不可再點擊 (前端防護)
        envElement.style.pointerEvents = 'none';
        envElement.style.display = 'none';
        
        isGrabbing = true; // 鎖定狀態，等待 API 回應

        // 模擬向 Server 發送 POST /grab
        setTimeout(() => {
            // 模擬 Server 從獎池抽出的金額 (這裡用假資料)
            // 實際應由 Server 執行離散區塊切線段法並 pop()
            const wonAmount = (Math.floor(Math.random() * 5) + 1) * 10; 
            
            myTickets -= 1;
            myTotalWon += wonAmount;
            updateStatusBar();
            showResultText(`搶到 ${wonAmount} 元！`);

            isGrabbing = false;

            // 檢查是否結束
            if (myTickets <= 0) {
                endGame();
            }
        }, 300); // 模擬網路延遲 300ms
    }

    // --- 更新狀態列 ---
    function updateStatusBar() {
        document.getElementById('display-tickets').innerText = myTickets;
        document.getElementById('display-won').innerText = myTotalWon;
    }

    // --- 顯示中間的提示文字 ---
    function showResultText(text) {
        const modal = document.getElementById('result-modal');
        modal.innerText = text;
        modal.style.display = 'block';
        setTimeout(() => {
            modal.style.display = 'none';
        }, 1000);
    }

    // --- 遊戲結束 ---
    function endGame() {
        clearInterval(gameInterval);
        setTimeout(() => {
            alert(`遊戲結束！\n你總共獲得了 ${myTotalWon} 元`);
            // 重置狀態，允許重新開始 (實際應用中，這裡應該發送 API 重新獲取最新狀態)
            document.getElementById('btn-bet').disabled = false;
            document.getElementById('bet-msg').innerText = '';
            document.getElementById('bet-amount').value = '';
            document.getElementById('game-area').innerHTML = '';
            switchScreen('screen-bet');
        }, 1500);
    }
</script>

</body>
</html>