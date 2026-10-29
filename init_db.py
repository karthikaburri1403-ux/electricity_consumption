import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

SCHEMA_FILE = Path(__file__).parent / "sql" / "schema.sql"


def main():
    # Connect WITHOUT choosing a database, because it may not exist yet
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = conn.cursor()

    script = SCHEMA_FILE.read_text(encoding="utf-8")
    # drop full-line comments, then run the script one statement at a time
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    for statement in "\n".join(lines).split(";"):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)

    conn.commit()
    cursor.close()
    conn.close()
    print("Database ready: electricity_db created with empty tables.")


if __name__ == "__main__":
    main()