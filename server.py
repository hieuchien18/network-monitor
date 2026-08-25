import os
import time
import threading
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, jsonify, request, render_template_string


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# TIMEZONE VIETNAM
# ============================================================

VIETNAM_TZ = timezone(
    timedelta(hours=7)
)


def vietnam_now():
    return datetime.now(VIETNAM_TZ)


def format_time(dt):
    return dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ============================================================
# CONFIG
# ============================================================

# Lấy từ Render Environment
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
)

CHAT_ID = os.environ.get(
    "CHAT_ID",
    ""
)


# Client gửi heartbeat mỗi 10 giây
HEARTBEAT_INTERVAL = 10


# Không nhận heartbeat đủ 30 giây => OFFLINE
OFFLINE_TIMEOUT = 30


# Watchdog kiểm tra mỗi 1 giây
CHECK_INTERVAL = 1


# ============================================================
# MACHINE STORAGE
# ============================================================

machines = {}

machines_lock = threading.Lock()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN chưa được cấu hình"
        )

        return False


    if not CHAT_ID:

        print(
            "❌ CHAT_ID chưa được cấu hình"
        )

        return False


    try:

        url = (
            "https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )


        response = requests.post(

            url,

            json={
                "chat_id": CHAT_ID,
                "text": message
            },

            timeout=15

        )


        print(
            "📱 Telegram:",
            response.status_code,
            response.text
        )


        return response.ok


    except Exception as ex:

        print(
            "❌ Telegram ERROR:",
            ex
        )

        return False


# ============================================================
# HEARTBEAT
# ============================================================

@app.route(
    "/heartbeat",
    methods=["POST"]
)
def heartbeat():

    data = request.get_json(
        silent=True
    ) or {}


    machine_name = str(
        data.get(
            "machine_name",
            "Unknown"
        )
    ).strip()


    public_ip = str(
        data.get(
            "public_ip",
            "Unknown"
        )
    ).strip()


    if not machine_name:

        machine_name = "Unknown"


    now = vietnam_now()


    with machines_lock:

        # ====================================================
        # MÁY MỚI
        # ====================================================

        if machine_name not in machines:

            machines[machine_name] = {

                "last_seen": now,

                "online": True,

                "public_ip": public_ip,

                "offline_alert_sent": False,

                "offline_since": None

            }


            print(
                f"🟢 NEW MACHINE: "
                f"{machine_name}"
            )


            # Gửi ONLINE lần đầu
            online_message = (

                "🟢 MÁY ĐÃ ONLINE\n\n"

                f"🖥️ Máy:\n"
                f"{machine_name}\n\n"

                f"🌐 Public IP:\n"
                f"{public_ip}\n\n"

                f"🕒 Thời gian:\n"
                f"{format_time(now)}"

            )


            # Gửi sau khi nhả lock
            should_send_online = True


        else:

            machine = machines[
                machine_name
            ]


            should_send_online = False


            # =================================================
            # OFFLINE -> ONLINE
            # =================================================

            if not machine["online"]:

                offline_since = (
                    machine.get(
                        "offline_since"
                    )
                )


                if offline_since:

                    offline_duration = int(

                        (
                            now
                            -
                            offline_since
                        ).total_seconds()

                    )

                else:

                    offline_duration = 0


                machine["online"] = True

                machine[
                    "offline_alert_sent"
                ] = False

                machine[
                    "offline_since"
                ] = None


                online_message = (

                    "🟢 MÁY ĐÃ ONLINE TRỞ LẠI\n\n"

                    f"🖥️ Máy:\n"
                    f"{machine_name}\n\n"

                    f"🌐 Public IP:\n"
                    f"{public_ip}\n\n"

                    f"⏱️ Thời gian mất kết nối:\n"
                    f"{offline_duration} giây\n\n"

                    f"🕒 Có mạng lại:\n"
                    f"{format_time(now)}"

                )


                should_send_online = True


            # =================================================
            # UPDATE HEARTBEAT
            # =================================================

            machine["last_seen"] = now

            machine["public_ip"] = public_ip


    # ========================================================
    # Gửi Telegram ngoài lock
    # ========================================================

    if should_send_online:

        send_telegram(
            online_message
        )


    return jsonify({

        "status": "OK",

        "machine": machine_name,

        "time": format_time(now)

    })


# ============================================================
# STATUS API
# ============================================================

@app.route(
    "/api/status",
    methods=["GET"]
)
def api_status():

    now = vietnam_now()

    result = {}


    with machines_lock:

        for (
            name,
            machine
        ) in machines.items():


            seconds = int(

                (
                    now
                    -
                    machine["last_seen"]
                ).total_seconds()

            )


            # =================================================
            # QUAN TRỌNG:
            # TÍNH ONLINE/OFFLINE TRỰC TIẾP
            # =================================================

            if seconds >= OFFLINE_TIMEOUT:

                status = "OFFLINE"

            else:

                status = "ONLINE"


            result[name] = {

                "status": status,

                "last_seen":
                    format_time(
                        machine["last_seen"]
                    ),

                "seconds_since_last_heartbeat":
                    seconds,

                "public_ip":
                    machine["public_ip"]

            }


    return jsonify({

        "server": "RUNNING",

        "time":
            format_time(now),

        "offline_timeout":
            OFFLINE_TIMEOUT,

        "machines":
            result

    })


# ============================================================
# ROOT
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def dashboard():

    return render_template_string(
        """
<!DOCTYPE html>

<html lang="vi">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<title>
Network Monitor
</title>


<style>

* {
    box-sizing: border-box;
}


body {

    margin: 0;

    font-family:
        Arial,
        sans-serif;

    background:
        #f3f4f6;

    color:
        #111827;

}


.header {

    background:
        #111827;

    color:
        white;

    padding:
        22px 30px;

    font-size:
        26px;

    font-weight:
        bold;

}


.container {

    max-width:
        1200px;

    margin:
        auto;

    padding:
        25px;

}


.server-info {

    background:
        white;

    padding:
        20px;

    border-radius:
        15px;

    margin-bottom:
        25px;

    box-shadow:
        0 4px 15px
        rgba(0,0,0,.08);

}


.server-running {

    color:
        #16a34a;

    font-weight:
        bold;

}


.machine-grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(320px, 1fr)
        );

    gap:
        20px;

}


.machine {

    background:
        white;

    border-radius:
        18px;

    padding:
        25px;

    box-shadow:
        0 5px 20px
        rgba(0,0,0,.08);

    border-left:
        7px solid
        #16a34a;

}


.machine.offline {

    border-left:
        7px solid
        #dc2626;

}


.machine-name {

    font-size:
        23px;

    font-weight:
        bold;

    margin-bottom:
        18px;

}


.status {

    display:
        inline-block;

    padding:
        9px 18px;

    border-radius:
        30px;

    font-size:
        17px;

    font-weight:
        bold;

    margin-bottom:
        20px;

}


.status.online {

    background:
        #dcfce7;

    color:
        #166534;

}


.status.offline {

    background:
        #fee2e2;

    color:
        #991b1b;

}


.info {

    padding:
        12px 0;

    border-bottom:
        1px solid
        #e5e7eb;

}


.empty {

    text-align:
        center;

    background:
        white;

    padding:
        60px;

    border-radius:
        15px;

}


.refresh {

    text-align:
        center;

    color:
        #6b7280;

    margin-top:
        25px;

}


</style>

</head>


<body>


<div class="header">

📡 NETWORK MONITOR

</div>


<div class="container">


<div class="server-info">

    <div>

        ☁️ Server:

        <span
            class="server-running"
        >

            🟢 RUNNING

        </span>

    </div>


    <div
        id="serverTime"
        style="margin-top:10px;"
    >

        Loading...

    </div>


    <div
        style="margin-top:10px;"
    >

        🔴 Offline timeout:

        <b>30 giây</b>

    </div>

</div>


<div
    class="machine-grid"
    id="machineGrid"
>

    <div class="empty">

        Đang tải...

    </div>

</div>


<div class="refresh">

    🔄 Tự động cập nhật mỗi 1 giây

</div>


</div>


<script>


async function loadStatus() {

    try {

        const response =
            await fetch(
                "/api/status"
            );


        const data =
            await response.json();


        document.getElementById(
            "serverTime"
        ).innerHTML =

            "🕒 Giờ Việt Nam: "
            +
            data.time;


        const machines =
            data.machines;


        const grid =
            document.getElementById(
                "machineGrid"
            );


        let html = "";


        const names =
            Object.keys(
                machines
            );


        if (
            names.length === 0
        ) {

            grid.innerHTML = `

                <div class="empty">

                    🖥️ Chưa có máy nào kết nối

                </div>

            `;

            return;

        }


        for (
            const name
            of names
        ) {


            const machine =
                machines[name];


            const online =
                machine.status ===
                "ONLINE";


            html += `

                <div
                    class="
                        machine
                        ${online
                            ? ""
                            : "offline"
                        }
                    "
                >

                    <div
                        class="machine-name"
                    >

                        🖥️ ${name}

                    </div>


                    <div
                        class="
                            status
                            ${online
                                ? "online"
                                : "offline"
                            }
                        "
                    >

                        ${online
                            ? "🟢 ONLINE"
                            : "🔴 OFFLINE"
                        }

                    </div>


                    <div class="info">

                        🌐 Public IP:

                        <b>
                            ${machine.public_ip}
                        </b>

                    </div>


                    <div class="info">

                        🕒 Last Seen:

                        <b>
                            ${machine.last_seen}
                        </b>

                    </div>


                    <div class="info">

                        ⏱️ Heartbeat:

                        <b>
                            ${machine.seconds_since_last_heartbeat}
                            giây trước
                        </b>

                    </div>


                </div>

            `;

        }


        grid.innerHTML =
            html;


    }

    catch (error) {

        console.error(
            error
        );

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
    )


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    print(
        "🐕 WATCHDOG STARTED"
    )


    while True:

        try:

            now = vietnam_now()


            machines_to_notify = []


            with machines_lock:

                for (
                    machine_name,
                    machine
                ) in list(
                    machines.items()
                ):


                    seconds = int(

                        (
                            now
                            -
                            machine["last_seen"]
                        ).total_seconds()

                    )


                    # =========================================
                    # ONLINE -> OFFLINE
                    # =========================================

                    if (

                        machine["online"]

                        and

                        seconds >=
                        OFFLINE_TIMEOUT

                    ):


                        machine[
                            "online"
                        ] = False


                        machine[
                            "offline_alert_sent"
                        ] = True


                        machine[
                            "offline_since"
                        ] = now


                        last_seen =
                            machine[
                                "last_seen"
                            ]


                        machines_to_notify.append({

                            "machine_name":
                                machine_name,

                            "public_ip":
                                machine[
                                    "public_ip"
                                ],

                            "seconds":
                                seconds,

                            "last_seen":
                                last_seen,

                            "offline_time":
                                now

                        })


            # ====================================================
            # Gửi Telegram ngoài lock
            # ====================================================

            for info in machines_to_notify:


                message = (

                    "🔴 CẢNH BÁO MÁY OFFLINE\n\n"

                    f"🖥️ Máy:\n"
                    f"{info['machine_name']}\n\n"

                    f"🌐 Public IP cuối:\n"
                    f"{info['public_ip']}\n\n"

                    f"📡 Không nhận heartbeat:\n"
                    f"{info['seconds']} giây\n\n"

                    f"🕒 Heartbeat cuối:\n"
                    f"{format_time(info['last_seen'])}\n\n"

                    f"🔴 Phát hiện Offline:\n"
                    f"{format_time(info['offline_time'])}\n\n"

                    "⚠️ Có thể do:\n"
                    "• Mất Internet\n"
                    "• Tắt Wi-Fi/LAN\n"
                    "• Máy tính bị tắt\n"
                    "• Client.py bị dừng"

                )


                print(
                    f"🔴 OFFLINE: "
                    f"{info['machine_name']}"
                )


                send_telegram(
                    message
                )


        except Exception as ex:

            print(
                "❌ WATCHDOG ERROR:",
                ex
            )


        time.sleep(
            CHECK_INTERVAL
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
# START SERVER
# ============================================================

if __name__ == "__main__":

    port = int(

        os.environ.get(
            "PORT",
            10000
        )

    )


    print(
        "🚀 NETWORK MONITOR SERVER STARTED"
    )


    print(
        f"⏱️ Offline timeout: "
        f"{OFFLINE_TIMEOUT}s"
    )


    print(
        f"🔎 Watchdog check: "
        f"{CHECK_INTERVAL}s"
    )


    app.run(

        host="0.0.0.0",

        port=port

    )
