# ShareShelf

A peer-to-peer lending library for everyday tools and equipment. Residents list items they rarely use, and neighbors borrow them instead of buying new ones.

**Student:** Shanly Lariosa Dakay
**Section:** G02
**Subject:** IT317 / IM2

## Tech Stack

- Django (backend and frontend via Django templates)
- PostgreSQL hosted on Supabase
- Bootstrap 5

## Features

- **Registration** with validation (required fields, email format, unique email, password confirmation) and hashed passwords
- **Login / Logout** using email as the username, with error messages for invalid credentials
- **Role-based dashboards** for Admin and Member, with URL access control so one role cannot open the other's pages
- **User profile** where members view and edit their own details and profile photo
- **Manage Users** (Admin only) with search, filters, and activate/deactivate
- **Item Listing** for lenders, including categories, 1 to 5 photos, availability windows, editing, unlisting, and deletion rules
- **Browse and Search** for items in the user's community, filtered by category and item name
- **Borrow Requests** with date and availability validation, owner approval or decline, borrower cancellation, expiry, and active-request limits
- **Pickup/Return Confirmation** with two-party handoff confirmation and status transitions
- **Ratings and Reviews** with completed-transaction eligibility, average recalculation, and account flagging
- **Notifications** with request, handoff, rating, due-date, overdue, and wishlist alerts
- **Wishlist** entries with category or keyword matching, the 10-active-entry limit, and same-community alerts

The SDD's lender/borrower/both role is implemented as `user_type`. The separate `role` field identifies Admin versus Member accounts and supports the two-dashboard design.

## User Roles

| Role | Access |
|---|---|
| Admin | Admin dashboard, Manage Users, own profile |
| Member | Member dashboard, own profile. Registers as Lender, Borrower, or Both |

## Setup

1. Clone the repository
   ```bash
   git clone https://github.com/shawnly2004-ctrl/ShareShelf-Dakay-Shanly-G02.git
   cd ShareShelf-Dakay-Shanly-G02
   ```
2. Create and activate a virtual environment
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` in the project root, then replace the placeholder values with your private Django and Supabase credentials. PowerShell:
   ```powershell
   Copy-Item .env.example .env
   ```
   Keep `DEBUG=True` only for local development. `.env` is ignored by Git; never commit or share it.
4. Create a `.env` file in the project root (this file is not in the repo):
   ```
   SECRET_KEY=your-secret-key
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost
   DB_NAME=postgres
   DB_USER=your-supabase-user
   DB_PASSWORD=your-supabase-password
   DB_HOST=your-supabase-pooler-host
   DB_PORT=5432
   ```
   When deploying, set `ALLOWED_HOSTS` to the hostnames serving the application.
5. Run migrations and create an admin account
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```
6. Start the server
   ```bash
   python manage.py runserver
   ```
   Open http://127.0.0.1:8000/

## Notes

- Credentials are stored in `.env`, which is excluded from version control.
- Admins deactivate accounts instead of deleting them, to preserve transaction history for later features.
- The Django admin site is not used as the main admin panel. The system has its own custom Admin dashboard.