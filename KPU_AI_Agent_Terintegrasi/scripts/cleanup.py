"""Remove expired anonymous sessions and old request counters.

Run periodically with a job scheduler. NEVER run via a public API.
"""
import time
from sqlalchemy import delete
from app.db.models import AnonymousSession, UsageWindow, utcnow
from app.db.session import get_engine
from sqlalchemy.orm import Session


def main():
    with Session(get_engine()) as db:
        db.execute(delete(UsageWindow).where(UsageWindow.minute < int(time.time() // 60) - 120))
        db.execute(delete(AnonymousSession).where(AnonymousSession.expires_at < utcnow()))
        db.commit()
    print("Expired sessions and usage counters cleaned.")


if __name__ == "__main__":
    main()
