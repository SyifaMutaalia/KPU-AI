"""Create the first administrator interactively; no password is accepted on argv."""

import argparse
import getpass
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_security import hash_password
from app.db.models import AdminAuditLog, AdminUser
from app.db.session import get_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap one initial Admin KPU account"
    )
    parser.add_argument(
        "email", help="Email admin (kata sandi tidak pernah menjadi argumen CLI)"
    )
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not re.fullmatch(r"[^@\s]{1,128}@[^@\s]{1,190}\.[^@\s]{2,63}", email):
        parser.error("Format email tidak valid.")
    if not sys.stdin.isatty():
        parser.error(
            "Jalankan secara interaktif agar kata sandi tidak masuk shell history."
        )
    password = getpass.getpass("Kata sandi awal (min. 12 karakter): ")
    confirmation = getpass.getpass("Ulangi kata sandi: ")
    if len(password) < 12 or len(password) > 128:
        parser.error("Kata sandi harus 12–128 karakter.")
    if password != confirmation:
        parser.error("Kata sandi tidak cocok.")
    with Session(get_engine()) as db:
        if db.scalar(select(AdminUser.id).limit(1)):
            parser.error(
                "Admin sudah ada; bootstrap hanya dapat membuat admin pertama."
            )
        if db.scalar(select(AdminUser.id).where(AdminUser.email == email)):
            parser.error("Email tersebut sudah terdaftar.")
        user = AdminUser(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        db.add(
            AdminAuditLog(
                actor_user_id=user.id,
                action="admin.bootstrap",
                target_type="admin_user",
                target_id=user.id,
                details="{}",
            )
        )
        db.commit()
    print(
        f"Admin {email} dibuat. Login pertama akan mewajibkan penggantian kata sandi."
    )


if __name__ == "__main__":
    main()
