import os
import time
import threading
from datetime import datetime

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("8508756103:AAGBFPaboWOaIxaCOf-W46PRBoeSDyiDcZ4", "")

CHAT_ID = os.getenv("6149566675", "")

OFFLINE_TIMEOUT = 60

CHECK_INTERVAL = 5


# ============================================================
# MACHINE DATA
# ============================================================

machines = {}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print("BOT_TOKEN hoặc CHAT_ID chưa được cấu hình")

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
            "Telegram:",
            response.text
        )

        return response.ok

    except Exception as ex:

        print(
            "Telegram Error:",
            ex
        )

        return False


# ============================================================
# HEARTBEAT API
# ============================================================

@app.route("/heartbeat", methods=["POST"])
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

    now = datetime.now()

    # --------------------------------------------
    # MÁY MỚI
    # --------------------------------------------

    if machine_name not in machines:

        machines[machine_name] = {

            "last_seen": now,

            "online": True,

            "public_ip": public_ip

        }

        print(
            f"[NEW MACHINE] {machine_name}"
        )

        send_telegram(
            f"""
🟢 MÁY ĐÃ ONLINE

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{now.strftime("%Y-%m-%d %H:%M:%S")}
"""
        )

    else:

        machine = machines[
            machine_name
        ]

        # ----------------------------------------
        # OFFLINE → ONLINE LẠI
        # ----------------------------------------

        if not machine["online"]:

            machine["online"] = True

            send_telegram(
                f"""
🟢 MÁY ĐÃ ONLINE TRỞ LẠI

🖥️ Máy:
{machine_name}

🌐 Public IP:
{public_ip}

🕒 Thời gian:
{now.strftime("%Y-%m-%d %H:%M:%S")}
"""
            )

        machine["last_seen"] = now

        machine["public_ip"] = public_ip


    return jsonify({

        "status": "OK",

        "machine": machine_name,

        "time": now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    })


# ============================================================
# VIEW STATUS
# ============================================================

@app.route("/", methods=["GET"])
def home():

    result = {}

    now = datetime.now()

    for name, machine in machines.items():

        seconds = int(
            (
                now
                - machine["last_seen"]
            ).total_seconds()
        )

        result[name] = {

            "status":
                "ONLINE"
                if machine["online"]
                else "OFFLINE",

            "last_seen":
                machine["last_seen"].strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "seconds_since_last_heartbeat":
                seconds,

            "public_ip":
                machine["public_ip"]

        }


    return jsonify({

        "server": "RUNNING",

        "machines": result

    })


# ============================================================
# WATCHDOG
# ============================================================

def watchdog():

    print(
        "Watchdog started"
    )

    while True:

        try:

            now = datetime.now()

            for machine_name, machine in list(
                machines.items()
            ):

                seconds_offline = int(

                    (
                        now
                        - machine["last_seen"]
                    ).total_seconds()

                )


                # --------------------------------
                # MẤT KẾT NỐI
                # --------------------------------

                if (

                    machine["online"]

                    and

                    seconds_offline
                    >= OFFLINE_TIMEOUT

                ):

                    machine["online"] = False


                    offline_time = (
                        machine["last_seen"]
                    )


                    print(

                        f"[OFFLINE] "
                        f"{machine_name}"

                    )


                    send_telegram(
                        f"""
🔴 CẢNH BÁO MÁY OFFLINE

🖥️ Máy:
{machine_name}

🌐 Public IP cuối:
{machine["public_ip"]}

📡 Không nhận heartbeat quá:
{OFFLINE_TIMEOUT} giây

🕒 Lần cuối online:
{offline_time.strftime("%Y-%m-%d %H:%M:%S")}

⚠️ Có thể:
• Mất Internet
• Tắt Wi-Fi/LAN
• Máy bị tắt
• Tool client bị dừng
"""
                    )


        except Exception as ex:

            print(
                "Watchdog Error:",
                ex
            )


        time.sleep(
            CHECK_INTERVAL
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