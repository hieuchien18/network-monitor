from flask import Flask, jsonify, request, render_template_string
import threading
import time
from datetime import datetime, timedelta, timezone
import os
import requests

app = Flask(__name__)

# ============================================================
# CONFIG
# ============================================================

OFFLINE_TIMEOUT = 30

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# Lưu thông tin máy
machines = {}

# Lock tránh lỗi khi nhiều request cùng truy cập
machines_lock = threading.Lock()

# Giờ Việt Nam UTC + 7
VN_TZ = timezone(timedelta(hours=7))


# ============================================================
# TIME
# ============================================================

def vn_now():
    return datetime.now(VN_TZ)


def vn_time_string():
    return vn_now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# TELEGRAM
# ============================================================

def telegram_configured():
    return bool(BOT_TOKEN and CHAT_ID)


def send_telegram(message):
    """
    Gửi tin nhắn Telegram.
    Không làm crash server nếu Telegram lỗi.
    """

    if not telegram_configured():
        return False, "BOT_TOKEN hoặc CHAT_ID chưa cấu hình"

    try:

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        data = {
            "chat_id": CHAT_ID,
            "text": message
        }

        response = requests.post(
            url,
            json=data,
            timeout=15
        )

        result = response.json()

        if response.status_code == 200 and result.get("ok"):

            return True, "Telegram gửi thành công"

        return False, str(result)

    except Exception as e:

        return False, str(e)


# ============================================================
# FORMAT TELEGRAM
# ============================================================

def telegram_online_message(machine_name, public_ip):

    return f"""🟢 MÁY ĐÃ ONLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{vn_time_string()}"""


def telegram_offline_message(machine_name, public_ip, last_seen):

    return f"""🔴 MÁY ĐÃ OFFLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Last Seen:
{last_seen}

⏱️ Offline timeout:
{OFFLINE_TIMEOUT} giây

📅 Thời gian phát hiện:
{vn_time_string()}"""


# ============================================================
# HEARTBEAT
# ============================================================

@app.route("/heartbeat", methods=["POST"])
def heartbeat():

    data = request.get_json(silent=True)

    if not data:
        data = request.form.to_dict()

    machine_name = data.get("machine")

    if not machine_name:
        machine_name = request.headers.get("X-Machine-Name")

    if not machine_name:
        return jsonify({
            "status": "ERROR",
            "message": "machine is required"
        }), 400

    machine_name = str(machine_name).strip().upper()

    public_ip = data.get("public_ip", "")

    if not public_ip:
        public_ip = request.remote_addr

    current_time = vn_now()

    need_send_online = False

    with machines_lock:

        # Máy chưa tồn tại
        if machine_name not in machines:

            machines[machine_name] = {
                "last_seen": current_time,
                "public_ip": public_ip,
                "status": "ONLINE",
                "telegram_online_sent": False,
                "telegram_offline_sent": False
            }

            need_send_online = True

        else:

            machine = machines[machine_name]

            old_status = machine.get("status", "OFFLINE")

            machine["last_seen"] = current_time
            machine["public_ip"] = public_ip
            machine["status"] = "ONLINE"

            # Nếu trước đó OFFLINE
            # bây giờ heartbeat lại => ONLINE
            if old_status == "OFFLINE":

                need_send_online = True

                machine["telegram_offline_sent"] = False

        if need_send_online:

            machines[machine_name]["telegram_online_sent"] = True

    # Gửi Telegram ngoài lock
    if need_send_online:

        send_telegram(
            telegram_online_message(
                machine_name,
                public_ip
            )
        )

    return jsonify({
        "status": "OK",
        "machine": machine_name,
        "time": vn_time_string()
    })


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    while True:

        time.sleep(1)

        current_time = vn_now()

        offline_messages = []

        with machines_lock:

            for machine_name, machine in machines.items():

                last_seen = machine.get("last_seen")

                if not last_seen:
                    continue

                seconds = (
                    current_time - last_seen
                ).total_seconds()

                # Quá timeout
                if seconds >= OFFLINE_TIMEOUT:

                    # Chỉ gửi Telegram 1 lần
                    if machine.get("status") != "OFFLINE":

                        machine["status"] = "OFFLINE"

                        machine["telegram_offline_sent"] = True

                        public_ip = machine.get(
                            "public_ip",
                            "Unknown"
                        )

                        offline_messages.append({
                            "machine": machine_name,
                            "public_ip": public_ip,
                            "last_seen": last_seen.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        })

        # Gửi ngoài lock
        for item in offline_messages:

            send_telegram(
                telegram_offline_message(
                    item["machine"],
                    item["public_ip"],
                    item["last_seen"]
                )
            )


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():

    current_time = vn_now()

    result = {}

    with machines_lock:

        for machine_name, machine in machines.items():

            last_seen = machine.get("last_seen")

            if not last_seen:
                continue

            seconds = int(
                (
                    current_time - last_seen
                ).total_seconds()
            )

            status = (
                "ONLINE"
                if seconds < OFFLINE_TIMEOUT
                else "OFFLINE"
            )

            result[machine_name] = {
                "last_seen": last_seen.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "public_ip": machine.get(
                    "public_ip",
                    "Unknown"
                ),
                "seconds_since_last_heartbeat": seconds,
                "status": status
            }

    return jsonify({
        "server": "RUNNING",
        "time": vn_time_string(),
        "offline_timeout": OFFLINE_TIMEOUT,
        "telegram": {
            "configured": telegram_configured(),
            "status": (
                "CONFIGURED"
                if telegram_configured()
                else "NOT CONFIGURED"
            )
        },
        "machines": result
    })


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route("/test-telegram", methods=["GET"])
def test_telegram():

    if not telegram_configured():

        return jsonify({
            "status": "ERROR",
            "message": "BOT_TOKEN hoặc CHAT_ID chưa cấu hình"
        }), 400

    message = f"""🧪 TEST TELEGRAM

✅ Network Monitor kết nối Telegram thành công.

🕒 Thời gian:
{vn_time_string()}"""

    success, result = send_telegram(message)

    return jsonify({
        "success": success,
        "message": result
    })


# ============================================================
# HOME UI
# ============================================================

HTML = """
<!DOCTYPE html>

<html lang="vi">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Network Monitor</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    font-family:Arial,sans-serif;
    background:#eef1f5;
    color:#1f2937;
}

.header{
    background:#111827;
    color:white;
    padding:25px;
}

.header h1{
    margin:0;
    font-size:30px;
}

.container{
    max-width:1150px;
    margin:auto;
    padding:25px;
}

.info{
    background:white;
    border-radius:18px;
    padding:22px;
    margin-bottom:25px;
    box-shadow:
        0 5px 20px rgba(0,0,0,.08);
}

.info-row{
    margin:10px 0;
    font-size:17px;
}

.dot{
    display:inline-block;
    width:16px;
    height:16px;
    border-radius:50%;
    margin-right:8px;
    vertical-align:middle;
}

.green{
    background:#16a34a;
    border:1px solid #087a2f;
}

.red{
    background:#dc2626;
    border:1px solid #991b1b;
}

.telegram-ok{
    color:#15803d;
    font-weight:bold;
}

.telegram-error{
    color:#dc2626;
    font-weight:bold;
}

.machine{
    background:white;
    border-radius:20px;
    padding:30px;
    margin-bottom:20px;
    border-left:7px solid #16a34a;
    box-shadow:
        0 5px 20px rgba(0,0,0,.08);
}

.machine.offline{
    border-left-color:#ef1111;
}

.machine h2{
    margin-top:0;
    font-size:26px;
}

.status{
    display:inline-flex;
    align-items:center;
    padding:12px 20px;
    border-radius:30px;
    font-weight:bold;
    margin-bottom:18px;
}

.status.online{
    background:#dcfce7;
    color:#166534;
}

.status.offline{
    background:#fee2e2;
    color:#991b1b;
}

.line{
    padding:13px 0;
    border-bottom:1px solid #e5e7eb;
    font-size:18px;
}

.no-machine{
    background:white;
    padding:40px;
    text-align:center;
    border-radius:20px;
    font-size:20px;
}

.button{
    display:inline-block;
    margin-top:10px;
    padding:10px 16px;
    background:#229ED9;
    color:white;
    border-radius:8px;
    text-decoration:none;
    font-weight:bold;
}

</style>

</head>

<body>

<div class="header">

    <h1>
        📡 NETWORK MONITOR
    </h1>

</div>


<div class="container">

    <div class="info">

        <div class="info-row">

            ☁️ Server:

            <span class="dot green"></span>

            <b>RUNNING</b>

        </div>


        <div class="info-row">

            🕒 Giờ Việt Nam:

            <b id="vnTime">
                Loading...
            </b>

        </div>


        <div class="info-row">

            🔴 Offline timeout:

            <b id="timeout">
                30 giây
            </b>

        </div>


        <div class="info-row">

            🤖 Telegram:

            <span id="telegramStatus">
                Checking...
            </span>

            <br>

            <a
                class="button"
                href="/test-telegram"
                target="_blank"
            >
                🧪 Test Telegram
            </a>

        </div>

    </div>


    <div id="machineList">

        <div class="no-machine">

            ⏳ Đang tải dữ liệu...

        </div>

    </div>


    <div
        style="
            text-align:center;
            color:#64748b;
            padding:10px;
        "
    >

        🔄 Tự động cập nhật mỗi 1 giây

    </div>

</div>


<script>

function escapeHtml(text){

    return String(text)
        .replace(/&/g,"&amp;")
        .replace(/</g,"&lt;")
        .replace(/>/g,"&gt;")
        .replace(/"/g,"&quot;")
        .replace(/'/g,"&#039;");

}


async function loadStatus(){

    try{

        const response =
            await fetch(
                "/api/status?t=" + Date.now()
            );

        const data =
            await response.json();


        document.getElementById(
            "vnTime"
        ).textContent =
            data.time;


        document.getElementById(
            "timeout"
        ).textContent =
            data.offline_timeout +
            " giây";


        const telegram =
            document.getElementById(
                "telegramStatus"
            );


        if(
            data.telegram &&
            data.telegram.configured
        ){

            telegram.innerHTML =
                "🟢 <span class='telegram-ok'>" +
                "ĐÃ CẤU HÌNH" +
                "</span>";

        }
        else{

            telegram.innerHTML =
                "🔴 <span class='telegram-error'>" +
                "CHƯA CẤU HÌNH" +
                "</span>";

        }


        const machineList =
            document.getElementById(
                "machineList"
            );


        const machines =
            data.machines || {};


        const names =
            Object.keys(machines);


        if(names.length === 0){

            machineList.innerHTML =

                `<div class="no-machine">
                    🖥️ Chưa có máy nào kết nối
                </div>`;

            return;

        }


        let html = "";


        names.forEach(function(name){

            const machine =
                machines[name];


            const isOnline =
                machine.status === "ONLINE";


            const statusClass =
                isOnline
                ? "online"
                : "offline";


            const machineClass =
                isOnline
                ? ""
                : "offline";


            const dotClass =
                isOnline
                ? "green"
                : "red";


            const seconds =
                machine.seconds_since_last_heartbeat;


            html += `

                <div
                    class="
                        machine
                        ${machineClass}
                    "
                >

                    <h2>
                        🖥️
                        ${escapeHtml(name)}
                    </h2>


                    <div
                        class="
                            status
                            ${statusClass}
                        "
                    >

                        <span
                            class="
                                dot
                                ${dotClass}
                            "
                        ></span>

                        ${machine.status}

                    </div>


                    <div class="line">

                        🌐 Public IP:

                        <b>
                            ${escapeHtml(
                                machine.public_ip
                            )}
                        </b>

                    </div>


                    <div class="line">

                        🕒 Last Seen:

                        <b>
                            ${machine.last_seen}
                        </b>

                    </div>


                    <div class="line">

                        ⏱️ Heartbeat:

                        <b>
                            ${seconds}
                            giây trước
                        </b>

                    </div>

                </div>

            `;

        });


        machineList.innerHTML =
            html;


    }
    catch(error){

        console.error(error);

    }

}


loadStatus();

setInterval(
    loadStatus,
    1000
);

</script>

</body>

</html>
"""


@app.route("/", methods=["GET"])
def home():

    return render_template_string(
        HTML
    )


# ============================================================
# START WATCHDOG
# ============================================================

watchdog_thread = threading.Thread(
    target=watchdog,
    daemon=True
)

watchdog_thread.start()


# ============================================================
# LOCAL RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
