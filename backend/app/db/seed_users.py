import sys
import os

# Adjust path to import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db.session import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.core.auth import get_password_hash
from app.core.settings import settings


def seed():
    db = SessionLocal()
    try:
        print("Starting seeding process...")

        # 1. Create Admin only when an explicit initial password is supplied.
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            if settings.initial_admin_password and len(settings.initial_admin_password) >= 12:
                admin_user = User(
                    username="admin",
                    password_hash=get_password_hash(settings.initial_admin_password),
                    role="ADMIN",
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)
                print("Seeded admin account.")
            else:
                print("Skipped admin account: INITIAL_ADMIN_PASSWORD is not configured.")
        else:
            print("Admin account already exists.")

        # 2. Create User accounts for employees
        employees = db.query(Employee).all()
        print(f"Found {len(employees)} employees in database.")
        if not settings.initial_user_password or len(settings.initial_user_password) < 12:
            print("Skipped employee accounts: INITIAL_USER_PASSWORD is not configured.")
            return
        for emp in employees:
            # Determine username
            username = None
            if emp.employee_code:
                username = emp.employee_code.strip().lower()
            
            if not username:
                # Fallback to normalized full name
                username = emp.full_name.strip().lower().replace(" ", "")
                if not username:
                    username = f"user_{emp.machine_employee_id}"
            
            # Check if user already exists
            user = db.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=get_password_hash(settings.initial_user_password),
                    role="USER",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Created user account: {username}")
            else:
                print(f"User account for username {username} already exists.")

            # Link employee to user
            if emp.user_id != user.id:
                emp.user_id = user.id
                db.add(emp)
                db.commit()
                print(f"Linked employee {emp.full_name} to user {username}")

        print("Seeding completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
