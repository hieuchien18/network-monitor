import os
import time
import threading
import requests

from flask import Flask, jsonify, request, render_template_string
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================

OFFLINE_TIMEOUT = 30
CHECK_INTERVAL = 2

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

# Giờ Việt Nam UTC+7
VN_TZ = timezone(timedelta(hours=7))

machines = {}

machines_lock = threading.Lock()


# =========================================================
# TIME
# =========================================================

def now_vn():

    return datetime.now(VN_TZ)


def format_time(dt):

    if not dt:
        return ""

    return dt.strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    print("")

    print("=" * 60)

    print("📨 TELEGRAM SEND")

    print(f"BOT_TOKEN: {'OK' if BOT_TOKEN else 'EMPTY'}")

    print(f"CHAT_ID: {'OK' if CHAT_ID else 'EMPTY'}")

    print(message)

    print("=" * 60)

    if not BOT_TOKEN or not CHAT_ID:

        print("❌ TELEGRAM CHƯA CẤU HÌNH BOT_TOKEN HOẶC CHAT_ID")

        return False

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        data = {
            "chat_id": CHAT_ID,
            "text": message
        }

        response = requests.post(
            url,
            data=data,
            timeout=15
        )

        print(f"Telegram HTTP: {response.status_code}")

        print(
            f"Telegram Response: "
            f"{response.text}"
        )

        if response.status_code == 200:

            print("✅ TELEGRAM GỬI THÀNH CÔNG")

            return True

        print("❌ TELEGRAM GỬI THẤT BẠI")

        return False

    except Exception as e:

        print(f"❌ TELEGRAM ERROR: {e}")

        return False


# =========================================================
# SEND ONLINE
# =========================================================

def send_online(machine_name, public_ip):

    message = f"""🟢 MÁY ĐÃ ONLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{format_time(now_vn())}
"""

    return send_telegram(message)


# =========================================================
# SEND OFFLINE
# =========================================================

def send_offline(machine_name, public_ip, last_seen):

    message = f"""🔴 MÁY ĐÃ OFFLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Mất kết nối lúc:
{format_time(last_seen)}

⏱️ Không nhận heartbeat quá:
{OFFLINE_TIMEOUT} giây

📅 Thời gian phát hiện:
{format_time(now_vn())}
"""

    return send_telegram(message)


# =========================================================
# HEARTBEAT
# =========================================================

@app.route("/heartbeat", methods=["POST"])
def heartbeat():

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "status": "ERROR",
                "message": "Invalid JSON"
            }), 400

        machine_name = (
            data.get("machine")
            or data.get("hostname")
            or ""
        ).strip()

        public_ip = (
            data.get("public_ip")
            or request.remote_addr
        ).strip()

        if not machine_name:

            return jsonify({
                "status": "ERROR",
                "message": "machine is required"
            }), 400

        current_time = now_vn()

        need_send_online = False

        with machines_lock:

            if machine_name not in machines:

                print(
                    f"[NEW MACHINE] "
                    f"{machine_name}"
                )

                machines[machine_name] = {

                    "last_seen": current_time,

                    "public_ip": public_ip,

                    "status": "ONLINE",

                    "offline_notified": False,

                    "online_notified": False
                }

                need_send_online = True

            else:

                machine = machines[machine_name]

                was_offline = (
                    machine.get("status")
                    == "OFFLINE"
                )

                machine["last_seen"] = (
                    current_time
                )

                machine["public_ip"] = (
                    public_ip
                )

                machine["status"] = "ONLINE"

                machine["offline_notified"] = False

                if was_offline:

                    need_send_online = True

                elif not machine.get(
                    "online_notified",
                    False
                ):

                    need_send_online = True

        # Gửi Telegram ngoài lock
        if need_send_online:

            success = send_online(
                machine_name,
                public_ip
            )

            with machines_lock:

                if machine_name in machines:

                    machines[machine_name][
                        "online_notified"
                    ] = success

        return jsonify({

            "status": "OK",

            "machine": machine_name,

            "time": format_time(
                current_time
            )

        }), 200

    except Exception as e:

        print(
            f"[HEARTBEAT ERROR] {e}"
        )

        return jsonify({

            "status": "ERROR",

            "message": str(e)

        }), 500


# =========================================================
# WATCHDOG
# =========================================================

def watchdog():

    print(
        "🛡️ WATCHDOG STARTED"
    )

    while True:

        try:

            current_time = now_vn()

            offline_list = []

            with machines_lock:

                for machine_name, machine in machines.items():

                    last_seen = machine.get(
                        "last_seen"
                    )

                    if not last_seen:

                        continue

                    seconds_offline = (
                        current_time -
                        last_seen
                    ).total_seconds()

                    # Quá 30 giây
                    if (
                        seconds_offline >
                        OFFLINE_TIMEOUT
                    ):

                        # Chỉ gửi 1 lần
                        if not machine.get(
                            "offline_notified",
                            False
                        ):

                            print("")

                            print(
                                "🚨 OFFLINE DETECTED"
                            )

                            print(
                                f"Machine: "
                                f"{machine_name}"
                            )

                            print(
                                f"Seconds: "
                                f"{int(seconds_offline)}"
                            )

                            machine[
                                "status"
                            ] = "OFFLINE"

                            machine[
                                "offline_notified"
                            ] = True

                            machine[
                                "online_notified"
                            ] = False

                            offline_list.append({

                                "machine_name":
                                    machine_name,

                                "public_ip":
                                    machine.get(
                                        "public_ip",
                                        ""
                                    ),

                                "last_seen":
                                    last_seen
                            })

                    else:

                        machine[
                            "status"
                        ] = "ONLINE"

            # Gửi Telegram ngoài lock
            for item in offline_list:

                send_offline(

                    item[
                        "machine_name"
                    ],

                    item[
                        "public_ip"
                    ],

                    item[
                        "last_seen"
                    ]
                )

        except Exception as e:

            print(
                f"[WATCHDOG ERROR] {e}"
            )

        time.sleep(
            CHECK_INTERVAL
        )


# =========================================================
# API STATUS
# =========================================================

@app.route("/api/status", methods=["GET"])
def api_status():

    current_time = now_vn()

    result = {}

    with machines_lock:

        for name, machine in machines.items():

            last_seen = machine.get(
                "last_seen"
            )

            seconds = 0

            if last_seen:

                seconds = int(
                    (
                        current_time -
                        last_seen
                    ).total_seconds()
                )

            status = "ONLINE"

            if seconds > OFFLINE_TIMEOUT:

                status = "OFFLINE"

            result[name] = {

                "status": status,

                "public_ip":
                    machine.get(
                        "public_ip",
                        ""
                    ),

                "last_seen":
                    format_time(
                        last_seen
                    ),

                "seconds_since_last_heartbeat":
                    seconds,

                "offline_notified":
                    machine.get(
                        "offline_notified",
                        False
                    )
            }

    return jsonify({

        "server": "RUNNING",

        "time": format_time(
            current_time
        ),

        "offline_timeout":
            OFFLINE_TIMEOUT,

        "machines": result
    })


# =========================================================
# TEST TELEGRAM
# =========================================================

@app.route(
    "/test-telegram",
    methods=["GET"]
)
def test_telegram():

    message = f"""🧪 TEST TELEGRAM

✅ Network Monitor kết nối Telegram thành công.

🕒 Thời gian:
{format_time(now_vn())}
"""

    success = send_telegram(
        message
    )

    return jsonify({

        "success": success,

        "bot_configured":
            bool(BOT_TOKEN),

        "chat_configured":
            bool(CHAT_ID)
    })


# =========================================================
# WEB UI
# =========================================================

@app.route("/", methods=["GET"])
def index():

    html = """
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

body {

    margin: 0;

    font-family:
        Arial,
        sans-serif;

    background:
        #f3f4f6;

}

.header {

    background:
        #172033;

    color:
        white;

    padding:
        25px;

    font-size:
        32px;

    font-weight:
        bold;

}

.container {

    max-width:
        1100px;

    margin:
        auto;

    padding:
        25px;

}

.info {

    background:
        white;

    padding:
        20px;

    border-radius:
        15px;

    margin-bottom:
        20px;

}

.machine {

    background:
        white;

    border-radius:
        18px;

    padding:
        25px;

    margin-bottom:
        20px;

    border-left:
        8px solid green;

}

.machine.offline {

    border-left-color:
        red;

}

.status {

    font-size:
        24px;

    font-weight:
        bold;

    margin:
        15px 0;

}

.online {

    color:
        green;

}

.offline {

    color:
        red;

}

.row {

    padding:
        12px 0;

    border-bottom:
        1px solid #ddd;

}

</style>

</head>

<body>

<div class="header">

📡 NETWORK MONITOR

</div>

<div class="container">

<div
class="info"
id="serverInfo"
>

Đang tải...

</div>

<div
id="machines"
>

</div>

</div>

<script>

async function loadData() {

    try {

        const response =
            await fetch(
                "/api/status"
            );

        const data =
            await response.json();

        document
            .getElementById(
                "serverInfo"
            )
            .innerHTML = `

<b>☁️ Server:</b>
🟢 ${data.server}

<br><br>

<b>🕒 Giờ Việt Nam:</b>
${data.time}

<br><br>

<b>🔴 Offline timeout:</b>
${data.offline_timeout} giây

`;

        let html = "";

        for (
            const name
            in data.machines
        ) {

            const m =
                data.machines[name];

            const isOffline =
                m.status === "OFFLINE";

            html += `

<div
class="machine ${
    isOffline
    ? "offline"
    : ""
}"
>

<h2>

🖥️ ${name}

</h2>

<div
class="status ${
    isOffline
    ? "offline"
    : "online"
}"
>

${
    isOffline
    ? "🔴 OFFLINE"
    : "🟢 ONLINE"
}

</div>

<div class="row">

🌐 Public IP:
<b>${m.public_ip}</b>

</div>

<div class="row">

🕒 Last Seen:
<b>${m.last_seen}</b>

</div>

<div class="row">

⏱️ Heartbeat:
<b>
${m.seconds_since_last_heartbeat}
giây trước
</b>

</div>

<div class="row">

📨 Telegram Offline:
<b>
${
    m.offline_notified
    ? "ĐÃ GỬI"
    : "CHƯA GỬI"
}
</b>

</div>

</div>

`;

        }

        document
            .getElementById(
                "machines"
            )
            .innerHTML = html;

    }
    catch (error) {

        console.log(error);

    }

}

loadData();

setInterval(
    loadData,
    1000
);

</script>

</body>

</html>
"""

    return render_template_string(
        html
    )


# =========================================================
# START WATCHDOG
# =========================================================

watchdog_thread = threading.Thread(

    target=watchdog,

    daemon=True

)

watchdog_thread.start()


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000

    )
