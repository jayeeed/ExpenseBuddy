import psycopg2
import os
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

db_uri = os.getenv("POSTGRES_URL")


def init_db():
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            date TEXT,
            price TEXT,
            category TEXT,
            description TEXT
        )
        """
    )
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print("Connected to:", db_version)

    conn.commit()
    return conn


conn = init_db()


def save_to_db(expense_data):
    with psycopg2.connect(db_uri) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO expenses (id, user_id, date, price, category, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                expense_data["id"],
                expense_data["user_id"],
                expense_data["date"],
                expense_data["price"],
                expense_data["category"].lower(),
                expense_data["description"].lower(),
            ),
        )
        conn.commit()


def db_query(query):
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(query)
    result = cursor.fetchall()

    return result
