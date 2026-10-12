import getpass

from app.auth import hash_password
from app.database import SessionLocal
from app.models.facility import AdminUser


def main():
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password (8+ characters): ")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters")
    db = SessionLocal()
    try:
        username = username.lower()
        if db.query(AdminUser).filter(AdminUser.username == username).first():
            raise SystemExit("Admin username already exists")
        db.add(AdminUser(username=username, password_hash=hash_password(password), role="SUPERADMIN"))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
