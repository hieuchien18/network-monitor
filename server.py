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
# VIETNAM TIME
# ============================================================

VIETNAM_TZ = timezone(timedelta(hours=7))


def vietnam_now():
    return datetime.now(VIETNAM_TZ)


def format_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
).strip()

CHAT_ID = os.environ.get(
    "CHAT_ID",
    ""
).strip()


# Client heartbeat:
# 10 seconds

HEARTBEAT_INTERVAL = 10


# Không nhận heartbeat 30 giây
# => OFFLINE

OFFLINE_TIMEOUT = 30


# Watchdog kiểm tra mỗi 1 giây

CHECK_INTERVAL = 1


# ============================================================
# MACHINE DATA
# ============================================================

machines = {}

machines_lock = threading.Lock()


# ============================================================
# TELEGRAM STATUS
# ============================================================

telegram_status = {

    "sent": False,

    "last_time": None,

    "last_type": None,

    "last_machine": None,

    "last_error": None

}


# ============================================================
# TELEGRAM SEND
# ============================================================

def send_telegram(message, event_type="", machine_name=""):

    global telegram_status


    # --------------------------------------------------------
    # Không có BOT TOKEN
    # --------------------------------------------------------

    if not BOT_TOKEN:

        telegram_status.update({

            "sent": False,

            "last_time": format_time(
                vietnam_now()
            ),

            "last_type": event_type,

            "last_machine": machine_name,

            "last_error":
                "BOT_TOKEN chưa được cấu hình"

        })

        return False


    # --------------------------------------------------------
    # Không có CHAT ID
    # --------------------------------------------------------

    if not CHAT_ID:

        telegram_status.update({

            "sent": False,

            "last_time": format_time(
                vietnam_now()
            ),

            "last_type": event_type,

            "last_machine": machine_name,

            "last_error":
                "CHAT_ID chưa được cấu hình"

        })

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


        now_text = format_time(
            vietnam_now()
        )


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        if response.ok:

            telegram_status.update({

                "sent": True,

                "last_time": now_text,

                "last_type": event_type,

                "last_machine": machine_name,

                "last_error": None

            })

            print(
                f"Telegram OK: "
                f"{event_type} - "
                f"{machine_name}"
            )

            return True


        # ----------------------------------------------------
        # ERROR
        # ----------------------------------------------------

        error_text = (
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )


        telegram_status.update({

            "sent": False,

            "last_time": now_text,

            "last_type": event_type,

            "last_machine": machine_name,

            "last_error": error_text

        })


        print(
            "Telegram ERROR:",
            error_text
        )


        return False


    except Exception as ex:

        now_text = format_time(
            vietnam_now()
        )


        telegram_status.update({

            "sent": False,

            "last_time": now_text,

            "last_type": event_type,

            "last_machine": machine_name,

            "last_error": str(ex)

        })


        print(
            "Telegram ERROR:",
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


    telegram_message = None

    telegram_event = ""


    with machines_lock:

        # ====================================================
        # NEW MACHINE
        # ====================================================

        if machine_name not in machines:

            machines[machine_name] = {

                "last_seen": now,

                "online": True,

                "public_ip":
                    public_ip,

                "offline_since":
                    None,

                "telegram_sent":
                    False,

                "telegram_time":
                    None,

                "telegram_event":
                    None,

                "telegram_error":
                    None

            }


            telegram_message = (

                "🟢 MÁY ĐÃ ONLINE\n\n"

                f"🖥️ Máy:\n"
                f"{machine_name}\n\n"

                f"🌐 Public IP:\n"
                f"{public_ip}\n\n"

                f"🕒 Thời gian:\n"
                f"{format_time(now)}"

            )


            telegram_event = "ONLINE"


        else:

            machine = machines[
                machine_name
            ]


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

                    offline_seconds = int(

                        (
                            now
                            -
                            offline_since
                        ).total_seconds()

                    )

                else:

                    offline_seconds = 0


                machine["online"] = True

                machine[
                    "offline_since"
                ] = None


                telegram_message = (

                    "🟢 MÁY ĐÃ KẾT NỐI LẠI\n\n"

                    f"🖥️ Máy:\n"
                    f"{machine_name}\n\n"

                    f"🌐 Public IP:\n"
                    f"{public_ip}\n\n"

                    f"🔴 Mất mạng từ:\n"
                    f"{format_time(offline_since) if offline_since else 'Unknown'}\n\n"

                    f"🟢 Có mạng lại:\n"
                    f"{format_time(now)}\n\n"

                    f"⏱️ Thời gian mất mạng:\n"
                    f"{offline_seconds} giây"

                )


                telegram_event = "ONLINE_AGAIN"


            # =================================================
            # NORMAL HEARTBEAT
            # =================================================

            machine["last_seen"] = now

            machine["public_ip"] = public_ip


    # ========================================================
    # SEND TELEGRAM
    # ========================================================

    if telegram_message:

        success = send_telegram(

            telegram_message,

            telegram_event,

            machine_name

        )


        # ----------------------------------------------------
        # Lưu trạng thái Telegram vào máy
        # ----------------------------------------------------

        with machines_lock:

            machine = machines[
                machine_name
            ]


            machine[
                "telegram_sent"
            ] = success


            machine[
                "telegram_time"
            ] = format_time(
                vietnam_now()
            )


            machine[
                "telegram_event"
            ] = telegram_event


            machine[
                "telegram_error"
            ] = (
                None
                if success
                else telegram_status[
                    "last_error"
                ]
            )


    return jsonify({

        "status": "OK",

        "machine":
            machine_name,

        "time":
            format_time(now)

    })


# ============================================================
# API STATUS
# ============================================================

@app.route(
    "/api/status",
    methods=["GET"]
)
def api_status():

    now = vietnam_now()

    result = {}


    with machines_lock:

        for name, machine in machines.items():

            seconds = int(

                (
                    now
                    -
                    machine["last_seen"]
                ).total_seconds()

            )


            if seconds >= OFFLINE_TIMEOUT:

                status = "OFFLINE"

            else:

                status = "ONLINE"


            result[name] = {

                "status":
                    status,

                "last_seen":
                    format_time(
                        machine["last_seen"]
                    ),

                "seconds_since_last_heartbeat":
                    seconds,

                "public_ip":
                    machine["public_ip"],

                "telegram_sent":
                    machine.get(
                        "telegram_sent",
                        False
                    ),

                "telegram_time":
                    machine.get(
                        "telegram_time"
                    ),

                "telegram_event":
                    machine.get(
                        "telegram_event"
                    ),

                "telegram_error":
                    machine.get(
                        "telegram_error"
                    )

            }


    return jsonify({

        "server":
            "RUNNING",

        "time":
            format_time(now),

        "offline_timeout":
            OFFLINE_TIMEOUT,

        "telegram": {

            "configured":
                bool(
                    BOT_TOKEN
                )
                and
                bool(
                    CHAT_ID
                ),

            "sent":
                telegram_status[
                    "sent"
                ],

            "last_time":
                telegram_status[
                    "last_time"
                ],

            "last_type":
                telegram_status[
                    "last_type"
                ],

            "last_machine":
                telegram_status[
                    "last_machine"
                ],

            "last_error":
                telegram_status[
                    "last_error"
                ]

        },

        "machines":
            result

    })


# ============================================================
# DASHBOARD
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def dashboard():

    return render_template_string(
        r"""
<!DOCTYPE html>

<html lang="vi">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="
        width=device-width,
        initial-scale=1.0
    "
>

<title>
NETWORK MONITOR
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
        Helvetica,
        sans-serif;

    background:
        #f1f5f9;

    color:
        #111827;

}


/* =========================================================
   HEADER
   ========================================================= */

.header {

    background:
        #0f172a;

    color:
        white;

    padding:
        30px 25px;

    font-size:
        30px;

    font-weight:
        bold;

}


.header span {

    font-size:
        28px;

}


/* =========================================================
   CONTAINER
   ========================================================= */

.container {

    max-width:
        1200px;

    margin:
        auto;

    padding:
        25px;

}


/* =========================================================
   SERVER
   ========================================================= */

.server-box {

    background:
        white;

    border-radius:
        18px;

    padding:
        22px;

    margin-bottom:
        25px;

    box-shadow:
        0 5px 20px
        rgba(
            0,
            0,
            0,
            .08
        );

}


.server-title {

    font-size:
        20px;

    font-weight:
        bold;

    margin-bottom:
        12px;

}


.server-line {

    margin:
        8px 0;

}


/* =========================================================
   MACHINE GRID
   ========================================================= */

.machine-grid {

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(
                320px,
                1fr
            )
        );

    gap:
        22px;

}


/* =========================================================
   MACHINE CARD
   ========================================================= */

.machine {

    background:
        white;

    border-radius:
        20px;

    padding:
        25px;

    box-shadow:
        0 7px 25px
        rgba(
            0,
            0,
            0,
            .10
        );

    border-left:
        8px solid
        #16a34a;

}


.machine.offline {

    border-left:
        8px solid
        #dc2626;

}


/* =========================================================
   MACHINE NAME
   ========================================================= */

.machine-name {

    font-size:
        24px;

    font-weight:
        bold;

    margin-bottom:
        15px;

    word-break:
        break-word;

}


/* =========================================================
   STATUS
   ========================================================= */

.status {

    display:
        inline-block;

    border-radius:
        30px;

    padding:
        10px 20px;

    font-size:
        18px;

    font-weight:
        bold;

    margin-bottom:
        15px;

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


/* =========================================================
   INFO
   ========================================================= */

.info {

    padding:
        12px 0;

    border-bottom:
        1px solid
        #e5e7eb;

    line-height:
        1.5;

}


/* =========================================================
   TELEGRAM BOX
   ========================================================= */

.telegram-box {

    margin-top:
        20px;

    padding:
        15px;

    border-radius:
        14px;

    background:
        #f8fafc;

}


.telegram-title {

    font-size:
        18px;

    font-weight:
        bold;

    margin-bottom:
        10px;

}


.telegram-ok {

    color:
        #15803d;

    font-weight:
        bold;

}


.telegram-error {

    color:
        #dc2626;

    font-weight:
        bold;

}


.telegram-none {

    color:
        #64748b;

}


/* =========================================================
   EMPTY
   ========================================================= */

.empty {

    background:
        white;

    border-radius:
        18px;

    padding:
        60px 20px;

    text-align:
        center;

    font-size:
        20px;

}


/* =========================================================
   FOOTER
   ========================================================= */

.refresh {

    text-align:
        center;

    margin-top:
        25px;

    color:
        #64748b;

}


/* =========================================================
   MOBILE
   ========================================================= */

@media (
    max-width: 600px
) {

    .header {

        font-size:
            26px;

        padding:
            25px 20px;

    }


    .container {

        padding:
            18px;

    }


    .machine {

        padding:
            22px;

    }


    .machine-name {

        font-size:
            22px;

    }

}

</style>

</head>


<body>


<!-- =======================================================
     HEADER
======================================================== -->

<div class="header">

    📡 NETWORK MONITOR

</div>


<div class="container">


<!-- =======================================================
     SERVER INFO
======================================================== -->

<div class="server-box">

    <div class="server-title">

        ☁️ SERVER

    </div>


    <div class="server-line">

        🟢 Status:
        <b>RUNNING</b>

    </div>


    <div
        class="server-line"
        id="serverTime"
    >

        🕒 Đang tải...

    </div>


    <div class="server-line">

        🔴 Offline sau:
        <b>30 giây</b>

    </div>


    <div
        class="server-line"
        id="telegramGlobal"
    >

        📱 Telegram:
        Đang kiểm tra...

    </div>

</div>


<!-- =======================================================
     MACHINES
======================================================== -->

<div
    class="machine-grid"
    id="machineGrid"
>

    <div class="empty">

        🔄 Đang tải...

    </div>

</div>


<div class="refresh">

    🔄 Tự động cập nhật mỗi 1 giây

</div>


</div>


<script>


// =========================================================
// ESCAPE HTML
// =========================================================

function escapeHtml(text) {

    if (
        text === null ||
        text === undefined
    ) {

        return "";

    }


    return String(text)

        .replace(
            /&/g,
            "&amp;"
        )

        .replace(
            /</g,
            "&lt;"
        )

        .replace(
            />/g,
            "&gt;"
        )

        .replace(
            /"/g,
            "&quot;"
        )

        .replace(
            /'/g,
            "&#039;"
        );

}


// =========================================================
// LOAD STATUS
// =========================================================

async function loadStatus() {

    try {


        const response =
            await fetch(
                "/api/status",
                {
                    cache:
                        "no-store"
                }
            );


        const data =
            await response.json();


        // =================================================
        // SERVER TIME
        // =================================================

        document.getElementById(
            "serverTime"
        ).innerHTML =

            "🕒 Giờ Việt Nam: "
            +
            escapeHtml(
                data.time
            );


        // =================================================
        // GLOBAL TELEGRAM
        // =================================================

        const tg =
            data.telegram;


        const globalTelegram =
            document.getElementById(
                "telegramGlobal"
            );


        if (
            tg.configured
        ) {

            if (
                tg.sent
            ) {

                globalTelegram.innerHTML =

                    "📱 Telegram: "
                    +
                    "<span class='telegram-ok'>"
                    +
                    "🟢 ĐÃ GỬI"
                    +
                    "</span>"
                    +
                    (
                        tg.last_time
                        ?
                        " — "
                        +
                        escapeHtml(
                            tg.last_time
                        )
                        :
                        ""
                    );

            } else {

                globalTelegram.innerHTML =

                    "📱 Telegram: "
                    +
                    "<span class='telegram-error'>"
                    +
                    "🔴 CHƯA GỬI"
                    +
                    "</span>";

            }

        } else {

            globalTelegram.innerHTML =

                "📱 Telegram: "
                +
                "<span class='telegram-error'>"
                +
                "🔴 CHƯA CẤU HÌNH"
                +
                "</span>";

        }


        // =================================================
        // MACHINE GRID
        // =================================================

        const grid =
            document.getElementById(
                "machineGrid"
            );


        const machines =
            data.machines;


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


        let html = "";


        // =================================================
        // EACH MACHINE
        // =================================================

        for (
            const name
            of names
        ) {


            const machine =
                machines[name];


            const online =
                machine.status ===
                "ONLINE";


            const safeName =
                escapeHtml(
                    name
                );


            const safeIp =
                escapeHtml(
                    machine.public_ip
                );


            const safeLastSeen =
                escapeHtml(
                    machine.last_seen
                );


            // =============================================
            // TELEGRAM STATUS
            // =============================================

            let telegramHtml = "";


            if (
                machine.telegram_sent
            ) {

                telegramHtml = `

                    <div class="telegram-ok">

                        🟢 ĐÃ GỬI

                    </div>

                    <div>

                        🕒 Lần gửi:

                        <b>
                            ${
                                escapeHtml(
                                    machine.telegram_time
                                    || "-"
                                )
                            }
                        </b>

                    </div>

                    <div>

                        📌 Sự kiện:

                        <b>
                            ${
                                escapeHtml(
                                    machine.telegram_event
                                    || "-"
                                )
                            }
                        </b>

                    </div>

                `;

            } else {


                telegramHtml = `

                    <div class="telegram-error">

                        🔴 CHƯA GỬI

                    </div>

                `;


                if (
                    machine.telegram_error
                ) {

                    telegramHtml += `

                        <div>

                            ❌ Lỗi:

                            ${
                                escapeHtml(
                                    machine.telegram_error
                                )
                            }

                        </div>

                    `;

                }

            }


            // =============================================
            // CARD
            // =============================================

            html += `

                <div
                    class="
                        machine
                        ${
                            online
                            ? ""
                            : "offline"
                        }
                    "
                >


                    <div
                        class="machine-name"
                    >

                        🖥️ ${safeName}

                    </div>


                    <div
                        class="
                            status
                            ${
                                online
                                ? "online"
                                : "offline"
                            }
                        "
                    >

                        ${
                            online
                            ? "🟢 ONLINE"
                            : "🔴 OFFLINE"
                        }

                    </div>


                    <div class="info">

                        🌐 Public IP:

                        <b>
                            ${safeIp}
                        </b>

                    </div>


                    <div class="info">

                        🕒 Last Seen:

                        <b>
                            ${safeLastSeen}
                        </b>

                    </div>


                    <div class="info">

                        ⏱️

                        ${
                            machine.seconds_since_last_heartbeat
                        }

                        giây trước

                    </div>


                    <div class="telegram-box">

                        <div
                            class="telegram-title"
                        >

                            📱 TELEGRAM

                        </div>

                        ${telegramHtml}

                    </div>


                </div>

            `;

        }


        grid.innerHTML =
            html;


    }
    catch (error) {


        console.error(
            "STATUS ERROR:",
            error
        );

    }

}


// =========================================================
// FIRST LOAD
// =========================================================

loadStatus();


// =========================================================
// AUTO REFRESH
// =========================================================

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

    while True:

        try:

            now = vietnam_now()

            offline_events = []


            with machines_lock:

                for (
                    machine_name,
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
                            "offline_since"
                        ] = now


                        offline_events.append({

                            "machine":
                                machine_name,

                            "public_ip":
                                machine[
                                    "public_ip"
                                ],

                            "last_seen":
                                machine[
                                    "last_seen"
                                ],

                            "offline_since":
                                now,

                            "seconds":
                                seconds

                        })


            # =================================================
            # SEND OFFLINE TELEGRAM
            # =================================================

            for event in offline_events:


                message = (

                    "🔴 MÁY ĐÃ OFFLINE\n\n"

                    f"🖥️ Máy:\n"
                    f"{event['machine']}\n\n"

                    f"🌐 Public IP cuối:\n"
                    f"{event['public_ip']}\n\n"

                    f"🕒 Heartbeat cuối:\n"
                    f"{format_time(event['last_seen'])}\n\n"

                    f"🔴 Phát hiện mất kết nối:\n"
                    f"{format_time(event['offline_since'])}\n\n"

                    f"⏱️ Không nhận heartbeat:\n"
                    f"{event['seconds']} giây"

                )


                success = send_telegram(

                    message,

                    "OFFLINE",

                    event["machine"]

                )


                # =============================================
                # SAVE TELEGRAM RESULT TO MACHINE
                # =============================================

                with machines_lock:

                    machine =
                        machines[
                            event["machine"]
                        ]


                    machine[
                        "telegram_sent"
                    ] = success


                    machine[
                        "telegram_time"
                    ] = format_time(
                        vietnam_now()
                    )


                    machine[
                        "telegram_event"
                    ] = "OFFLINE"


                    machine[
                        "telegram_error"
                    ] = (

                        None

                        if success

                        else
                        telegram_status[
                            "last_error"
                        ]

                    )


        except Exception as ex:

            print(
                "WATCHDOG ERROR:",
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


    app.run(

        host="0.0.0.0",

        port=port

    )
