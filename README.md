# Lost & Found

A web application for a college campus where students can report lost and found items, search through reports, get **automatic match suggestions**, and submit claims to recover their belongings.

Live demo: https://lost-and-found-zeta-drab.vercel.app/login

---

## Features

- **User accounts**: register and log in with a hashed password
- **Report items**: post a lost or found item with name, category, description, location, date and an optional photo
- **Search and filter**: search by item name or location, and filter by category and lost/found type
- **Smart matching**: suggests up to 5 similar items using TF-IDF and cosine similarity, with a match percentage
- **Claim system**: a user can claim an item by sending a message, and the item owner can approve or reject the claim
- **Auto-recovery**: approving a claim marks the item as recovered and rejects the other pending claims for it
- **Admin dashboard**: shows total users, active lost items, active found items and recovered items, lists recent reports and all users, and lets the admin delete items

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| Frontend | HTML, CSS, Jinja2 templates |
| Matching | scikit-learn (TF-IDF, cosine similarity) |
| Security | Werkzeug (password hashing, secure file names) |

---

## How the Smart Matching Works

1. When an item's details page is opened, the app collects all **active** items of the opposite type (lost vs. found).
2. For each item, the name, category, description and location are combined into one text string.
3. `TfidfVectorizer` (English stop words removed) converts the text into numerical vectors.
4. `cosine_similarity` compares the current item with every candidate.
5. Candidates scoring **15% or higher** are shown, sorted by score, with a maximum of 5 results.

---

## Database Schema

**users**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| name | TEXT | Required |
| email | TEXT | Unique, required |
| password | TEXT | Hashed |
| is_admin | INTEGER | 0 = user, 1 = admin |

**items**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| user_id | INTEGER | Foreign key to users |
| name | TEXT | Required |
| category | TEXT | Required |
| description | TEXT | Optional |
| location | TEXT | Required |
| date | TEXT | Required |
| image | TEXT | Uploaded file name |
| type | TEXT | `lost` or `found` |
| status | TEXT | `active` or `recovered` |

**claims**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| item_id | INTEGER | Foreign key to items |
| claimant_id | INTEGER | Foreign key to users |
| message | TEXT | Required |
| status | TEXT | `pending`, `approved` or `rejected` |
| created_at | TIMESTAMP | Defaults to current time |

---

## Routes

| Route | Method | Access | Description |
|---|---|---|---|
| `/` | GET | Public | Home page |
| `/register` | GET, POST | Public | Create an account |
| `/login` | GET, POST | Public | Log in |
| `/logout` | GET | Logged in | Clear session |
| `/dashboard` | GET | Logged in | User dashboard |
| `/report/<lost\|found>` | GET, POST | Logged in | Report an item |
| `/items` | GET | Public | Browse, search and filter active items |
| `/item/<id>` | GET | Public | Item details and match suggestions |
| `/item/<id>/claim` | GET, POST | Logged in | Submit a claim (not allowed on your own item) |
| `/item/<id>/recovered` | GET | Item owner | Mark an item as recovered |
| `/claims` | GET | Logged in | Claims received on your items |
| `/claims/<id>/<approve\|reject>` | GET | Item owner | Approve or reject a claim |
| `/admin` | GET | Admin | Admin dashboard |
| `/admin/delete-item/<id>` | GET | Admin | Delete an item |

---

## Project Structure

```
lost-and-found/
├── app.py                # Flask application (routes, database, matching)
├── database.db           # SQLite database
├── requirements.txt      # Python dependencies
├── README.md
├── static/
│   └── uploads/          # Uploaded item images
└── templates/            # HTML templates (Jinja2)
```

---

## Installation and Setup

**Prerequisites:** Python 3.9 or higher

```bash
# 1. Clone the repository
git clone <your-repository-url>
cd lost-and-found

# 2. (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

On first run, the tables are created automatically and a default admin account is added.

---

## Default Admin Login

| Field | Value |
|---|---|
| Email | `admin@college.com` |
| Password | `admin123` |

> Change this password before any real deployment.

---

## Security Measures

- Passwords are hashed with Werkzeug and never stored as plain text
- All database queries are parameterised, which protects against SQL injection
- Uploaded file names are sanitised with `secure_filename`
- Claim and admin actions check ownership or admin rights on the server
- Users cannot claim their own items

---

## Known Limitations and Future Improvements

- Move the secret key to an environment variable and turn off `debug` mode in production
- Change state-changing actions (approve, reject, delete) from GET links to POST requests with CSRF protection
- Validate upload file type and size
- Delete related claims when an item is deleted
- Add email notifications for new matches and claims
- Improve matching with word embeddings so "bag" and "backpack" are treated as similar, and add image-based matching
- Use PostgreSQL and cloud image storage (such as Cloudinary or S3) for hosted deployment, since serverless platforms like Vercel do not keep local files or SQLite writes permanently

---

## Author

- **Name:** Daman Kumar
- **Course / Department:** B.Tech Cse DS 
- **College:** AKTU
