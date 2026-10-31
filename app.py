
import os
import re
import hmac
import time
import threading

from datetime import datetime, timezone
from flask import Flask, jsonify, request
from fc_clubs_api import FC27API

app = Flask(__name__)

VERSION = "7.8.0"
CACHE_SECONDS = 300

cache = {}
cache_lock = threading.Lock()


def reply(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.before_request
def protect_bridge():
    # La santé du serveur reste consultable.
    if request.path in ("/", "/health"):
        return None

    # Les autres chemins exigent une clé serveur.
    expected = os.environ.get(
        "FC27_BRIDGE_SECRET", ""
    )

    provided = request.headers.get(
        "X-FC27-Bridge-Key", ""
    )

    if (
        len(expected) < 32
        or not hmac.compare_digest(
            provided, expected
        )
    ):
        return reply({
            "ok": False,
            "error": "UNAUTHORIZED",
            "message": "Accès réservé au serveur FC27."
        }, 401)

    return None


def cached_result(key, callback):
    now = time.time()

    with cache_lock:
        saved = cache.get(key)

        if saved and saved["expires"] > now:
            return {
                **saved["result"],
                "cached": True
            }

    result = callback()

    with cache_lock:
        if len(cache) > 100:
            cache.clear()

        cache[key] = {
            "expires": time.time() + CACHE_SECONDS,
            "result": result
        }

    return {
        **result,
        "cached": False
    }


def handle_error(error):
    app.logger.exception(
        "FC27 EA Bridge request failed"
    )

    return reply({
        "ok": False,
        "error": type(error).__name__,
        "message": (
            "Impossible de récupérer les données EA. "
            "Consulte les logs Render."
        )
    }, 502)


@app.get("/")
@app.get("/health")
def health():
    return reply({
        "ok": True,
        "service": "FC27 EA Python Bridge",
        "version": VERSION,
        "status": "online",
        "mode": "read-only"
    })


@app.get("/api/search")
def search():
    club_name = request.args.get(
        "q", ""
    ).strip()

    if (
        len(club_name) < 3
        or len(club_name) > 60
        or re.search(r"[<>\x00-\x1f]", club_name)
    ):
        return reply({
            "ok": False,
            "error": "INVALID_CLUB_NAME"
        }, 400)

    try:
        def load():
            api = FC27API()
            club_id = api.find_club_id(
                club_name
            )

            if club_id is None:
                return {
                    "ok": True,
                    "found": False,
                    "club": club_name,
                    "clubId": None
                }

            return {
                "ok": True,
                "found": True,
                "club": club_name,
                "clubId": int(club_id),
                "readOnly": True
            }

        result = cached_result(
            "search:" + club_name.casefold(),
            load
        )

        return reply(result)

    except Exception as error:
        return handle_error(error)


@app.get("/api/club/<club_id>/summary")
def club_summary(club_id):
    if not re.fullmatch(r"\d{1,16}", club_id):
        return reply({
            "ok": False,
            "error": "INVALID_CLUB_ID"
        }, 400)

    try:
        def load():
            api = FC27API()

            members = api.get_member_stats(
                int(club_id)
            )

            matches = api.get_club_matches(
                int(club_id),
                match_type="friendlyMatch",
                count=10
            )

            return {
                "ok": True,
                "clubId": int(club_id),
                "membersCount": len(members),
                "friendlyMatchesCount": len(matches),
                "eaConnection": "success",
                "readOnly": True,
                "testedAt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

        result = cached_result(
            "summary:" + club_id,
            load
        )

        return reply(result)

    except Exception as error:
        return handle_error(error)


@app.get("/test")
def test():
    # Test historique conservé,
    # mais désormais protégé par la clé.
    return club_summary("66712")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get("PORT", 10000)
        )
    )
