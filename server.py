import time
import threading
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request, render_template_string


app = Flask(__name__)


# ============================================================
# CONFIG
# ============================================================

# Client gửi heartbeat mỗi 10 giây
# Nếu quá 30 giây không nhận được heartbeat => OFFLINE
OFFLINE_TIMEOUT = 30

# Watchdog kiểm tra mỗi 1 giây
CHECK_INTERVAL = 1


# ============================================================
# TELEGRAM CONFIG
# ============================================================

BOT_TOKEN = "8508756103:AAGBFPaboWOaIxaCOf-W46PRBoeSDyiDcZ4"

CHAT_ID = "6149566675"


# ============================================================
# TIMEZONE VIETNAM
# ============================================================

VN_TZ = timezone(
    timedelta(hours=7)
)


# ============================================================
# MACHINE DATA
# ============================================================

machines = {}

machines_lock = threading.Lock()


# ============================================================
# TIME FUNCTIONS
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


# ============================================================
# SEND TELEGRAM
# ============================================================

def send_telegram(message):

    try:

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
                        "Telegram sent successfully"
                    )

                return (
                    False,
                    response.text
                )

            except Exception:

                return (
                    False,
                    response.text
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
# SEND ONLINE ALERT
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
# SEND OFFLINE ALERT
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
# HEARTBEAT API
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
        # MACHINE NAME
        # ====================================================

        machine_name = str(

            data.get(
                "machine",
                ""
            )

        ).strip().upper()


        # ====================================================
        # PUBLIC IP
        # ====================================================

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


        # Nếu client không lấy được Public IP
        # thì lấy IP request gửi lên
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

                public_ip = request.remote_addr


        current_time = now_vn()


        need_online_alert = False


        # ====================================================
        # UPDATE MACHINE
        # ====================================================

        with machines_lock:


            # ------------------------------------------------
            # MÁY MỚI
            # ------------------------------------------------

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

                    "last_telegram_result":
                        "",

                    "last_offline_alert":
                        None

                }


                # Máy mới gửi ONLINE
                need_online_alert = True


            # ------------------------------------------------
            # MÁY ĐÃ TỒN TẠI
            # ------------------------------------------------

            else:


                machine = machines[
                    machine_name
                ]


                was_offline = (

                    machine.get(
                        "status"
                    )

                    ==

                    "OFFLINE"

                )


                # Cập nhật heartbeat
                machine[
                    "last_seen"
                ] = current_time


                machine[
                    "public_ip"
                ] = public_ip


                machine[
                    "status"
                ] = "ONLINE"


                # ------------------------------------------------
                # NẾU TRƯỚC ĐÓ OFFLINE
                # ------------------------------------------------

                if was_offline:


                    print(

                        f"[MACHINE BACK ONLINE] "
                        f"{machine_name}"

                    )


                    # Reset để lần offline tiếp theo
                    # được gửi Telegram
                    machine[
                        "offline_alert_sent"
                    ] = False


                    need_online_alert = True


        # ====================================================
        # SEND ONLINE TELEGRAM
        # KHÔNG GỬI TRONG LOCK
        # ====================================================

        if need_online_alert:


            print(

                f"[SENDING ONLINE ALERT] "
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
# SERVER TỰ KIỂM TRA MÁY OFFLINE
# ============================================================

def watchdog():

    print(
        "========================================"
    )

    print(
        "WATCHDOG STARTED"
    )

    print(
        f"OFFLINE TIMEOUT: "
        f"{OFFLINE_TIMEOUT} seconds"
    )

    print(
        "========================================"
    )


    while True:


        try:


            current_time = now_vn()


            send_list = []


            # ====================================================
            # KIỂM TRA TẤT CẢ MÁY
            # ====================================================

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


                    # ====================================================
                    # QUÁ OFFLINE_TIMEOUT
                    # ====================================================

                    if (

                        seconds_missing
                        >=
                        OFFLINE_TIMEOUT

                    ):


                        # ------------------------------------------------
                        # CHUYỂN TRẠNG THÁI OFFLINE
                        # ------------------------------------------------

                        if (

                            machine.get(
                                "status"
                            )

                            !=

                            "OFFLINE"

                        ):


                            print(

                                f"[OFFLINE DETECTED] "

                                f"Machine: "
                                f"{machine_name} | "

                                f"Missing: "
                                f"{seconds_missing}s"

                            )


                            machine[
                                "status"
                            ] = "OFFLINE"


                        # ------------------------------------------------
                        # CHƯA GỬI TELEGRAM
                        # ------------------------------------------------

                        if not machine.get(

                            "offline_alert_sent",

                            False

                        ):


                            # Đánh dấu trước
                            # để không gửi lặp liên tục
                            machine[
                                "offline_alert_sent"
                            ] = True


                            send_list.append({

                                "machine_name":
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


            # ====================================================
            # GỬI TELEGRAM NGOÀI LOCK
            # ====================================================

            for item in send_list:


                machine_name = item[
                    "machine_name"
                ]


                print(

                    f"[SENDING OFFLINE ALERT] "
                    f"{machine_name}"

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


                # ====================================================
                # LƯU KẾT QUẢ
                # ====================================================

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
                                "last_offline_alert"
                            ] = now_vn()


                        else:


                            # Gửi Telegram lỗi
                            # lần sau thử lại
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


            result[
                machine_name
            ] = {


                "status":

                    machine.get(
                        "status",
                        "UNKNOWN"
                    ),


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

*{

    box-sizing:
        border-box;

}


body{

    margin:0;

    padding:20px;

    font-family:

        Arial,
        sans-serif;

    background:

        #f3f4f6;

}


h1{

    margin-top:0;

}


.card{

    background:

        white;

    padding:

        20px;

    margin-bottom:

        15px;

    border-radius:

        12px;

    box-shadow:

        0 2px 10px
        rgba(0,0,0,0.08);

}


.online{

    border-left:

        8px solid
        #16a34a;

}


.offline{

    border-left:

        8px solid
        #dc2626;

}


.row{

    padding:

        10px 0;

    border-bottom:

        1px solid
        #e5e7eb;

}


.status-online{

    color:

        #16a34a;

    font-weight:

        bold;

}


.status-offline{

    color:

        #dc2626;

    font-weight:

        bold;

}


button{

    padding:

        10px 16px;

    border:

        none;

    border-radius:

        8px;

    cursor:

        pointer;

    font-size:

        15px;

}


.test-btn{

    background:

        #229ED9;

    color:

        white;

}

</style>

</head>


<body>


<h1>
📡 NETWORK MONITOR
</h1>


<div
id="app"
>

Đang tải...

</div>


<script>


async function loadData(){


    try{


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

Status:

<b>

${data.server}

</b>

</div>

<div class="row">

🕒 ${data.time}

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
class="test-btn"
onclick="testTelegram()"
>

🧪 Test Telegram

</button>

</div>

`;


        const machines =

            data.machines;


        const names =

            Object.keys(
                machines
            );


        if(

            names.length === 0

        ){


            html += `

<div class="card">

⚠️ Chưa có máy nào gửi heartbeat.

</div>

`;


        }


        for(

            const name

            of names

        ){


            const m =

                machines[name];


            const isOnline =

                m.status
                ===
                "ONLINE";


            html += `

<div

class="card

${

isOnline

?

"online"

:

"offline"

}

"

>


<h2>

🖥️ ${name}

</h2>


<div class="row">

📡 Status:

<b

class="

${

isOnline

?

"status-online"

:

"status-offline"

}

"

>

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

🤖 Telegram:

${

m.last_telegram_result

||

"Chưa có"

}

</div>


<div class="row">

🚨 Lần OFFLINE cuối:

${

m.last_offline_alert

||

"Chưa có"

}

</div>


</div>

`;

        }


        document.getElementById(

            "app"

        ).innerHTML =

            html;


    }

    catch(error){


        document.getElementById(

            "app"

        ).innerHTML =

            `

<div class="card offline">

❌ Không thể tải dữ liệu:

${error}

</div>

`;


    }


}


async function testTelegram(){


    try{


        const response =

            await fetch(

                "/test-telegram?t="

                +

                Date.now()

            );


        const data =

            await response.json();


        alert(

            data.success

            ?

            "🟢 Telegram gửi thành công"

            :

            "🔴 Telegram lỗi: "

            +

            data.result

        );


        loadData();


    }

    catch(error){


        alert(

            "❌ Test Telegram lỗi: "

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
# START FLASK
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False

    )
