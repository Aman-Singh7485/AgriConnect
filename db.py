import mysql.connector
from mysql.connector import Error


def get_db_connection():
    try:
        return mysql.connector.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="Aman@321",
            database="agriconnect"
        )
    except Error as error:
        print(f"Database connection failed: {error}")
        return None