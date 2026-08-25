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


# ============================================================
# MACHINE DATA
# ============================================================

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

    return dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN:

        print(
            "[TELEGRAM ERROR] BOT_TOKEN is empty"
        )

        return False, "BOT_TOKEN is empty"


    if not CHAT_ID:

        print(
            "[TELEGRAM ERROR] CHAT_ID is empty"
        )

        return False, "CHAT_ID is empty"


    try:

        url = (
            "https://api.telegram.org/bot"
            + BOT_TOKEN
            + "/sendMessage"
        )


        print(
            "[TELEGRAM SENDING]"
        )

        print(message)


        response = requests.post(

            url,

            json={

                "chat_id":
                    CHAT_ID,

                "text":
                    message

            },

            timeout=15

        )


        print(
            "[TELEGRAM RESPONSE]",
            response.status_code,
            response.text
        )


        if response.status_code == 200:

            try:

                data = response.json()

                if data.get("ok") is True:

                    return (
                        True,
                        "Sent successfully"
                    )

                return (
                    False,
                    response.text
                )

            except Exception as e:

                return (
                    False,
                    "Invalid Telegram JSON: "
                    + str(e)
                )


        return (
            False,
            "HTTP "
            + str(response.status_code)
            + ": "
            + response.text
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
# SEND ONLINE
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
# SEND OFFLINE
# ============================================================

def send_offline_alert(

    machine_name,
    public_ip,
    last_seen,
    seconds_missing

):

    message = f"""🔴 CẢNH BÁO MẤT KẾT NỐI

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Heartbeat cuối:
{format_time(last_seen)}

⏱️ Mất kết nối:
{seconds_missing} giây

🚨 Offline timeout:
{OFFLINE_TIMEOUT} giây

🕒 Phát hiện lúc:
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


        machine_name = str(

            data.get(
                "machine",
                ""
            )

        ).strip().upper()


        public_ip = str(

            data.get(
                "public_ip",
                ""
            )

        ).strip()


        if not machine_name:

            return jsonify({

                "status":
                    "ERROR",

                "message":
                    "machine is required"

            }), 400


        if not public_ip:

            public_ip = (

                request.headers.get(

                    "X-Forwarded-For",

                    request.remote_addr

                )

                .split(",")

                [0]

                .strip()

            )


        current_time = now_vn()


        need_online_alert = False


        with machines_lock:


            # ================================================
            # MÁY CHƯA TỒN TẠI
            # ================================================

            if machine_name not in machines:


                machines[
                    machine_name
                ] = {

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
                        None,

                    "last_online_alert":
                        None

                }


                need_online_alert = True


                print(

                    "[NEW MACHINE]",

                    machine_name

                )


            # ================================================
            # MÁY ĐÃ TỒN TẠI
            # ================================================

            else:


                machine = machines[
                    machine_name
                ]


                old_status = machine.get(

                    "status",

                    "UNKNOWN"

                )


                # Nếu trước đó OFFLINE
                # giờ heartbeat lại
                # => ONLINE LẠI

                if old_status == "OFFLINE":


                    print(

                        "[MACHINE BACK ONLINE]",

                        machine_name

                    )


                    need_online_alert = True


                    # reset để lần OFFLINE tiếp theo
                    # được gửi Telegram

                    machine[
                        "offline_alert_sent"
                    ] = False


                machine[
                    "last_seen"
                ] = current_time


                machine[
                    "public_ip"
                ] = public_ip


                machine[
                    "status"
                ] = "ONLINE"


        # ====================================================
        # GỬI ONLINE NGOÀI LOCK
        # ====================================================

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


                    if success:


                        machines[
                            machine_name
                        ][
                            "last_online_alert"
                        ] = now_vn()


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
        "======================================"
    )

    print(
        "WATCHDOG STARTED"
    )

    print(
        "OFFLINE TIMEOUT:",
        OFFLINE_TIMEOUT,
        "seconds"
    )

    print(
        "======================================"
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


                    # Debug mỗi 5 giây

                    if seconds_missing % 5 == 0:

                        print(

                            "[WATCHDOG]",

                            machine_name,

                            "| Missing:",

                            seconds_missing,

                            "seconds",

                            "| Status:",

                            machine.get(
                                "status"
                            )

                        )


                    # ============================================
                    # OFFLINE
                    # ============================================

                    if (

                        seconds_missing
                        >=
                        OFFLINE_TIMEOUT

                    ):


                        # Nếu chưa OFFLINE
                        # chuyển trạng thái

                        if (

                            machine.get(
                                "status"
                            )

                            !=

                            "OFFLINE"

                        ):


                            machine[
                                "status"
                            ] = "OFFLINE"


                            print(

                                "======================================"

                            )


                            print(

                                "[OFFLINE DETECTED]"

                            )


                            print(

                                "Machine:",

                                machine_name

                            )


                            print(

                                "Last Seen:",

                                format_time(
                                    last_seen
                                )

                            )


                            print(

                                "Missing:",

                                seconds_missing,

                                "seconds"

                            )


                            print(

                                "======================================"

                            )


                        # ========================================
                        # CHƯA GỬI TELEGRAM
                        # ========================================

                        if not machine.get(

                            "offline_alert_sent",

                            False

                        ):


                            print(

                                "[PREPARE OFFLINE TELEGRAM]",

                                machine_name

                            )


                            # Đánh dấu ngay
                            # để không gửi lặp

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
                                    last_seen,

                                "seconds_missing":
                                    seconds_missing

                            })


            # =================================================
            # GỬI TELEGRAM NGOÀI LOCK
            # =================================================

            for item in send_list:


                print(

                    "======================================"

                )

                print(

                    "[SENDING OFFLINE ALERT]"

                )

                print(

                    "Machine:",

                    item[
                        "machine_name"
                    ]

                )

                print(

                    "======================================"

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


                            print(

                                "[OFFLINE ALERT SENT SUCCESS]"

                            )


                        else:


                            print(

                                "[OFFLINE ALERT FAILED]"

                            )


                            # Cho phép thử lại
                            # sau 5 giây

                            machine = machines[
                                machine_name
                            ]


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


            # Tính trạng thái trực tiếp
            # tránh trường hợp watchdog chưa chạy

            if (

                seconds_missing
                >=
                OFFLINE_TIMEOUT

            ):

                display_status = "OFFLINE"

            else:

                display_status = "ONLINE"


            result[
                machine_name
            ] = {


                "status":
                    display_status,


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


                "last_online_alert":

                    format_time(

                        machine.get(

                            "last_online_alert"

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


    success, result = (

        send_telegram(

            f"""🧪 TEST TELEGRAM

✅ Network Monitor kết nối Telegram thành công.

🕒 Thời gian:
{format_time(now_vn())}
"""

        )

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

<html lang="vi">

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

*{

    box-sizing:
        border-box;

}


body{

    font-family:
        Arial,
        sans-serif;

    background:
        #eef1f5;

    margin:
        0;

    padding:
        20px;

}


.container{

    max-width:
        900px;

    margin:
        auto;

}


h1{

    background:
        #172033;

    color:
        white;

    padding:
        25px;

    border-radius:
        15px;

}


.card{

    background:
        white;

    padding:
        20px;

    margin-bottom:
        20px;

    border-radius:
        18px;

    box-shadow:
        0 4px 20px
        rgba(
            0,
            0,
            0,
            0.08
        );

}


.online{

    border-left:
        7px solid
        #16a34a;

}


.offline{

    border-left:
        7px solid
        #dc2626;

}


.row{

    padding:
        12px 5px;

    border-bottom:
        1px solid
        #e5e7eb;

}


.status-online{

    color:
        #15803d;

    font-weight:
        bold;

}


.status-offline{

    color:
        #dc2626;

    font-weight:
        bold;

}


.header-status{

    font-size:
        20px;

    line-height:
        2;

}


.machine-name{

    font-size:
        25px;

    font-weight:
        bold;

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


</div>


<script>


async function loadData(){


    try{


        const response =

            await fetch(

                "/api/status?t="
                +
                Date.now(),

                {

                    cache:
                        "no-store"

                }

            );


        const data =

            await response.json();


        let html = `

<div class="card header-status">

🟢 Server:

<b>

${data.server}

</b>

<br>

🕒 Giờ Việt Nam:

${data.time}

<br>

🔴 Offline timeout:

<b>

${data.offline_timeout} giây

</b>

<br>

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

`;


        for(

            const name

            in

            data.machines

        ){


            const m =

                data.machines[
                    name
                ];


            const statusClass =

                m.status === "ONLINE"

                ?

                "online"

                :

                "offline";


            const statusText =

                m.status === "ONLINE"

                ?

                "🟢 ONLINE"

                :

                "🔴 OFFLINE";


            html += `

<div class="card ${statusClass}">

<div class="machine-name">

🖥️ ${name}

</div>


<div class="row">

📡 Status:

<b class="${
    m.status === "ONLINE"

    ?

    "status-online"

    :

    "status-offline"
}">

${statusText}

</b>

</div>


<div class="row">

🌐 IP:

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

⏱️ Mất heartbeat:

<b>

${m.seconds_since_last_heartbeat}

giây

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

🕒 Lần gửi OFFLINE:

<b>

${
    m.last_offline_alert

    ||

    "Chưa gửi"
}

</b>

</div>


<div class="row">

🕒 Lần gửi ONLINE:

<b>

${
    m.last_online_alert

    ||

    "Chưa gửi"
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

    catch(error){


        document.getElementById(
            "app"
        ).innerHTML =

        "❌ Lỗi tải dữ liệu: "

        +

        error;


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

threading.Thread(

    target=watchdog,

    daemon=True

).start()


# ============================================================
# START APP
# ============================================================

if __name__ == "__main__":


    app.run(

        host="0.0.0.0",

        port=int(

            os.environ.get(

                "PORT",

                5000

            )

        ),

        debug=False

    )
