
from flask import Flask, jsonify
from fc_clubs_api import FC27API
from datetime import datetime, timezone
import threading
import time
import os

app = Flask(__name__)

CLUB_NAME = "CLK ZENITH"
CLUB_ID = 66712
CACHE_SECONDS = 300

cache = {
    "expires": 0,
    "result": None
}

lock = threading.Lock()


@app.get("/")
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "FC27 EA Python Bridge",
        "version": "1.0.0-test",
        "status": "online",
        "mode": "read-only"
    })


@app.get("/test")
def test_ea():
    now = time.time()

    with lock:
        if (
            cache["result"] is not None
            and cache["expires"] > now
        ):
            return jsonify({
                **cache["result"],
                "cached": True
            })

        try:
            api = FC27API()

            found_id = api.find_club_id(
                CLUB_NAME
            )

            if int(found_id) != CLUB_ID:
                return jsonify({
                    "ok": False,
                    "error": "CLUB_ID_MISMATCH",
                    "message": (
                        "Le club trouvé ne correspond "
                        "pas à l'identifiant attendu."
                    )
                }), 502

            members = api.get_member_stats(
                CLUB_ID
            )

            matches = api.get_club_matches(
                CLUB_ID,
                match_type="friendlyMatch",
                count=10
            )

            result = {
                "ok": True,
                "service": "FC27 EA Python Bridge",
                "club": CLUB_NAME,
                "clubId": CLUB_ID,
                "membersCount": len(members),
                "friendlyMatchesCount": len(matches),
                "eaConnection": "success",
                "readOnly": True,
                "testedAt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            cache["result"] = result
            cache["expires"] = (
                time.time() + CACHE_SECONDS
            )

            return jsonify({
                **result,
                "cached": False
            })

        except Exception as error:
            app.logger.exception(
                "EA FC27 connection failed"
            )

            return jsonify({
                "ok": False,
                "service": "FC27 EA Python Bridge",
                "error": type(error).__name__,
                "message": (
                    "La connexion EA a échoué. "
                    "Consulte les logs du serveur."
                )
            }), 502


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
