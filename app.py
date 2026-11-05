
import os
import re
import hmac
import time
import threading
import json

from datetime import datetime, timezone
from flask import Flask, jsonify, request
from fc_clubs_api import FC27API

app = Flask(__name__)

VERSION = "7.8.2"
CACHE_SECONDS = 300
MAX_RESPONSE_BYTES = 1_500_000

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
    if request.path in ("/", "/health"):
        return None

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
            "Données EA indisponibles. "
            "Consulter les logs Render."
        )
    }, 502)


def validate_club_id(club_id):
    return bool(
        re.fullmatch(r"\d{1,16}", club_id)
    )


def safe_ea_data(data):
    """
    Vérifie que les données peuvent être
    renvoyées en JSON et limite leur taille.
    """
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        default=str
    )

    if len(encoded.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError(
            "EA_RESPONSE_TOO_LARGE"
        )

    return json.loads(encoded)


def count_items(data):
    if isinstance(data, (list, tuple, dict)):
        return len(data)

    return None


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
    if not validate_club_id(club_id):
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
                "membersCount": count_items(members),
                "friendlyMatchesCount": count_items(matches),
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


@app.get("/api/club/<club_id>/members")
def club_members(club_id):
    if not validate_club_id(club_id):
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

            members = safe_ea_data(members)

            return {
                "ok": True,
                "clubId": int(club_id),
                "source": "EA FC27",
                "readOnly": True,
                "membersCount": count_items(members),
                "data": members,
                "fetchedAt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

        result = cached_result(
            "members:" + club_id,
            load
        )

        return reply(result)

    except Exception as error:
        return handle_error(error)


@app.get("/api/club/<club_id>/friendlies")
def club_friendlies(club_id):
    if not validate_club_id(club_id):
        return reply({
            "ok": False,
            "error": "INVALID_CLUB_ID"
        }, 400)

    # Opt-in only: legacy callers keep their flattened match records.
    output_format = request.args.get("format", "records")
    if output_format not in ("records", "raw"):
        return reply({"ok": False, "error": "INVALID_FORMAT"}, 400)

    try:
        def load():
            api = FC27API()

            matches = api.get_club_matches(
                int(club_id),
                match_type="friendlyMatch",
                count=10,
                output=output_format
            )

            matches = safe_ea_data(matches)

            return {
                "ok": True,
                "clubId": int(club_id),
                "source": "EA FC27",
                "matchType": "friendlyMatch",
                "readOnly": True,
                "matchesCount": count_items(matches),
                "data": matches,
                "fetchedAt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

        result = cached_result(
            "friendlies:" + club_id + ":" + output_format,
            load
        )

        return reply(result)

    except Exception as error:
        return handle_error(error)


@app.get("/test")
def test():
    return club_summary("66712")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get("PORT", 10000)
        )
    )
