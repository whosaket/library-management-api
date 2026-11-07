import mysql.connector

# ---- Edit these (same values as in load_library.py) ----
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your-password",
    "database": "library_management",
}
# --------------------------------------------------------


def get_connection():
    """Open a new MySQL connection. Call once per request and close it after."""
    return mysql.connector.connect(**DB_CONFIG)
