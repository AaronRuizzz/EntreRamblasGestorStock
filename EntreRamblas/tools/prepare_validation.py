"""Create the isolated test database without touching the development database."""
import psycopg2

connection = psycopg2.connect(
    dbname="postgres", host="127.0.0.1", port=55432, user="mgs_test",
)
connection.autocommit = True
with connection.cursor() as cursor:
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", ["mgs_validation"])
    if not cursor.fetchone():
        cursor.execute("CREATE DATABASE mgs_validation ENCODING 'UTF8' TEMPLATE template0")
        print("Created isolated database mgs_validation")
    else:
        print("Using existing isolated database mgs_validation")
connection.close()
