import os
import time
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request, render_template_string


app = Flask(__name__)


# ============================================================
# CONFIG
# ============================================================

OFFLINE_TIMEOUT = 30
CHECK_INTERVAL = 1

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

VN_TZ = timezone(timedelta(hours=7))

machines = {}

machines_lock = threading.Lock()


# ============================================================
# TIME
# ============================================================

def now_vn():

    return datetime.now(VN_TZ)


def format_time(dt):

    if dt is None:

        return ""

    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN:

        return False, "BOT_TOKEN is empty"

    if not CHAT_ID:

        return False, "CHAT_ID is empty"

    try:

        url = (
            "https://api.telegram.org/bot"
            + BOT_TOKEN
            + "/sendMessage"
        )

        response = requests.post(

            url,

            data={
                "chat_id": CHAT_ID,
                "text": message
            },

            timeout=10
        )

        print(
            "[TELEGRAM]",
            response.status_code,
            response.text
        )

        if response.status_code == 200:

            data = response.json()

            if data.get("ok") is True:

                return True, "Sent successfully"

        return False, response.text

    except Exception as e:

        print(
            "[TELEGRAM ERROR]",
            str(e)
        )

        return False, str(e)


# ============================================================
# TELEGRAM ONLINE
# ============================================================

def send_online_alert(machine_name, public_ip):

    message = f"""🟢 MÁY ĐÃ ONLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{format_time(now_vn())}
"""

    return send_telegram(message)


# ============================================================
# TELEGRAM OFFLINE
# ============================================================

def send_offline_alert(
    machine_name,
    public_ip,
    last_seen
):

    message = f"""🔴 MÁY ĐÃ MẤT KẾT NỐI

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Heartbeat cuối:
{format_time(last_seen)}

⏱️ Không nhận tín hiệu quá:
{OFFLINE_TIMEOUT} giây

🚨 Phát hiện lúc:
{format_time(now_vn())}
"""

    return send_telegram(message)


# ============================================================
# HEARTBEAT
# ============================================================

@app.route(
    "/heartbeat",
    methods=["POST"]
)
def heartbeat():

    try:

        data = request.get_json(
            silent=True
        )

        if not isinstance(data, dict):

            return jsonify({

                "status": "ERROR",

                "message":
                    "JSON body required"

            }), 400


        machine_name = str(
            data.get("machine", "")
        ).strip().upper()


        public_ip = str(
            data.get(
                "public_ip",
                ""
            )
        ).strip()


        if not machine_name:

            return jsonify({

                "status": "ERROR",

                "message":
                    "machine is required"

            }), 400


        if not public_ip:

            public_ip = (
                request.headers.get(
                    "X-Forwarded-For",
                    request.remote_addr
                )
                .split(",")[0]
                .strip()
            )


        current_time = now_vn()

        need_online_alert = False


        with machines_lock:


            # ------------------------------------------------
            # MÁY MỚI
            # ------------------------------------------------

            if machine_name not in machines:

                machines[machine_name] = {

                    "last_seen":
                        current_time,

                    "public_ip":
                        public_ip,

                    "status":
                        "ONLINE",

                    "offline_alert_sent":
                        False,

                    "last_telegram_result":
                        "",

                    "last_offline_alert":
                        None

                }

                need_online_alert = True


            # ------------------------------------------------
            # MÁY ONLINE LẠI
            # ------------------------------------------------

            else:

                machine = machines[
                    machine_name
                ]

                was_offline = (
                    machine.get("status")
                    == "OFFLINE"
                )


                machine[
                    "last_seen"
                ] = current_time


                machine[
                    "public_ip"
                ] = public_ip


                machine[
                    "status"
                ] = "ONLINE"


                if was_offline:

                    # Cho phép lần OFFLINE tiếp theo
                    # gửi Telegram lại

                    machine[
                        "offline_alert_sent"
                    ] = False


                    need_online_alert = True


        # ================================================
        # GỬI ONLINE NGOÀI LOCK
        # ================================================

        if need_online_alert:

            success, result = (
                send_online_alert(

                    machine_name,

                    public_ip
                )
            )

            with machines_lock:

                if machine_name in machines:

                    machines[
                        machine_name
                    ][
                        "last_telegram_result"
                    ] = result


        return jsonify({

            "status":
                "OK",

            "machine":
                machine_name,

            "time":
                format_time(
                    current_time
                )

        }), 200


    except Exception as e:

        print(
            "[HEARTBEAT ERROR]",
            str(e)
        )

        return jsonify({

            "status":
                "ERROR",

            "message":
                str(e)

        }), 500


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    print(
        "WATCHDOG STARTED"
    )

    while True:

        try:

            current_time = now_vn()

            send_list = []


            with machines_lock:

                for machine_name, machine in machines.items():

                    last_seen = machine.get(
                        "last_seen"
                    )

                    if last_seen is None:

                        continue


                    seconds_missing = int(

                        (
                            current_time
                            -
                            last_seen
                        ).total_seconds()

                    )


                    # =========================================
                    # QUÁ 30 GIÂY
                    # =========================================

                    if (
                        seconds_missing
                        >= OFFLINE_TIMEOUT
                    ):


                        if (
                            machine.get(
                                "status"
                            )
                            != "OFFLINE"
                        ):

                            print(
                                f"[OFFLINE DETECTED] "
                                f"{machine_name} | "
                                f"{seconds_missing}s"
                            )


                            machine[
                                "status"
                            ] = "OFFLINE"


                        # =====================================
                        # CHỈ GỬI 1 LẦN
                        # =====================================

                        if not machine.get(

                            "offline_alert_sent",

                            False

                        ):


                            # Đánh dấu ngay để tránh gửi lặp
                            # nhưng vẫn lưu kết quả Telegram

                            machine[
                                "offline_alert_sent"
                            ] = True


                            send_list.append({

                                "machine_name":
                                    machine_name,

                                "public_ip":
                                    machine.get(
                                        "public_ip",
                                        "Unknown"
                                    ),

                                "last_seen":
                                    last_seen

                            })


            # ================================================
            # GỬI TELEGRAM NGOÀI LOCK
            # ================================================

            for item in send_list:


                print(

                    "[SENDING OFFLINE ALERT]",

                    item[
                        "machine_name"
                    ]

                )


                success, result = (
                    send_offline_alert(

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
                )


                print(

                    "[OFFLINE TELEGRAM RESULT]",

                    success,

                    result

                )


                with machines_lock:

                    machine_name = item[
                        "machine_name"
                    ]


                    if machine_name in machines:


                        machines[
                            machine_name
                        ][
                            "last_telegram_result"
                        ] = result


                        if success:

                            machines[
                                machine_name
                            ][
                                "last_offline_alert"
                            ] = now_vn()


                        else:

                            # Nếu gửi lỗi thì cho phép
                            # watchdog thử lại

                            machines[
                                machine_name
                            ][
                                "offline_alert_sent"
                            ] = False


        except Exception as e:

            print(

                "[WATCHDOG ERROR]",

                str(e)

            )


        time.sleep(
            CHECK_INTERVAL
        )


# ============================================================
# API STATUS
# ============================================================

@app.route(
    "/api/status",
    methods=["GET"]
)
def api_status():

    current_time = now_vn()

    result = {}


    with machines_lock:

        for machine_name, machine in machines.items():

            last_seen = machine.get(
                "last_seen"
            )


            seconds_missing = 0


            if last_seen:

                seconds_missing = int(

                    (
                        current_time
                        -
                        last_seen
                    ).total_seconds()

                )


            status = machine.get(
                "status",
                "UNKNOWN"
            )


            result[machine_name] = {

                "status":
                    status,

                "public_ip":
                    machine.get(
                        "public_ip",
                        "Unknown"
                    ),

                "last_seen":
                    format_time(
                        last_seen
                    ),

                "seconds_since_last_heartbeat":
                    seconds_missing,

                "offline_alert_sent":
                    machine.get(
                        "offline_alert_sent",
                        False
                    ),

                "last_offline_alert":
                    format_time(

                        machine.get(
                            "last_offline_alert"
                        )

                    ),

                "last_telegram_result":
                    machine.get(
                        "last_telegram_result",
                        ""
                    )

            }


    return jsonify({

        "server":
            "RUNNING",

        "time":
            format_time(
                current_time
            ),

        "offline_timeout":
            OFFLINE_TIMEOUT,

        "telegram_configured":
            bool(
                BOT_TOKEN
                and
                CHAT_ID
            ),

        "machines":
            result

    })


# ============================================================
# TEST TELEGRAM
# ============================================================

@app.route(
    "/test-telegram",
    methods=["GET"]
)
def test_telegram():

    success, result = send_telegram(

        f"""🧪 TEST TELEGRAM

✅ Network Monitor kết nối Telegram thành công.

🕒 Thời gian:
{format_time(now_vn())}
"""

    )


    return jsonify({

        "success":
            success,

        "result":
            result

    })


# ============================================================
# WEB
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return render_template_string(

        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1"
>

<title>
Network Monitor
</title>

<style>

body{

    font-family:
        Arial;

    background:
        #f3f4f6;

    margin:0;

    padding:20px;

}

.card{

    background:white;

    padding:20px;

    margin-bottom:15px;

    border-radius:12px;

}

.online{

    border-left:
        7px solid green;

}

.offline{

    border-left:
        7px solid red;

}

.row{

    padding:8px;

    border-bottom:
        1px solid #ddd;

}

</style>

</head>

<body>

<h1>
📡 NETWORK MONITOR
</h1>

<div id="app">

Đang tải...

</div>


<script>

async function loadData(){

    const response =
        await fetch(
            "/api/status?t="
            +
            Date.now()
        );


    const data =
        await response.json();


    let html = `

<div class="card">

🟢 Server:
<b>${data.server}</b>

<br><br>

🕒 ${data.time}

<br><br>

🤖 Telegram:

<b>

${

data.telegram_configured

? "🟢 ĐÃ CẤU HÌNH"

: "🔴 CHƯA CẤU HÌNH"

}

</b>

</div>

`;


    for(

        const name

        in data.machines

    ){


        const m =
            data.machines[name];


        html += `

<div class="card ${

m.status === "ONLINE"

? "online"

: "offline"

}">

<h2>

🖥️ ${name}

</h2>

<div class="row">

📡 Status:

<b>

${m.status}

</b>

</div>

<div class="row">

🌐 IP:

${m.public_ip}

</div>

<div class="row">

🕒 Last Seen:

${m.last_seen}

</div>

<div class="row">

⏱️ Mất heartbeat:

${m.seconds_since_last_heartbeat}
giây

</div>

<div class="row">

📨 Đã gửi OFFLINE:

${

m.offline_alert_sent

? "YES"

: "NO"

}

</div>

<div class="row">

🤖 Telegram Result:

${m.last_telegram_result}

</div>

</div>

`;

    }


    document.getElementById(
        "app"
    ).innerHTML =
        html;

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
    )


# ============================================================
# START WATCHDOG
# ============================================================

threading.Thread(

    target=watchdog,

    daemon=True

).start()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=int(

            os.environ.get(

                "PORT",

                5000

            )

        )

    )
