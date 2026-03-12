import os
from flask import Flask, render_template, request, jsonify
import pymysql

app = Flask(__name__)

# =============================
# DATABASE CONFIG (Railway)
# =============================
DB_HOST = os.getenv("MYSQLHOST")
DB_PORT = int(os.getenv("MYSQLPORT", 3306))
DB_USER = os.getenv("MYSQLUSER")
DB_PASSWORD = os.getenv("MYSQLPASSWORD")
DB_NAME = os.getenv("MYSQLDATABASE")

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

# =============================
# ROUTES
# =============================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/songs")
def songs():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM bannhac")
        data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@app.route("/favorites")
def favorites():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM favorites")
        data = cursor.fetchall()
    conn.close()
    return jsonify(data)

# =============================
# HEALTH CHECK
# =============================

@app.route("/health")
def health():
    return {"status": "ok"}

# =============================
# RUN SERVER
# =============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Server running on port {port}")
    app.run(host="0.0.0.0", port=port)
