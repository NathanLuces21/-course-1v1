import os
import time
import threading
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cle-a-changer")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

PASSWORD = os.environ.get("GAME_PASSWORD", "COURSE2026")
players = {}
phase = "waiting"
countdown_end = 0
winner = None
lock = threading.RLock()
loop_started = False
HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Turbo Duo</title>
<style>
body{background:#11111b;color:white;font-family:Arial;text-align:center;padding:20px}
main{max-width:850px;margin:auto;background:#252532;padding:20px;border-radius:18px}
input,button{padding:12px;margin:6px;border:0;border-radius:8px}
button{background:#927cff;color:white;cursor:pointer}
canvas{width:100%;background:#18202d;border-radius:10px}
</style>
</head>
<body><main>
<h1>🏁 TURBO DUO</h1>
<div id="login">
<form id="join">
<input id="name" placeholder="Ton pseudo" maxlength="16" required>
<input id="pass" type="password" placeholder="Mot de passe" required>
<button>Rejoindre la course</button>
</form><p id="error"></p>
</div>
<div id="game" hidden>
<h2 id="status">En attente...</h2>
<canvas id="track" width="850" height="300"></canvas>
<p id="scores"></p>
<p>Maintiens le bouton pour courir !</p>
<button id="mobileRun"
style="width:90%;height:80px;font-size:24px;touch-action:none;">
🚀 AVANCER
</button>
<button id="restart">Rejouer</button>
</div>
</main>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script>
const socket=io();
let state=null,moving=false;
const $=id=>document.getElementById(id);
$("join").onsubmit=e=>{
 e.preventDefault();
 socket.emit("join_game",{name:$("name").value,password:$("pass").value});
};
socket.on("join_result",d=>{
 if(!d.ok){$("error").textContent=d.error;return}
 $("login").hidden=true;$("game").hidden=false;
});
function control(v){
 if(moving===v)return;moving=v;
 socket.emit("control",{right:v});
}
onkeydown=e=>{if(e.key==="ArrowRight"||e.key.toLowerCase()==="d"){e.preventDefault();control(true)}};
onkeyup=e=>{if(e.key==="ArrowRight"||e.key.toLowerCase()==="d")control(false)};
onblur=()=>control(false);
$("restart").onclick=()=>socket.emit("restart_game");
const mobileRun = $("mobileRun");

mobileRun.addEventListener("pointerdown", e => {
  e.preventDefault();
  control(true);
});

mobileRun.addEventListener("pointerup", e => {
  e.preventDefault();
  control(false);
});

mobileRun.addEventListener("pointercancel", () => control(false));
mobileRun.addEventListener("contextmenu", e => e.preventDefault());
socket.on("game_state",d=>{
 state=d;
 $("status").textContent=d.phase==="waiting"?"En attente d'un joueur...":
 d.phase==="countdown"?"Départ dans "+Math.ceil(d.countdown)+" !":
 d.phase==="racing"?"GO !":"🏆 "+(d.winner||"")+" gagne !";
 $("scores").textContent=d.players.map(p=>p?p.name+" : "+Math.floor(p.x-50)+" m":"En attente").join(" | ");
 draw();
});
function draw(){
 const c=$("track"),x=c.getContext("2d");
 x.clearRect(0,0,850,300);
 x.fillStyle="#18202d";x.fillRect(0,0,850,300);
 x.fillStyle="#29364a";x.fillRect(20,45,810,85);x.fillRect(20,170,810,85);
 x.strokeStyle="white";x.setLineDash([12,10]);x.beginPath();x.moveTo(20,150);x.lineTo(830,150);x.stroke();x.setLineDash([]);
 x.fillStyle="white";for(let y=45;y<255;y+=18){x.fillRect(790,y,12,9);x.fillRect(802,y+9,12,9)}
 if(!state)return;
 state.players.forEach((p,i)=>{
 if(!p)return;
 let y=i===0?95:220,col=i===0?"#a78bfa":"#38bdf8";
 x.fillStyle=col;x.beginPath();x.arc(p.x,y-17,9,0,7);x.fill();
 x.fillRect(p.x-7,y-8,14,20);
 x.strokeStyle=col;x.lineWidth=4;x.beginPath();
 x.moveTo(p.x-3,y+12);x.lineTo(p.x-10,y+22);
 x.moveTo(p.x+3,y+12);x.lineTo(p.x+10,y+22);x.stroke();
 x.fillStyle="white";x.font="13px Arial";x.fillText(p.name,p.x-25,y-32);
 });
}
</script>
</body></html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)


def send_state():
    with lock:
        data = {
            "phase": phase,
            "countdown": max(0, countdown_end - time.time()),
            "winner": winner,
            "players": [
                next(
                    (
                        {"name": p["name"], "x": p["x"]}
                        for p in players.values()
                        if p["slot"] == i
                    ),
                    None
                )
                for i in (0, 1)
            ]
        }
    socketio.emit("game_state", data)

def ensure_loop():
    global loop_started
    with lock:
        if loop_started:
            return
        loop_started = True
    socketio.start_background_task(loop)
@socketio.on("join_game")
def join(data):
    global phase,countdown_end,winner
    sid=request.sid
 ensure_loop()
    with lock:
        if data.get("password")!=PASSWORD:
            emit("join_result",{"ok":False,"error":"Mot de passe incorrect"})
            return
        if sid not in players:
            if len(players)>=2:
                emit("join_result",{"ok":False,"error":"La partie est complète"})
                return
            used=[p["slot"] for p in players.values()]
            slot=next(i for i in (0,1) if i not in used)
            players[sid]={"slot":slot,"name":str(data.get("name","Joueur"))[:16],"x":50.0,"right":False}
        else:
            slot=players[sid]["slot"]
        if len(players)==2 and phase=="waiting":
            phase="countdown";countdown_end=time.time()+3;winner=None
    emit("join_result",{"ok":True,"slot":slot})
    send_state()

@socketio.on("control")
def control(data):
    with lock:
        p=players.get(request.sid)
        if p:p["right"]=bool(data.get("right",False))

@socketio.on("restart_game")
def restart():
    global phase,countdown_end,winner
    with lock:
        if len(players)!=2 or phase!="finished":return
        for p in players.values():p.update(x=50.0,right=False)
        winner=None;phase="countdown";countdown_end=time.time()+3
    send_state()

@socketio.on("disconnect")
def leave():
    global phase,winner
    with lock:
        players.pop(request.sid,None)
        phase="waiting";winner=None
        for p in players.values():p.update(x=50.0,right=False)
    send_state()



def loop():
    global phase, winner, countdown_end

    while True:
        socketio.sleep(0.05)

        with lock:
            if phase == "countdown" and time.time() >= countdown_end:
                print("COMPTE A REBOURS TERMINE")
                phase = "racing"
                countdown_end = 0

            if phase == "racing":
                for p in players.values():
                    if p["right"]:
                        p["x"] = min(790, p["x"] + 3)

                        if p["x"] >= 790 and winner is None:
                            winner = p["name"]
                            phase = "finished"
                            break

        send_state()





if __name__=="__main__":
    socketio.run(app,host="0.0.0.0",port=10000)


