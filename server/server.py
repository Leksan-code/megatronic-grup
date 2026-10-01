"""
МЕГАТРОНИК — игровой сервер.

Каждый запустивший приложение — участник игры. Раз в секунду клиент шлёт
свои координаты и получает список игроков в радиусе 200 м:
расстояние, азимут и короткий публичный тег. Координаты других игроков
и их секретные ID наружу не передаются. Ничего не хранится постоянно.

Запуск на хостинге:
    gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT server:app
Строго один воркер (-w 1): данные хранятся в памяти процесса.
"""

import hashlib
import math
import os
import threading
import time

from flask import Flask, jsonify, request

app = Flask(__name__)

players = {}          # secret_id -> {"lat", "lon", "ts", "tag"}
lock = threading.Lock()

PLAYER_TIMEOUT_SECONDS = 20
CLEANUP_INTERVAL_SECONDS = 30
VISIBLE_RADIUS_M = 200
MAX_PLAYERS = 20000
ID_LEN = 32
HEX = set("0123456789abcdef")
LAT_PREFILTER = VISIBLE_RADIUS_M / 111000.0 * 1.5   # быстрый отсев по широте


def distance_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def parse_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def get_player_id(data):
    v = data.get("player_id")
    if not isinstance(v, str):
        return None
    v = v.strip().lower()
    if len(v) != ID_LEN or not set(v) <= HEX:
        return None
    return v


def get_coord(data, key, limit):
    v = data.get(key)
    if isinstance(v, bool):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or abs(v) > limit:
        return None
    return v


def public_tag(secret_id):
    return hashlib.sha256(secret_id.encode()).hexdigest()[:6]


def error(msg, code=400):
    return jsonify({"error": msg}), code


def cleanup(now):
    stale = [pid for pid, p in players.items() if now - p["ts"] > PLAYER_TIMEOUT_SECONDS]
    for pid in stale:
        del players[pid]


def cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        with lock:
            cleanup(time.time())


threading.Thread(target=cleanup_loop, daemon=True).start()


@app.route("/update", methods=["POST"])
def update():
    data = parse_json()
    if data is None:
        return error("Ожидается JSON-объект")
    pid = get_player_id(data)
    lat = get_coord(data, "lat", 90)
    lon = get_coord(data, "lon", 180)
    if pid is None:
        return error("Некорректный player_id")
    if lat is None or lon is None:
        return error("lat/lon обязательны")

    now = time.time()
    with lock:
        if pid not in players and len(players) >= MAX_PLAYERS:
            return error("Сервер переполнен", 503)
        me = players.get(pid)
        tag = me["tag"] if me else public_tag(pid)
        players[pid] = {"lat": lat, "lon": lon, "ts": now, "tag": tag}

        nearby = []
        for other_id, p in players.items():
            if other_id == pid:
                continue
            if now - p["ts"] > PLAYER_TIMEOUT_SECONDS:
                continue
            if abs(p["lat"] - lat) > LAT_PREFILTER:
                continue
            d = distance_m(lat, lon, p["lat"], p["lon"])
            if d > VISIBLE_RADIUS_M:
                continue
            nearby.append({
                "tag": p["tag"],
                "dist": round(d, 1),
                "bearing": round(bearing_deg(lat, lon, p["lat"], p["lon"]), 1),
                "age": round(now - p["ts"], 1),
            })

    nearby.sort(key=lambda x: x["dist"])
    return jsonify({"players": nearby, "tag": tag})


@app.route("/leave", methods=["POST"])
def leave():
    data = parse_json()
    if data is None:
        return error("Ожидается JSON-объект")
    pid = get_player_id(data)
    if pid is None:
        return error("Некорректный player_id")
    with lock:
        players.pop(pid, None)
    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    with lock:
        return jsonify({"ok": True, "players": len(players)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
