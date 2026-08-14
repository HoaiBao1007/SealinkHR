import sys
import os

# Adjust path to import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db.session import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.core.auth import get_password_hash
from app.core.settings import settings
from app.core.roles import IT_ADMIN


def seed_admin():
    db = SessionLocal()
    try:
        print("Starting seeding of shared IT account admin_sealink...")

        # Check if username "admin_sealink" exists
        admin_user = db.query(User).filter(User.username == "admin_sealink").first()
        if not admin_user:
            initial_password = settings.initial_admin_password
            if not initial_password or len(initial_password) < 12 or initial_password.lower().startswith("replace-"):
                print("Skipping admin creation: set a strong INITIAL_ADMIN_PASSWORD (at least 12 characters) in .env.")
                return
            admin_user = User(
                username="admin_sealink",
                password_hash=get_password_hash(initial_password),
                role=IT_ADMIN,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("Successfully seeded admin_sealink account!")
            print(f"Role: {IT_ADMIN}")
        else:
            print("admin_sealink account already exists.")
            if admin_user.role != IT_ADMIN:
                admin_user.role = IT_ADMIN
                db.add(admin_user)
                db.commit()
                print(f"Updated role to {IT_ADMIN}.")

        admin_employee = db.query(Employee).filter(Employee.user_id == admin_user.id).first()
        if not admin_employee:
            admin_employee = db.query(Employee).filter(Employee.machine_employee_id == "ADMIN_SEALINK").first()
            if admin_employee and admin_employee.user_id not in (None, admin_user.id):
                raise RuntimeError("ADMIN_SEALINK is already linked to another user.")
            if not admin_employee:
                admin_employee = Employee(
                    machine_employee_id="ADMIN_SEALINK",
                    full_name="SEALINK Administrator",
                    department_name="Administration",
                    is_active=False,
                )
                db.add(admin_employee)
            admin_employee.user_id = admin_user.id
            db.commit()
            print("Linked administrator to an audit profile.")

    except Exception as e:
        db.rollback()
        print(f"Error seeding admin_sealink: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
