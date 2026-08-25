import os
import time
import threading
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, jsonify, request, render_template_string


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


# ============================================================
# VIETNAM TIME UTC + 7
# ============================================================

VN_TZ = timezone(
    timedelta(hours=7)
)


def get_vietnam_time():

    return datetime.now(VN_TZ)


# ============================================================
# CONFIG
# ============================================================

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


# Quá 30 giây không nhận heartbeat -> OFFLINE
OFFLINE_TIMEOUT = 30


# Server kiểm tra mỗi 5 giây
CHECK_INTERVAL = 5


# ============================================================
# MACHINE DATA
# ============================================================

machines = {}


# ============================================================
# SEND TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "❌ BOT_TOKEN hoặc CHAT_ID "
            "chưa được cấu hình"
        )

        return False

    try:

        url = (
            f"https://api.telegram.org/"
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
            "❌ TELEGRAM ERROR:",
            ex
        )

        return False


# ============================================================
# HEARTBEAT API
# ============================================================

@app.route(
    "/heartbeat",
    methods=["POST"]
)
def heartbeat():

    data = request.get_json(
        silent=True
    ) or {}


    machine_name = data.get(
        "machine_name",
        "Unknown"
    )


    public_ip = data.get(
        "public_ip",
        "Unknown"
    )


    # Giờ Việt Nam
    now = get_vietnam_time()


    # ========================================================
    # MÁY CHƯA TỒN TẠI
    # ========================================================

    if machine_name not in machines:


        machines[machine_name] = {

            "last_seen":
                now,

            "online":
                True,

            "public_ip":
                public_ip,

            "offline_alert_sent":
                False

        }


        print(

            f"🟢 NEW MACHINE: "
            f"{machine_name}"

        )


        # Gửi thông báo máy online lần đầu
        send_telegram(

            f"🟢 MÁY ĐÃ ONLINE\n\n"

            f"🖥️ Máy:\n"
            f"{machine_name}\n\n"

            f"🌐 Public IP:\n"
            f"{public_ip}\n\n"

            f"🕒 Thời gian:\n"
            f"{now.strftime('%Y-%m-%d %H:%M:%S')}"

        )


    else:


        machine = machines[
            machine_name
        ]


        # ====================================================
        # OFFLINE -> ONLINE
        # ====================================================

        if not machine["online"]:


            offline_time = int(

                (
                    now
                    -
                    machine["last_seen"]
                ).total_seconds()

            )


            machine[
                "online"
            ] = True


            machine[
                "offline_alert_sent"
            ] = False


            print(

                f"🟢 MACHINE BACK ONLINE: "
                f"{machine_name}"

            )


            send_telegram(

                f"🟢 MÁY ĐÃ ONLINE TRỞ LẠI\n\n"

                f"🖥️ Máy:\n"
                f"{machine_name}\n\n"

                f"🌐 Public IP:\n"
                f"{public_ip}\n\n"

                f"⏱️ Thời gian mất kết nối:\n"
                f"{offline_time} giây\n\n"

                f"🕒 Có mạng lại:\n"
                f"{now.strftime('%Y-%m-%d %H:%M:%S')}"

            )


        # ====================================================
        # UPDATE HEARTBEAT
        # ====================================================

        machine[
            "last_seen"
        ] = now


        machine[
            "public_ip"
        ] = public_ip


    return jsonify({

        "status":
            "OK",

        "machine":
            machine_name,

        "time":
            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

    })


# ============================================================
# STATUS API
# ============================================================

@app.route(
    "/api/status",
    methods=["GET"]
)
def api_status():

    result = {}


    now = get_vietnam_time()


    for (
        name,
        machine
    ) in machines.items():


        seconds = int(

            (

                now

                -

                machine[
                    "last_seen"
                ]

            ).total_seconds()

        )


        if machine["online"]:

            status = "ONLINE"

        else:

            status = "OFFLINE"


        result[name] = {

            "status":
                status,


            "last_seen":

                machine[
                    "last_seen"
                ].strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),


            "seconds_since_last_heartbeat":
                seconds,


            "public_ip":

                machine[
                    "public_ip"
                ]

        }


    return jsonify({

        "server":
            "RUNNING",

        "time":

            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

        "machines":
            result

    })


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    print(
        "🐕 WATCHDOG STARTED"
    )


    while True:


        try:


            # Giờ Việt Nam
            now = get_vietnam_time()


            for (

                machine_name,
                machine

            ) in list(

                machines.items()

            ):


                seconds_offline = int(

                    (

                        now

                        -

                        machine[
                            "last_seen"
                        ]

                    ).total_seconds()

                )


                # ============================================
                # QUÁ 30 GIÂY KHÔNG CÓ HEARTBEAT
                # ============================================

                if (

                    machine["online"]

                    and

                    seconds_offline
                    >=
                    OFFLINE_TIMEOUT

                ):


                    print(

                        f"🔴 MACHINE OFFLINE: "
                        f"{machine_name}"

                    )


                    machine[
                        "online"
                    ] = False


                    machine[
                        "offline_alert_sent"
                    ] = True


                    last_seen = machine[
                        "last_seen"
                    ]


                    send_telegram(

                        f"🔴 CẢNH BÁO MÁY OFFLINE\n\n"

                        f"🖥️ Máy:\n"
                        f"{machine_name}\n\n"

                        f"🌐 Public IP cuối:\n"
                        f"{machine['public_ip']}\n\n"

                        f"📡 Không nhận heartbeat:\n"
                        f"{seconds_offline} giây\n\n"

                        f"🕒 Lần cuối Online:\n"
                        f"{last_seen.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                        f"🕒 Phát hiện Offline:\n"
                        f"{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                        f"⚠️ Có thể do:\n"
                        f"• Mất Internet\n"
                        f"• Tắt Wi-Fi/LAN\n"
                        f"• Máy tính bị tắt\n"
                        f"• Client.py bị dừng"

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
# DASHBOARD
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
    content="width=device-width, initial-scale=1.0"
>

<title>
Network Monitor
</title>


<style>

* {

    box-sizing:
        border-box;

}


body {

    margin:
        0;

    font-family:

        Arial,
        sans-serif;

    background:

        #f3f4f6;

}


header {

    background:

        #111827;

    color:

        white;

    padding:

        20px;

    font-size:

        24px;

    font-weight:

        bold;

}


.container {

    max-width:

        1200px;

    margin:

        auto;

    padding:

        30px;

}


.grid {

    display:

        grid;

    grid-template-columns:

        repeat(
            auto-fit,
            minmax(300px, 1fr)
        );

    gap:

        20px;

}


.card {

    background:

        white;

    border-radius:

        15px;

    padding:

        25px;

    box-shadow:

        0 4px 15px
        rgba(0,0,0,.08);

}


.online {

    border-left:

        7px solid green;

}


.offline {

    border-left:

        7px solid red;

}


.status {

    font-size:

        20px;

    font-weight:

        bold;

}


.time {

    color:

        #666;

    margin-bottom:

        20px;

}

</style>

</head>


<body>


<header>

📡 NETWORK MONITOR

</header>


<div class="container">


    <h3
        id="serverTime"
        class="time"
    >

        Loading...

    </h3>


    <div
        class="grid"
        id="machines"
    >

        Loading...

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


        const machines =

            data.machines;


        document.getElementById(
            "serverTime"
        ).innerHTML =

            "🕒 Giờ Việt Nam: "
            +
            data.time;


        let html = "";


        for (

            const name

            in

            machines

        ) {


            const machine =

                machines[name];


            const status =

                machine.status;


            const css =

                status === "ONLINE"

                ?

                "online"

                :

                "offline";


            html += `

            <div
                class="
                    card
                    ${css}
                "
            >


                <h2>

                    🖥️ ${name}

                </h2>


                <p
                    class="status"
                >

                    ${

                        status === "ONLINE"

                        ?

                        "🟢 ONLINE"

                        :

                        "🔴 OFFLINE"

                    }

                </p>


                <p>

                    🌐 Public IP:

                    ${machine.public_ip}

                </p>


                <p>

                    🕒 Last Seen:

                    ${machine.last_seen}

                </p>


                <p>

                    ⏱️

                    ${machine.seconds_since_last_heartbeat}

                    giây trước

                </p>


            </div>

            `;

        }


        if (

            html === ""

        ) {


            html =

                "<h2>⚠️ Chưa có máy nào kết nối</h2>";

        }


        document.getElementById(
            "machines"
        ).innerHTML =

            html;


    }


    catch (error) {


        console.log(
            error
        );


    }


}


loadData();


setInterval(

    loadData,

    5000

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
# START SERVER
# ============================================================

if __name__ == "__main__":


    port = int(

        os.environ.get(

            "PORT",

            10000

        )

    )


    app.run(

        host="0.0.0.0",

        port=port

    )
