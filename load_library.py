import csv
import mysql.connector

# ---- Edit these ----
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your-password",
}
DB_NAME = "library_management"
CSV_FOLDER = "."  # folder that holds the 5 CSV files
# --------------------

TABLES = {
    "category": """
        CREATE TABLE IF NOT EXISTS category (
            cat_id INT PRIMARY KEY,
            cname VARCHAR(50) NOT NULL
        )""",
    "publisher": """
        CREATE TABLE IF NOT EXISTS publisher (
            pub_id INT PRIMARY KEY,
            pname VARCHAR(100) NOT NULL
        )""",
    "members": """
        CREATE TABLE IF NOT EXISTS members (
            member_id INT PRIMARY KEY,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            phone_no VARCHAR(15),
            doj DATE,
            status VARCHAR(10)
        )""",
    "books": """
        CREATE TABLE IF NOT EXISTS books (
            book_id INT PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            author VARCHAR(100),
            category_id INT,
            publisher_id INT,
            publication_year INT,
            FOREIGN KEY (category_id) REFERENCES category(cat_id),
            FOREIGN KEY (publisher_id) REFERENCES publisher(pub_id)
        )""",
    "issue": """
        CREATE TABLE IF NOT EXISTS issue (
            transaction_id INT PRIMARY KEY,
            book_id INT,
            member_id INT,
            issue_date DATE,
            due_date DATE,
            return_date DATE NULL,
            status VARCHAR(10),
            FOREIGN KEY (book_id) REFERENCES books(book_id),
            FOREIGN KEY (member_id) REFERENCES members(member_id)
        )""",
}

# Parent tables first so foreign keys are satisfied
LOAD_ORDER = ["category", "publisher", "members", "books", "issue"]
CSV_FILES = {
    "category": "category.csv",
    "publisher": "publisher.csv",
    "members": "members.csv",
    "books": "books.csv",
    "issue": "issue.csv",
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [[(v if v != "" else None) for v in row] for row in reader]
    return header, rows


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cur.execute(f"USE {DB_NAME}")

    for name in LOAD_ORDER:
        cur.execute(TABLES[name])

    for name in LOAD_ORDER:
        header, rows = read_csv(f"{CSV_FOLDER}/{CSV_FILES[name]}")
        placeholders = ", ".join(["%s"] * len(header))
        sql = f"INSERT INTO {name} ({', '.join(header)}) VALUES ({placeholders})"
        cur.executemany(sql, rows)
        print(f"{name}: inserted {cur.rowcount} rows")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
