import importlib
import subprocess
import sys

REQUIRED_LIBRARIES = {
    'flask': 'flask',
    'flask_paginate': 'flask-paginate',
    'mysql.connector': 'mysql-connector-python',
    'pymysql': 'pymysql',
    'dotenv': 'python-dotenv',
    'werkzeug': 'werkzeug',
    'flask_wtf': 'flask-wtf'
}

def check_and_install():
    for lib, pkg in REQUIRED_LIBRARIES.items():
        try:
            importlib.import_module(lib)
            print(f"Đã cài đặt: {lib}")
        except ImportError:
            print(f"Đang cài đặt {lib}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

if __name__ == "__main__":
    check_and_install()
    print("Tất cả thư viện đã sẵn sàng!")