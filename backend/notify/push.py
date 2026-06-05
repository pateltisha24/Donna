"""
Web Push delivery via VAPID.

Sends notifications to stored browser subscriptions. Configuration comes from
env (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_CLAIM_EMAIL). If the keys are
absent, push is silently disabled so the app still runs.
"""

import json
import logging
import os

from memory.mongo_store import MongoStore

logger = logging.getLogger("donna.push")

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "mailto:admin@donna.local")


def push_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def send_to_all(title: str, body: str, store: MongoStore | None = None) -> int:
    """Send a notification to every stored subscription. Returns count delivered."""
    if not push_enabled():
        logger.info("Push disabled (no VAPID keys) — skipping notification")
        return 0

    from pywebpush import WebPushException, webpush

    store = store or MongoStore()
    payload = json.dumps({"title": title, "body": body})
    delivered = 0

    for sub in store.get_subscriptions():
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
            delivered += 1
        except WebPushException as e:
            # 404/410 mean the subscription is dead — prune it.
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                store.delete_subscription(sub.get("endpoint", ""))
                logger.info("Pruned expired push subscription")
            else:
                logger.warning("Push failed: %s", e)
        except Exception as e:  # noqa: BLE001
            logger.warning("Push error: %s", e)

    return delivered
