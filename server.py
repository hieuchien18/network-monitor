import os
import time
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request, render_template_string


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# CONFIG
# ============================================================

OFFLINE_TIMEOUT = 30
CHECK_INTERVAL = 1


# ============================================================
# TELEGRAM
#
# CẤU HÌNH TRÊN RENDER:
#
# BOT_TOKEN = token bot Telegram
# CHAT_ID   = chat id Telegram
#
# Không cần ghi token trực tiếp vào code.
# ============================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
).strip()


CHAT_ID = os.environ.get(
    "CHAT_ID",
    ""
).strip()


# ============================================================
# VIETNAM TIMEZONE
# ============================================================

VN_TZ = timezone(
    timedelta(hours=7)
)


# ============================================================
# MACHINE STORAGE
# ============================================================

machines = {}

machines_lock = threading.Lock()


# ============================================================
# TIME
# ============================================================

def now_vn():

    return datetime.now(
        VN_TZ
    )


def format_time(dt):

    if dt is None:
        return ""

    return dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def seconds_since(dt):

    if dt is None:
        return 999999

    return max(
        0,
        int(
            (
                now_vn() - dt
            ).total_seconds()
        )
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN:

        print(
            "[TELEGRAM] BOT_TOKEN EMPTY"
        )

        return False, "BOT_TOKEN is empty"


    if not CHAT_ID:

        print(
            "[TELEGRAM] CHAT_ID EMPTY"
        )

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

                "chat_id":
                    CHAT_ID,

                "text":
                    message

            },

            timeout=15

        )


        print(
            "[TELEGRAM]",
            response.status_code,
            response.text
        )


        try:

            result = response.json()

        except Exception:

            result = {
                "ok": False,
                "description":
                    response.text
            }


        if (

            response.status_code == 200

            and

            result.get("ok") is True

        ):

            return (
                True,
                "Telegram sent successfully"
            )


        return (
            False,
            response.text
        )


    except Exception as e:

        print(
            "[TELEGRAM ERROR]",
            str(e)
        )

        return (
            False,
            str(e)
        )


# ============================================================
# ONLINE TELEGRAM
# ============================================================

def send_online_alert(
    machine_name,
    public_ip
):

    message = f"""🟢 MÁY ĐÃ ONLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{format_time(now_vn())}
"""


    return send_telegram(
        message
    )


# ============================================================
# OFFLINE TELEGRAM
# ============================================================

def send_offline_alert(
    machine_name,
    public_ip,
    last_seen,
    seconds_missing
):

    message = f"""🔴 MÁY ĐÃ MẤT KẾT NỐI

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Heartbeat cuối:
{format_time(last_seen)}

⏱️ Không nhận tín hiệu:
{seconds_missing} giây

🚨 Phát hiện lúc:
{format_time(now_vn())}
"""


    return send_telegram(
        message
    )


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


        if not isinstance(
            data,
            dict
        ):

            return jsonify({

                "status":
                    "ERROR",

                "message":
                    "JSON body required"

            }), 400


        # ====================================================
        # MACHINE
        # ====================================================

        machine_name = str(

            data.get(
                "machine",
                ""
            )

        ).strip().upper()


        if not machine_name:

            return jsonify({

                "status":
                    "ERROR",

                "message":
                    "machine is required"

            }), 400


        # ====================================================
        # PUBLIC IP
        # ====================================================

        public_ip = str(

            data.get(
                "public_ip",
                ""
            )

        ).strip()


        if not public_ip:

            forwarded = request.headers.get(
                "X-Forwarded-For"
            )


            if forwarded:

                public_ip = (
                    forwarded
                    .split(",")[0]
                    .strip()
                )

            else:

                public_ip = (
                    request.remote_addr
                    or
                    "UNKNOWN"
                )


        current_time = now_vn()


        send_online = False


        # ====================================================
        # UPDATE MACHINE
        # ====================================================

        with machines_lock:


            # =================================================
            # MACHINE MỚI
            # =================================================

            if machine_name not in machines:

                print(
                    f"[NEW MACHINE] "
                    f"{machine_name}"
                )


                machines[machine_name] = {

                    "last_seen":
                        current_time,

                    "public_ip":
                        public_ip,

                    "status":
                        "ONLINE",

                    "offline_alert_sent":
                        False,

                    "last_offline_alert":
                        None,

                    "last_online_alert":
                        None,

                    "last_telegram_result":
                        "",

                    "online_alert_sent":
                        False

                }


                send_online = True


            # =================================================
            # MACHINE CŨ
            # =================================================

            else:

                machine = machines[
                    machine_name
                ]


                # ---------------------------------------------
                # TÍNH TRẠNG THÁI THỰC TẾ TRƯỚC HEARTBEAT
                # ---------------------------------------------

                old_last_seen = machine.get(
                    "last_seen"
                )


                old_seconds = seconds_since(
                    old_last_seen
                )


                was_offline = (

                    machine.get(
                        "status"
                    )
                    == "OFFLINE"

                    or

                    old_seconds
                    >=
                    OFFLINE_TIMEOUT

                )


                # ---------------------------------------------
                # CẬP NHẬT HEARTBEAT
                # ---------------------------------------------

                machine[
                    "last_seen"
                ] = current_time


                machine[
                    "public_ip"
                ] = public_ip


                machine[
                    "status"
                ] = "ONLINE"


                # ---------------------------------------------
                # NẾU TRƯỚC ĐÓ OFFLINE
                # ---------------------------------------------

                if was_offline:

                    print(
                        f"[BACK ONLINE] "
                        f"{machine_name}"
                    )


                    machine[
                        "offline_alert_sent"
                    ] = False


                    machine[
                        "online_alert_sent"
                    ] = False


                    send_online = True


        # ====================================================
        # GỬI ONLINE TELEGRAM
        # NGOÀI LOCK
        # ====================================================

        if send_online:

            print(
                f"[SENDING ONLINE] "
                f"{machine_name}"
            )


            success, result = (

                send_online_alert(

                    machine_name,

                    public_ip

                )

            )


            print(
                "[ONLINE TELEGRAM RESULT]",
                success,
                result
            )


            with machines_lock:

                if machine_name in machines:

                    machine = machines[
                        machine_name
                    ]


                    machine[
                        "last_telegram_result"
                    ] = result


                    if success:

                        machine[
                            "last_online_alert"
                        ] = now_vn()


                        machine[
                            "online_alert_sent"
                        ] = True


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
#
# NHIỆM VỤ:
# - Kiểm tra heartbeat
# - >= 30 giây => OFFLINE
# - Gửi Telegram đúng 1 lần
# ============================================================

def watchdog():

    print(
        "=============================================="
    )

    print(
        "WATCHDOG STARTED"
    )

    print(
        f"OFFLINE TIMEOUT = "
        f"{OFFLINE_TIMEOUT} seconds"
    )

    print(
        "=============================================="
    )


    while True:

        try:

            send_list = []


            current_time = now_vn()


            # =================================================
            # KIỂM TRA MÁY
            # =================================================

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


                    # =================================================
                    # OFFLINE
                    # =================================================

                    if (

                        seconds_missing
                        >=
                        OFFLINE_TIMEOUT

                    ):


                        # ---------------------------------------------
                        # Nếu chưa OFFLINE
                        # ---------------------------------------------

                        if (

                            machine.get(
                                "status"
                            )
                            !=
                            "OFFLINE"

                        ):

                            print(
                                f"[OFFLINE DETECTED] "
                                f"{machine_name} "
                                f"| {seconds_missing}s"
                            )


                            machine[
                                "status"
                            ] = "OFFLINE"


                        # ---------------------------------------------
                        # CHỈ GỬI 1 LẦN
                        # ---------------------------------------------

                        if not machine.get(

                            "offline_alert_sent",

                            False

                        ):

                            machine[
                                "offline_alert_sent"
                            ] = True


                            send_list.append({

                                "machine":
                                    machine_name,

                                "public_ip":
                                    machine.get(
                                        "public_ip",
                                        "UNKNOWN"
                                    ),

                                "last_seen":
                                    last_seen,

                                "seconds_missing":
                                    seconds_missing

                            })


                    # =================================================
                    # ONLINE
                    # =================================================

                    else:

                        # Đây là phần QUAN TRỌNG
                        #
                        # Không bao giờ để:
                        #
                        # ONLINE + 48 giây
                        #
                        # Nếu < 30s thì ONLINE.

                        machine[
                            "status"
                        ] = "ONLINE"


            # =================================================
            # GỬI OFFLINE TELEGRAM
            # NGOÀI LOCK
            # =================================================

            for item in send_list:


                machine_name = item[
                    "machine"
                ]


                print(
                    f"[SENDING OFFLINE] "
                    f"{machine_name}"
                )


                success, result = (

                    send_offline_alert(

                        item[
                            "machine"
                        ],

                        item[
                            "public_ip"
                        ],

                        item[
                            "last_seen"
                        ],

                        item[
                            "seconds_missing"
                        ]

                    )

                )


                print(
                    "[OFFLINE TELEGRAM RESULT]",
                    success,
                    result
                )


                with machines_lock:


                    if machine_name not in machines:

                        continue


                    machine = machines[
                        machine_name
                    ]


                    machine[
                        "last_telegram_result"
                    ] = result


                    if success:

                        machine[
                            "last_offline_alert"
                        ] = now_vn()

                    else:

                        # Gửi thất bại
                        # cho phép thử lại
                        machine[
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
#
# STATUS ĐƯỢC TÍNH LẠI TỪ last_seen
#
# Đây là phần chống lỗi:
#
# ONLINE + 48 giây
#
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


            if last_seen is not None:

                seconds_missing = max(

                    0,

                    int(

                        (
                            current_time
                            -
                            last_seen
                        ).total_seconds()

                    )

                )


            # =================================================
            # TÍNH STATUS THỰC TẾ
            # =================================================

            if (

                last_seen is not None

                and

                seconds_missing
                <
                OFFLINE_TIMEOUT

            ):

                actual_status = "ONLINE"

            else:

                actual_status = "OFFLINE"


                # Đồng bộ lại RAM
                machine[
                    "status"
                ] = "OFFLINE"


            # =================================================
            # TELEGRAM STATUS
            # =================================================

            telegram_result = machine.get(
                "last_telegram_result",
                ""
            )


            result[machine_name] = {

                "status":
                    actual_status,

                "public_ip":
                    machine.get(
                        "public_ip",
                        "UNKNOWN"
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

                "last_online_alert":
                    format_time(

                        machine.get(
                            "last_online_alert"
                        )

                    ),

                "last_telegram_result":
                    telegram_result

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
# WEB INTERFACE
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

* {
    box-sizing:
        border-box;
}


body {

    margin:
        0;

    padding:
        20px;

    font-family:
        Arial,
        sans-serif;

    background:
        #f3f4f6;

    color:
        #111827;

}


.container {

    max-width:
        1100px;

    margin:
        auto;

}


h1 {

    font-size:
        32px;

    margin-bottom:
        20px;

}


.card {

    background:
        white;

    padding:
        20px;

    margin-bottom:
        16px;

    border-radius:
        16px;

    box-shadow:
        0 4px 15px
        rgba(0,0,0,0.08);

}


.online {

    border-left:
        8px solid
        #16a34a;

}


.offline {

    border-left:
        8px solid
        #dc2626;

}


.status {

    font-size:
        22px;

    font-weight:
        bold;

}


.status-online {

    color:
        #16a34a;

}


.status-offline {

    color:
        #dc2626;

}


.row {

    padding:
        12px 0;

    border-bottom:
        1px solid
        #e5e7eb;

}


.row:last-child {

    border-bottom:
        none;

}


button {

    border:
        none;

    border-radius:
        10px;

    padding:
        12px 18px;

    cursor:
        pointer;

    font-size:
        16px;

}


.test-button {

    background:
        #229ed9;

    color:
        white;

}


.refresh {

    text-align:
        center;

    color:
        #6b7280;

    margin-top:
        20px;

}


</style>

</head>


<body>


<div class="container">


<h1>
📡 NETWORK MONITOR
</h1>


<div id="app">
Đang tải...
</div>


<div class="refresh">

🔄 Tự động cập nhật mỗi 1 giây

</div>


</div>


<script>


async function loadData() {


    try {


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

<h2>
🟢 SERVER
</h2>


<div class="row">

☁️ Server:

<b>
${data.server}
</b>

</div>


<div class="row">

🕒 Giờ Việt Nam:

<b>
${data.time}
</b>

</div>


<div class="row">

🔴 Offline timeout:

<b>
${data.offline_timeout}
giây
</b>

</div>


<div class="row">

🤖 Telegram:

<b>

${

data.telegram_configured

?

"🟢 ĐÃ CẤU HÌNH"

:

"🔴 CHƯA CẤU HÌNH"

}

</b>

</div>


<br>


<button
class="test-button"
onclick="testTelegram()"
>

🧪 Test Telegram

</button>


</div>

`;


        const names =
            Object.keys(
                data.machines
            );


        if (
            names.length === 0
        ) {


            html += `

<div class="card">

⚠️ Chưa có máy nào gửi heartbeat.

</div>

`;


        }


        for (
            const name of names
        ) {


            const m =
                data.machines[name];


            const isOnline =
                m.status === "ONLINE";


            html += `

<div class="card

${

isOnline
?
"online"
:
"offline"

}

">


<h2>

🖥️ ${name}

</h2>


<div class="row status

${

isOnline
?
"status-online"
:
"status-offline"

}

">

${

isOnline
?
"🟢 ONLINE"
:
"🔴 OFFLINE"

}

</div>


<div class="row">

🌐 Public IP:

<b>
${m.public_ip}
</b>

</div>


<div class="row">

🕒 Last Seen:

<b>
${m.last_seen}
</b>

</div>


<div class="row">

⏱️ Heartbeat:

<b>

${m.seconds_since_last_heartbeat}
giây trước

</b>

</div>


<div class="row">

📨 Đã gửi OFFLINE:

<b>

${

m.offline_alert_sent
?
"YES"
:
"NO"

}

</b>

</div>


<div class="row">

🔴 Lần OFFLINE cuối:

<b>

${

m.last_offline_alert
||
"Chưa có"

}

</b>

</div>


<div class="row">

🟢 Lần ONLINE cuối:

<b>

${

m.last_online_alert
||
"Chưa có"

}

</b>

</div>


<div class="row">

🤖 Telegram Result:

<b>

${

m.last_telegram_result
||
"Chưa có"

}

</b>

</div>


</div>

`;

        }


        document.getElementById(
            "app"
        ).innerHTML = html;


    }

    catch (error) {


        document.getElementById(
            "app"
        ).innerHTML = `

<div class="card offline">

<h2>
🔴 ERROR
</h2>

${error}

</div>

`;

    }

}


async function testTelegram() {


    try {


        const response =
            await fetch(
                "/test-telegram?t="
                +
                Date.now()
            );


        const data =
            await response.json();


        if (
            data.success
        ) {


            alert(
                "🟢 Telegram gửi thành công!"
            );


        } else {


            alert(

                "🔴 Telegram lỗi:\n\n"
                +
                data.result

            );

        }


        loadData();


    }

    catch (error) {


        alert(

            "🔴 Không thể test Telegram:\n\n"
            +
            error

        );

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
# START
# ============================================================

if __name__ == "__main__":

    port = int(

        os.environ.get(
            "PORT",
            "5000"
        )

    )


    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )
