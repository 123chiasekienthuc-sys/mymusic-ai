# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_paginate import Pagination, get_page_args
import mysql.connector
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_wtf.csrf import CSRFProtect

from config import DB_CONFIG
import sys
from pathlib import Path

import pymysql
from pymysql.constants import CLIENT
import getpass
from dotenv import load_dotenv
import json

import time
from functools import wraps
from flask import make_response  # Thêm dòng này vào import flask hiện có
import random
from threading import Thread
from queue import Queue
import uuid

# Thêm import mới ở đầu file
from ai_assistant import sql_assistant
import json

# --- CẤU HÌNH --- #
load_dotenv()  # Load biến môi trường từ file .env

BACKUP_PATH = Path("data/mymusic.sql")  # Đường dẫn mặc định
DEFAULT_PASSWORD = "123456"  # Password mặc định

# --- HÀM CHÍNH --- #
import getpass
from pymysql.constants import CLIENT

def get_db_config():
    """Lấy thông tin kết nối database"""

    print("\n🔧 NHẬP THÔNG TIN DATABASE (Enter để dùng Railway mặc định)")

    config = {
        'host': input("MySQL Host [switchback.proxy.rlwy.net]: ").strip() or "switchback.proxy.rlwy.net",
        'port': int(input("Port [53475]: ").strip() or 53475),
        'user': input("Username [root]: ").strip() or "root",
        'database': input("Database [railway]: ").strip() or "railway",
        'charset': 'utf8mb4',
        'client_flag': CLIENT.MULTI_STATEMENTS
    }

    password = getpass.getpass("Password (Railway MySQL): ").strip()
    config['password'] = password

    return config


def restore_database(config, backup_file):
    """Khôi phục database từ file SQL"""

    conn = None

    try:
        print(f"\n🔗 Đang kết nối MySQL tại {config['host']}:{config['port']}...")

        conn = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            charset=config['charset'],
            client_flag=config['client_flag'],
            autocommit=True
        )

        with conn.cursor() as cursor:

            # Kiểm tra phiên bản MySQL
            cursor.execute("SELECT VERSION()")
            print(f"⚙️ MySQL Version: {cursor.fetchone()[0]}")

            print(f"\n📥 Đang import dữ liệu từ {backup_file}...")

            # Tắt kiểm tra khóa ngoại
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")

            sql_command = ""

            with open(backup_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # Bỏ qua comment
                    if line.startswith("--") or line == "":
                        continue

                    sql_command += line + " "

                    # Khi gặp dấu ; thì chạy câu SQL
                    if line.endswith(";"):
                        try:
                            cursor.execute(sql_command)
                        except Exception as e:
                            print("⚠️ Lỗi SQL:", e)

                        sql_command = ""

            # Bật lại khóa ngoại
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")

        print("\n✅ KHÔI PHỤC DATABASE THÀNH CÔNG!")
        print("\n🔑 Thông tin kết nối:")
        print(f"- Host: {config['host']}")
        print(f"- Port: {config['port']}")
        print(f"- Database: {config['database']}")
        print(f"- Username: {config['user']}")

    except pymysql.Error as e:
        print(f"\n❌ LỖI MySQL ({e.args[0]}): {e.args[1]}")

    except FileNotFoundError:
        print(f"\n❌ KHÔNG TÌM THẤY FILE: {backup_file}")

    except Exception as e:
        print(f"\n❌ LỖI KHÔNG XÁC ĐỊNH: {str(e)}")

    finally:
        if conn:
            conn.close()





# 1. Xác định đường dẫn gốc
if getattr(sys, 'frozen', False):
    base_path = Path(sys.executable).parent  # Lấy thư mục chứa file .exe
else:
    base_path = Path(__file__).parent.absolute()

# 2. Định nghĩa đường dẫn các thư mục (Dùng viết thường cho 'static' và 'templates')
static_dir = base_path / 'static'
template_dir = base_path / 'templates'
data_dir = base_path / 'data'

# 3. Chỉ tạo thư mục nếu nó chưa tồn tại (Dùng try-except để tránh lỗi Access Denied trên Windows)
#for dir_path in [static_dir, template_dir, data_dir]:
#   try:
#       if not dir_path.exists():
#            dir_path.mkdir(parents=True, exist_ok=True)
#    except OSError as e:
#        print(f"Cảnh báo: Không thể tạo thư mục {dir_path}: {e}")

# 4. Cấu hình Flask chuẩn
app = Flask(__name__, 
            template_folder=str(template_dir),
            static_folder=str(static_dir))

app.secret_key = 'your-secret-key-here'  # <-- Thêm dòng này (dùng key phức tạp hơn cho production)
csrf = CSRFProtect(app)  # Rồi mới khởi tạo CSRF

# ===== THÊM MỚI: Rate Limiting =====
request_history = {}

def rate_limit(max_requests=5, time_window=60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            
            if client_ip not in request_history:
                request_history[client_ip] = []
            
            request_history[client_ip] = [
                req_time for req_time in request_history[client_ip]
                if current_time - req_time < time_window
            ]
            
            if len(request_history[client_ip]) >= max_requests:
                return jsonify({
                    "status": "Loi",
                    "feedback": f"Bạn đã gửi quá {max_requests} request trong {time_window} giây. Vui lòng đợi!"
                }), 429
            
            request_history[client_ip].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
# ===== KẾT THÚC Rate Limiting =====

# ===== THÊM MỚI: Retry Mechanism cho Gemini =====
# --- CẤU HÌNH GOOGLE AI ---
from google import genai
from google.genai import types

# Khởi tạo client (giữ nguyên của bạn)
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

def call_gemini_with_retry(prompt, retries=3, delay=5):
    """
    Hàm gọi Gemini có khả năng tự động thử lại nếu gặp lỗi 429
    """
    for i in range(retries):
        try:
            # Sử dụng model flash-8b để có hạn mức cao hơn
            response = client.models.generate_content(
                model='gemini-1.5-flash-8b', 
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=500, # Giới hạn để tiết kiệm token
                    temperature=0.7
                )
            )
            return response.text
        except Exception as e:
            # Nếu là lỗi quá tải (429) và chưa hết số lần thử
            if "429" in str(e) and i < retries - 1:
                print(f"⚠️ Hết hạn mức Gemini (429). Đang đợi {delay} giây để thử lại lần {i+1}...")
                time.sleep(delay)
                delay *= 2 # Tăng thời gian đợi gấp đôi cho lần sau (Exponential backoff)
                continue
            else:
                print(f"❌ Lỗi AI: {str(e)}")
                return f"Lỗi: {str(e)}"
    return "Hệ thống AI hiện đang quá tải, vui lòng thử lại sau vài phút."

# Kết nối database
def get_db_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn

# THÊM: Cấu hình upload ảnh ca sĩ
SINGER_IMAGE_FOLDER = 'static/images/singers'
app.config['SINGER_IMAGE_FOLDER'] = SINGER_IMAGE_FOLDER

# Tạo thư mục nếu chưa tồn tại
os.makedirs(SINGER_IMAGE_FOLDER, exist_ok=True)
# Google API
from google import genai
# Khởi tạo AI (GEMINI_API_KEY nằm trong file .env nhé)
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# Khi muốn dùng AI để chấm điểm SQL:
# response = client.models.generate_content(model='gemini-1.5-flash', contents='Câu hỏi của bạn...')
# print(response.text)

# --- ROUTES & API ---

@app.route('/')
def index():
    return render_template('index.html')

# Cập nhật route /thuc-hanh-ai
@app.route('/thuc-hanh-ai', methods=['GET', 'POST'])
@csrf.exempt 
def thuc_hanh_ai():
    # In debug để xem dữ liệu
    print("=== THUC HANH AI ===")
    print("Method:", request.method)
    print("Content-Type:", request.content_type)
    
    # Xử lý GET request - hiển thị trang
    if request.method == 'GET':
        return render_template('thuc_hanh_ai.html')
    
    # Xử lý POST request - API
    try:
        # Lấy dữ liệu từ request
        if request.is_json:
            data = request.get_json()
            print("JSON data:", data)
        else:
            data = request.form.to_dict()
            print("Form data:", data)
        
        if not data:
            return jsonify({
                "status": "Loi",
                "message": "Không nhận được dữ liệu",
                "score": 0,
                "feedback": "Vui lòng nhập câu lệnh SQL!"
            })
        
        action = data.get('action', 'evaluate')
        sql_query = data.get('sql_query', '').strip()
        exercise_id = data.get('exercise_id', '1')
        
        if not sql_query:
            return jsonify({
                "status": "Loi",
                "message": "Câu lệnh SQL trống",
                "score": 0,
                "feedback": "Vui lòng nhập câu lệnh SQL!"
            })
        
        if action == 'evaluate':
            # Sử dụng AI để đánh giá
            result = sql_assistant.evaluate_sql(sql_query, exercise_id)
            
            # Thêm SQL mẫu nếu có
            if exercise_id in sql_assistant.sample_exercises:
                result['sql_chuan'] = sql_assistant.sample_exercises[exercise_id]['solution']
            
            # Đảm bảo có đủ các trường cần thiết
            return jsonify({
                "status": result.get('status', 'unknown'),
                "message": result.get('message', 'Đã đánh giá câu lệnh SQL'),
                "feedback": result.get('feedback', ''),
                "score": result.get('score', 0),
                "sql_chuan": result.get('sql_chuan', '')
            })
            
        elif action == 'execute':
            # Thực thi SQL an toàn
            result = sql_assistant.execute_sql_safe(sql_query)
            return jsonify(result)
            
    except Exception as e:
        print(f"Lỗi: {str(e)}")
        return jsonify({
            "status": "Loi",
            "message": f"Lỗi xử lý: {str(e)}",
            "feedback": "Có lỗi xảy ra, vui lòng thử lại!",
            "score": 0,
            "sql_chuan": ""
        })

# API thực thi SQL an toàn
@app.route('/api/execute-sql', methods=['POST'])
@csrf.exempt
def execute_sql_api():
    """API thực thi câu lệnh SQL an toàn (chỉ SELECT)"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({
                "success": False,
                "error": "Vui lòng nhập câu lệnh SQL"
            })
        
        result = sql_assistant.execute_sql_safe(sql)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# API tạo bài tập mới bằng AI
@app.route('/api/generate-exercise', methods=['POST'])
@csrf.exempt  # Thêm dòng này để tránh lỗi CSRF
def generate_exercise_api():
    """API tạo bài tập SQL mới bằng AI"""
    try:
        # Lấy dữ liệu từ request (có thể có hoặc không)
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict() or {}
        
        topic = data.get('topic', '')
        print(f"📝 Đang tạo bài tập mới với topic: {topic}")
        
        # Sử dụng AI để tạo bài tập mới
        exercise = sql_assistant.generate_exercise(topic)
        
        # Đảm bảo exercise có đủ các trường cần thiết
        if not isinstance(exercise, dict):
            exercise = {}
        
        # Tạo bài tập mẫu nếu AI không trả về kết quả
        if not exercise or 'title' not in exercise:
            import random
            sample_exercises = [
                {
                    'title': 'Tìm tất cả bản nhạc của thể loại "Nhạc trẻ"',
                    'description': 'Viết câu lệnh SQL để lấy danh sách các bản nhạc thuộc thể loại "Nhạc trẻ"',
                    'solution': "SELECT * FROM bannhac WHERE theloai = 'Nhạc trẻ'",
                    'hint': 'Sử dụng WHERE để lọc theo thể loại'
                },
                {
                    'title': 'Đếm số lượng ca sĩ',
                    'description': 'Đếm tổng số ca sĩ trong database',
                    'solution': 'SELECT COUNT(*) as tong_so FROM casi',
                    'hint': 'Sử dụng hàm COUNT(*)'
                },
                {
                    'title': 'Tìm nhạc sĩ sinh năm 1950',
                    'description': 'Liệt kê các nhạc sĩ sinh năm 1950',
                    'solution': "SELECT * FROM nhacsi WHERE YEAR(ngaysinh) = 1950",
                    'hint': 'Dùng hàm YEAR() để lấy năm từ ngày sinh'
                }
            ]
            exercise = random.choice(sample_exercises)
        
        print(f"✅ Đã tạo bài tập: {exercise.get('title', 'Không có tiêu đề')}")
        return jsonify(exercise)
        
    except Exception as e:
        print(f"❌ Lỗi tạo bài tập: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Trả về bài tập mẫu khi có lỗi
        fallback_exercise = {
            'title': 'Liệt kê tất cả bản nhạc',
            'description': 'Viết câu lệnh SQL để lấy danh sách tất cả bản nhạc trong database',
            'solution': 'SELECT * FROM bannhac',
            'hint': 'Sử dụng SELECT * FROM [tên_bảng]'
        }
        return jsonify(fallback_exercise)

# API lấy danh sách bài tập
@app.route('/api/exercises', methods=['GET'])
def get_exercises_api():
    """API lấy danh sách bài tập SQL"""
    exercises = []
    for id, ex in sql_assistant.sample_exercises.items():
        exercises.append({
            'id': id,
            'title': ex['title'],
            'description': ex['description']
        })
    return jsonify(exercises)

# API lấy chi tiết bài tập
@app.route('/api/exercises/<exercise_id>', methods=['GET'])
def get_exercise_detail_api(exercise_id):
    """API lấy chi tiết bài tập"""
    if exercise_id in sql_assistant.sample_exercises:
        ex = sql_assistant.sample_exercises[exercise_id]
        return jsonify({
            'id': exercise_id,
            'title': ex['title'],
            'description': ex['description'],
            'hint': ex['hint'],
            'solution': ex['solution']
        })
    return jsonify({"error": "Không tìm thấy bài tập"}), 404

# API chat với AI assistant
@app.route('/api/ai-chat', methods=['POST'])
@csrf.exempt
def ai_chat_api():
    """API chat với AI assistant về SQL"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Không nhận được dữ liệu"
            })
        
        message = data.get('message', '').strip()
        context = data.get('context', '')
        
        print(f"🤖 AI Chat - Message: {message}")  # Debug
        print(f"📚 AI Chat - Context: {context}")  # Debug
        
        if not message:
            return jsonify({
                "success": False,
                "error": "Vui lòng nhập câu hỏi"
            })
        
        # Sử dụng method chat_response mới
        response = sql_assistant.chat_response(message, context)
        if not response:
            return jsonify({
            "success": False,
            "error": "AI không tạo được phản hồi"
            })
        return jsonify({
            "success": True,
            "response": response
        })
        
    except Exception as e:
        print(f"❌ AI Chat Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

# API kiểm tra cú pháp SQL
@app.route('/api/validate-sql', methods=['POST'])
@csrf.exempt
def validate_sql_api():
    """API kiểm tra cú pháp SQL"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({
                "valid": False,
                "error": "Câu lệnh SQL trống"
            })
        
        # Chỉ kiểm tra cú pháp, không thực thi
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        try:
            # Thử phân tích cú pháp
            cursor.execute(f"EXPLAIN {sql}")
            return jsonify({
                "valid": True,
                "message": "Cú pháp SQL hợp lệ"
            })
        except mysql.connector.Error as err:
            return jsonify({
                "valid": False,
                "error": f"Lỗi cú pháp: {err.msg}"
            })
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({
            "valid": False,
            "error": str(e)
        })

# API thống kê học tập
@app.route('/api/learning-stats', methods=['GET'])
def learning_stats_api():
    """API thống kê quá trình học tập"""
    # Trong thực tế, bạn nên lưu lịch sử học tập vào database
    # Đây là dữ liệu mẫu
    return jsonify({
        "total_exercises": len(sql_assistant.sample_exercises),
        "completed": 0,  # Sẽ cập nhật khi có tính năng lưu lịch sử
        "accuracy": 0,
        "streak": 0,
        "recommendations": [
            {
                "title": "Luyện tập JOIN",
                "description": "Bài tập về kết hợp nhiều bảng",
                "exercise_id": "4"
            },
            {
                "title": "Thực hành GROUP BY",
                "description": "Bài tập về nhóm và thống kê",
                "exercise_id": "3"
            }
        ]
    })


@app.route('/api/stats')
def get_database_stats():
    """Lấy thống kê tổng hợp trong 1 lần kết nối"""
    try:
        with db_cursor() as cursor:
            queries = {
                'nhacsi': "SELECT COUNT(*) as count FROM nhacsi",
                'casi': "SELECT COUNT(*) as count FROM casi",
                'bannhac': "SELECT COUNT(*) as count FROM bannhac",
                'banthuam': "SELECT COUNT(*) as count FROM banthuam"
            }
            results = {}
            for key, sql in queries.items():
                cursor.execute(sql)
                results[key] = cursor.fetchone()['count']
            return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API lấy danh sách nhạc sĩ
@app.route('/api/nhacsi')
def get_nhacsi():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM nhacsi")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

# API thêm nhạc sĩ
@app.route('/api/nhacsi', methods=['POST'])
def add_nhacsi1():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO nhacsi (tennhacsi, ngaysinh, tieusu) VALUES (%s, %s, %s)",
        (data['tennhacsi'], data['ngaysinh'], data['tieusu'])
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

# Tương tự cho các API khác (ca sĩ, bản nhạc, bản thu âm)
# Thêm các API endpoint mới
@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    stats = {}
    
    # Đếm số lượng nhạc sĩ
    cursor.execute("SELECT COUNT(*) as count FROM nhacsi")
    stats['nhacsi'] = cursor.fetchone()['count']
    
    # Đếm số lượng ca sĩ
    cursor.execute("SELECT COUNT(*) as count FROM casi")
    stats['casi'] = cursor.fetchone()['count']
    
    # Đếm số lượng bản nhạc
    cursor.execute("SELECT COUNT(*) as count FROM bannhac")
    stats['bannhac'] = cursor.fetchone()['count']
    
    # Đếm số lượng bản thu âm
    cursor.execute("SELECT COUNT(*) as count FROM banthuam")
    stats['banthuam'] = cursor.fetchone()['count']
    
    cursor.close()
    conn.close()
    
    return jsonify(stats)

@app.route('/api/nhacsi/latest')
def get_latest_nhacsi():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM nhacsi ORDER BY created_at DESC LIMIT 5")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

# Thêm các API tương tự cho casi và bannhac

    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

# API lấy danh sách 5 ca sĩ mới nhất
@app.route('/api/casi/latest')
def get_latest_casi():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT idcasi, tencasi, ngaysinh, DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them 
        FROM casi 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)
# API lấy danh sách bản nhạc nổi bật (có nhiều bản thu âm nhất)
@app.route('/api/bannhac/noibat')
def get_featured_bannhac():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            bn.idbannhac, 
            bn.tenbannhac,
	    bn.idnhacsi, 
            ns.tennhacsi,
            COUNT(ba.idbanthuam) as soluong_banthuam,
            DATE_FORMAT(bn.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac bn
        LEFT JOIN banthuam ba ON bn.idbannhac = ba.idbannhac
        LEFT JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        GROUP BY bn.idbannhac
        ORDER BY soluong_banthuam DESC, bn.created_at DESC
        LIMIT 5
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)
# API lấy thông tin chi tiết nhạc sĩ
@app.route('/api/nhacsi/<int:id>')
def get_nhacsi_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy thông tin cơ bản
    cursor.execute("""
        SELECT 
            idnhacsi, 
            tennhacsi, 
            ngaysinh, 
            tieusu,
            avatar,
            DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them
        FROM nhacsi 
        WHERE idnhacsi = %s
    """, (id,))
    nhacsi = cursor.fetchone()
    
    if not nhacsi:
        return jsonify({"error": "Nhạc sĩ không tồn tại"}), 404
    
    # Lấy danh sách bài hát
    cursor.execute("""
        SELECT 
            idbannhac, 
            tenbannhac,
            DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac
        WHERE idnhacsi = %s
        ORDER BY created_at DESC
    """, (id,))
    baihat = cursor.fetchall()
    
    # Lấy số lượng bản thu âm cho mỗi bài hát
    for bh in baihat:
        cursor.execute("""
            SELECT COUNT(*) as soluong_banthuam
            FROM banthuam
            WHERE idbannhac = %s
        """, (bh['idbannhac'],))
        result = cursor.fetchone()
        bh['soluong_banthuam'] = result['soluong_banthuam']
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "nhacsi": nhacsi,
        "baihat": baihat
    })
@app.route('/nhacsi')
def nhacsi_list():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM nhacsi ORDER BY tennhacsi")
    nhacsi_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('nhacsi_list.html', nhacsi_list=nhacsi_list)
@app.route('/nhacsi/<int:id>')
def nhacsi_detail(id):
    return render_template('nhacsi_detail.html', idnhacsi=id)

# API lấy thông tin chi tiết ca sĩ
@app.route('/api/casi/<int:id>')
def get_casi_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy thông tin cơ bản
    cursor.execute("""
        SELECT 
            idcasi, 
            tencasi, 
            ngaysinh, 
            sunghiep,
            DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them
        FROM casi 
        WHERE idcasi = %s
    """, (id,))
    casi = cursor.fetchone()
    
    if not casi:
        return jsonify({"error": "Ca sĩ không tồn tại"}), 404
    
    # Lấy danh sách bản thu âm
    cursor.execute("""
        SELECT 
            ba.idbanthuam,
            ba.idbannhac,
            bn.tenbannhac,
            ns.idnhacsi,
            ns.tennhacsi,
            DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
        FROM banthuam ba
        JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
        JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        WHERE ba.idcasi = %s
        ORDER BY ba.created_at DESC
    """, (id,))
    banthuam = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "casi": casi,
        "banthuam": banthuam
    })

# Route hiển thị trang chi tiết
@app.route('/casi/<int:id>')
def casi_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # SỬA: Thêm trường anhdaidien và đổi tên cột cho đúng
    cursor.execute("""
        SELECT 
            idcasi, 
            tencasi, 
            Ngaysinh as ngaysinh,      -- SỬA: ngaysinh -> Ngaysinh
            Sunghiep as sunghiep,       -- SỬA: sunghiep -> Sunghiep
            anhdaidien,                  -- THÊM: trường ảnh đại diện
            DATE_FORMAT(created_at, '%%d/%%m/%%Y') as ngay_them
        FROM casi 
        WHERE idcasi = %s
    """, (id,))
    casi = cursor.fetchone()
    
    if not casi:
        return render_template('404.html'), 404
    
    # Lấy danh sách bản thu âm của ca sĩ
    cursor.execute("""
        SELECT 
            ba.idbanthuam,
            bn.idbannhac,
            bn.tenbannhac,
            ns.idnhacsi,
            ns.tennhacsi,
            DATE_FORMAT(ba.created_at, '%%d/%%m/%%Y') as ngay_them
        FROM banthuam ba
        JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
        JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        WHERE ba.idcasi = %s
        ORDER BY ba.created_at DESC
    """, (id,))
    banthuam = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('casi_detail.html', 
                         casi=casi,
                         banthuam=banthuam)
@app.route('/casi')
def casi_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    filter_by = request.args.get('filter', 'all')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Query với tên cột đúng
    query = """
        SELECT 
            c.idcasi,
            c.tencasi,
            c.Ngaysinh as ngaysinh,
            c.Sunghiep as sunghiep,
            c.anhdaidien,
            COUNT(b.idbanthuam) as soluong_banthuam,
            DATE_FORMAT(c.created_at, '%d/%m/%Y') as ngay_them
        FROM casi c
        LEFT JOIN banthuam b ON c.idcasi = b.idcasi
    """

    # Điều kiện lọc
    conditions = []
    if filter_by == 'has_records':
        conditions.append("b.idbanthuam IS NOT NULL")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY c.idcasi"

    # Sắp xếp
    if filter_by == 'newest':
        query += " ORDER BY c.created_at DESC"
    elif filter_by == 'oldest':
        query += " ORDER BY c.created_at ASC"
    else:
        query += " ORDER BY c.tencasi ASC"

    # Phân trang
    query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"

    print("DEBUG - Query:", query)  # Thêm dòng này để debug
    
    cursor.execute(query)
    casi_list = cursor.fetchall()

    print("DEBUG - Data:", casi_list)  # Thêm dòng này để debug

    # Đếm tổng số
    count_query = "SELECT COUNT(*) as total FROM casi c"
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    
    cursor.execute(count_query)
    total = cursor.fetchone()['total']
    total_pages = (total + per_page - 1) // per_page

    cursor.close()
    conn.close()

    return render_template('casi_list.html',
                         casi_list=casi_list,
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         filter_by=filter_by)

@app.route('/api/casi/<int:id>', methods=['DELETE'])
@csrf.exempt  # Thêm dòng này để tránh lỗi CSRF
def delete_casi(id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)  # SỬA: dùng dictionary=True
        
        # Kiểm tra ca sĩ có tồn tại không
        cursor.execute("SELECT * FROM casi WHERE idcasi = %s", (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return jsonify({
                "success": False,
                "message": "Ca sĩ không tồn tại"
            }), 404
        
        # Kiểm tra xem có bản thu âm không
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idcasi = %s", (id,))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        
        if count > 0:
            return jsonify({
                "success": False,
                "message": "Không thể xóa ca sĩ đã có bản thu âm"
            }), 400
        
        # Xóa file ảnh nếu có
        if casi['anhdaidien']:
            file_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], casi['anhdaidien'])
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Đã xóa file ảnh: {file_path}")
        
        # Xóa ca sĩ
        cursor.execute("DELETE FROM casi WHERE idcasi = %s", (id,))
        conn.commit()
        
        return jsonify({
            "success": True,
            "message": "Xóa ca sĩ thành công"
        })
        
    except mysql.connector.Error as err:
        print(f"Lỗi MySQL: {err}")
        if conn:
            conn.rollback()
        return jsonify({
            "success": False,
            "message": f"Lỗi database: {str(err)}"
        }), 500
        
    except Exception as e:
        print(f"Lỗi: {str(e)}")
        if conn:
            conn.rollback()
        return jsonify({
            "success": False,
            "message": f"Lỗi hệ thống: {str(e)}"
        }), 500
        
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# THÊM MỚI: Route hiển thị form chỉnh sửa
@app.route('/casi/edit/<int:idcasi>', methods=['GET'])
def edit_casi_form(idcasi):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT 
                idcasi, 
                tencasi, 
                Ngaysinh as ngaysinh, 
                Sunghiep as sunghiep,
                anhdaidien
            FROM casi 
            WHERE idcasi = %s
        """, (idcasi,))
        casi = cursor.fetchone()
        
        if not casi:
            flash('Không tìm thấy ca sĩ!', 'danger')
            return redirect(url_for('casi_list'))
        
        return render_template('casi_edit.html', casi=casi)
        
    except Exception as e:
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('casi_list'))
    finally:
        cursor.close()
        conn.close()

# THÊM MỚI: Route xử lý cập nhật
@app.route('/casi/edit/<int:idcasi>', methods=['POST'])
@csrf.exempt
def edit_casi(idcasi):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin ca sĩ hiện tại
        cursor.execute("SELECT * FROM casi WHERE idcasi = %s", (idcasi,))
        casi = cursor.fetchone()
        
        if not casi:
            flash('Ca sĩ không tồn tại', 'danger')
            return redirect(url_for('casi_list'))
        
        # Lấy dữ liệu từ form
        tencasi = request.form.get('tencasi', '').strip()
        ngaysinh = request.form.get('ngaysinh')
        sunghiep = request.form.get('sunghiep', '').strip()
        
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('edit_casi_form', idcasi=idcasi))
        
        # Xử lý ảnh
        anhdaidien_path = casi['anhdaidien']
        remove_avatar = request.form.get('remove_avatar') == 'true'
        
        if remove_avatar:
            if casi['anhdaidien']:
                old_file = os.path.join(app.config['SINGER_IMAGE_FOLDER'], casi['anhdaidien'])
                if os.path.exists(old_file):
                    os.remove(old_file)
            anhdaidien_path = None
            
        elif 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ', 'danger')
                    return redirect(url_for('edit_casi_form', idcasi=idcasi))
                
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"casi_{idcasi}_{int(datetime.now().timestamp())}.{ext}")
                save_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], filename)
                
                file.save(save_path)
                anhdaidien_path = filename
                
                if casi['anhdaidien'] and not remove_avatar:
                    old_file = os.path.join(app.config['SINGER_IMAGE_FOLDER'], casi['anhdaidien'])
                    if os.path.exists(old_file):
                        os.remove(old_file)
        
        # Cập nhật database
        cursor.execute("""
            UPDATE casi 
            SET tencasi = %s, 
                Ngaysinh = %s, 
                Sunghiep = %s, 
                anhdaidien = %s
            WHERE idcasi = %s
        """, (tencasi, ngaysinh, sunghiep, anhdaidien_path, idcasi))
        
        conn.commit()
        flash('Cập nhật ca sĩ thành công!', 'success')
        return redirect(url_for('casi_detail', id=idcasi))
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_casi_form', idcasi=idcasi))
    finally:
        cursor.close()
        conn.close()

@app.route('/casi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_casi():
    if request.method == 'GET':
        # Hiển thị form thêm mới
        return render_template('casi_add.html')
    
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Lấy dữ liệu từ form
            tencasi = request.form.get('tencasi', '').strip()
            ngaysinh = request.form.get('ngaysinh')
            sunghiep = request.form.get('sunghiep', '').strip()
            
            # Validate dữ liệu
            if not tencasi:
                flash('Tên ca sĩ không được để trống', 'danger')
                return redirect(url_for('add_casi'))
            
            # Xử lý ảnh đại diện
            anhdaidien_path = None
            if 'anhdaidien' in request.files:
                file = request.files['anhdaidien']
                if file and file.filename:
                    if not allowed_image(file.filename):
                        flash('Định dạng ảnh không hợp lệ. Chỉ chấp nhận: PNG, JPG, JPEG, GIF', 'danger')
                        return redirect(url_for('add_casi'))
                    
                    # Tạo tên file an toàn
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"casi_{int(datetime.now().timestamp())}.{ext}")
                    save_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], filename)
                    
                    # Lưu file
                    file.save(save_path)
                    anhdaidien_path = filename
            
            # Thêm vào database
            cursor.execute("""
                INSERT INTO casi (tencasi, Ngaysinh, Sunghiep, anhdaidien)
                VALUES (%s, %s, %s, %s)
            """, (tencasi, ngaysinh, sunghiep, anhdaidien_path))
            
            conn.commit()
            flash('Thêm ca sĩ thành công!', 'success')
            return redirect(url_for('casi_list'))
            
        except Exception as e:
            conn.rollback()
            flash(f'Lỗi khi thêm ca sĩ: {str(e)}', 'danger')
            return redirect(url_for('add_casi'))
            
        finally:
            cursor.close()
            conn.close()

@app.route('/bannhac/edit/<int:idbannhac>', methods=['GET', 'POST'])
@csrf.exempt
def edit_bannhac(idbannhac):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin bài hát hiện tại
        cursor.execute("""
            SELECT b.*, n.tennhacsi 
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            WHERE b.idbannhac = %s
        """, (idbannhac,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            flash('Không tìm thấy bài hát!', 'danger')
            return redirect(url_for('bannhac_list'))
        
        if request.method == 'POST':
            # Lấy dữ liệu từ form
            tenbannhac = request.form.get('tenbannhac', '').strip()
            theloai = request.form.get('theloai', '').strip()
            idnhacsi = request.form.get('idnhacsi')
            
            # Validate dữ liệu
            if not tenbannhac:
                flash('Tên bài hát không được để trống', 'danger')
                return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
            
            if not idnhacsi:
                flash('Vui lòng chọn nhạc sĩ', 'danger')
                return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
            
            # Cập nhật database
            cursor.execute("""
                UPDATE bannhac 
                SET tenbannhac = %s, 
                    theloai = %s, 
                    idnhacsi = %s
                WHERE idbannhac = %s
            """, (tenbannhac, theloai, idnhacsi, idbannhac))
            
            conn.commit()
            flash('Cập nhật bài hát thành công!', 'success')
            return redirect(url_for('bannhac_detail', id=idbannhac))
        
        # Lấy danh sách nhạc sĩ cho dropdown
        cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
        
        return render_template('bannhac_edit.html', 
                             bannhac=bannhac,
                             nhacsi_list=nhacsi_list)
        
    except Exception as e:
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('bannhac_list'))
    finally:
        cursor.close()
        conn.close()

@app.route('/api/bannhac/<int:id>', methods=['DELETE'])
@csrf.exempt
def delete_bannhac_api(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Kiểm tra bài hát có tồn tại không
        cursor.execute("SELECT * FROM bannhac WHERE idbannhac = %s", (id,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            return jsonify({
                "success": False,
                "message": "Bài hát không tồn tại"
            }), 404
        
        # Kiểm tra xem có bản thu âm không
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idbannhac = %s", (id,))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        
        if count > 0:
            return jsonify({
                "success": False,
                "message": "Không thể xóa bài hát đã có bản thu âm"
            }), 400
        
        # Xóa bài hát
        cursor.execute("DELETE FROM bannhac WHERE idbannhac = %s", (id,))
        conn.commit()
        
        return jsonify({
            "success": True,
            "message": "Xóa bài hát thành công"
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/bannhac/add', methods=['GET', 'POST'])
@csrf.exempt
def add_bannhac():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy danh sách nhạc sĩ cho dropdown
        cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
        
        if request.method == 'GET':
            return render_template('bannhac_add.html', nhacsi_list=nhacsi_list)
        
        elif request.method == 'POST':
            # Lấy dữ liệu từ form
            tenbannhac = request.form.get('tenbannhac', '').strip()
            theloai = request.form.get('theloai', '').strip()
            idnhacsi = request.form.get('idnhacsi')
            
            # Validate dữ liệu
            if not tenbannhac:
                flash('Tên bài hát không được để trống', 'danger')
                return redirect(url_for('add_bannhac'))
            
            if not idnhacsi:
                flash('Vui lòng chọn nhạc sĩ', 'danger')
                return redirect(url_for('add_bannhac'))
            
            # Thêm vào database
            cursor.execute("""
                INSERT INTO bannhac (tenbannhac, theloai, idnhacsi)
                VALUES (%s, %s, %s)
            """, (tenbannhac, theloai, idnhacsi))
            
            conn.commit()
            flash('Thêm bài hát thành công!', 'success')
            return redirect(url_for('bannhac_list'))
            
    except Exception as e:
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_bannhac'))
    finally:
        cursor.close()
        conn.close()
@app.route('/bannhac/<int:id>')
def bannhac_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy thông tin cơ bản bản nhạc
    cursor.execute("""
        SELECT 
            b.*,
	    b.idnhacsi,
            n.tennhacsi,
            DATE_FORMAT(b.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        WHERE b.idbannhac = %s
    """, (id,))
    bannhac = cursor.fetchone()
    
    if not bannhac:
        return render_template('404.html'), 404
    
    # Lấy danh sách bản thu âm
    cursor.execute("""
        SELECT 
            ba.idbanthuam,
            c.idcasi,
            c.tencasi,
            DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
        FROM banthuam ba
        JOIN casi c ON ba.idcasi = c.idcasi
        WHERE ba.idbannhac = %s
    """, (id,))
    banthuam = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('bannhac_detail.html',
                         bannhac=bannhac,
                         banthuam=banthuam)

@app.route('/api/bannhac/<int:id>', methods=['DELETE'])
def delete_bannhac(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Kiểm tra xem có bản thu âm nào không
        cursor.execute("SELECT COUNT(*) FROM banthuam WHERE idbannhac = %s", (id,))
        if cursor.fetchone()[0] > 0:
            return jsonify({
                "success": False,
                "message": "Không thể xóa bản nhạc đã có bản thu âm"
            })
        
        cursor.execute("DELETE FROM bannhac WHERE idbannhac = %s", (id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        })
    finally:
        cursor.close()
        conn.close()

@app.route('/api/banthuam/<int:id>', methods=['DELETE'])
def delete_banthuam(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM banthuam WHERE idbanthuam = %s", (id,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        })
    finally:
        cursor.close()
        conn.close()

@app.route('/api/bannhac/noibat')
def get_featured_songs():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            bn.idbannhac,
            bn.tenbannhac,
            bn.idnhacsi,
            ns.tennhacsi,
            COUNT(ba.idbanthuam) as soluong_banthuam,
            DATE_FORMAT(bn.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac bn
        LEFT JOIN banthuam ba ON bn.idbannhac = ba.idbannhac
        LEFT JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        GROUP BY bn.idbannhac
        ORDER BY soluong_banthuam DESC
        LIMIT 4
    """)
    data = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(data)

@app.route('/bannhac')
def bannhac_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    nhacsi_id = request.args.get('nhacsi', None)
    sort_by = request.args.get('sort', 'newest')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Base query
    query = """
        SELECT 
            b.idbannhac,
            b.tenbannhac,
            b.theloai,
            b.idnhacsi,
            n.tennhacsi,
            COUNT(ba.idbanthuam) as soluong_banthuam,
            DATE_FORMAT(b.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        LEFT JOIN banthuam ba ON b.idbannhac = ba.idbannhac
    """

    # Điều kiện lọc
    conditions = []
    if nhacsi_id:
        conditions.append(f"b.idnhacsi = {nhacsi_id}")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY b.idbannhac"

    # Sắp xếp
    if sort_by == 'newest':
        query += " ORDER BY b.created_at DESC"
    elif sort_by == 'oldest':
        query += " ORDER BY b.created_at ASC"
    elif sort_by == 'name_asc':
        query += " ORDER BY b.tenbannhac ASC"
    elif sort_by == 'name_desc':
        query += " ORDER BY b.tenbannhac DESC"
    elif sort_by == 'popular':
        query += " ORDER BY soluong_banthuam DESC"

    # Phân trang
    query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"

    cursor.execute(query)
    bannhac_list = cursor.fetchall()

    # Lấy danh sách nhạc sĩ cho filter
    cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
    nhacsi_list = cursor.fetchall()

    # Lấy tổng số bản ghi
    count_query = "SELECT COUNT(*) as total FROM bannhac"
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    
    cursor.execute(count_query)
    total = cursor.fetchone()['total']
    total_pages = (total + per_page - 1) // per_page

    cursor.close()
    conn.close()

    return render_template('bannhac_list.html',
                         bannhac_list=bannhac_list,
                         nhacsi_list=nhacsi_list,
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         nhacsi_id=nhacsi_id,
                         sort_by=sort_by)

@app.route('/api/banthuam/noibat')
def get_featured_recordings():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            ba.idbanthuam,
            ba.ngaythuam,
            b.idbannhac,
            b.tenbannhac,
            c.idcasi,
            c.tencasi,
            COUNT(f.id) as luot_thich,
            DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
        FROM banthuam ba
        JOIN bannhac b ON ba.idbannhac = b.idbannhac
        JOIN casi c ON ba.idcasi = c.idcasi
        LEFT JOIN favorites f ON ba.idbanthuam = f.idbanthuam
        GROUP BY ba.idbanthuam
        ORDER BY luot_thich DESC, ba.created_at DESC
        LIMIT 6
    """)
    data = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(data)



@app.route('/api/banthuam', methods=['GET'])
def get_recordings():
    song_id = request.args.get('bannhac')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if song_id:
        query = """
        SELECT bt.idbanthuam, bt.ngaythu, cs.tencasi
        FROM banthuam bt
        JOIN casi cs ON bt.idcasi = cs.idcasi
        WHERE bt.idbannhac = %s
        """
        cursor.execute(query, (song_id,))
    else:
        cursor.execute("SELECT * FROM banthuam LIMIT 50")
    
    recordings = cursor.fetchall()
    
    # Format dates
    for rec in recordings:
        if 'ngaythu' in rec and rec['ngaythu']:
            rec['ngaythu'] = rec['ngaythu'].isoformat()
    
    cursor.close()
    conn.close()
    
    return jsonify(recordings)

@app.route('/banthuam/delete/<int:recording_id>', methods=['POST'])
@csrf.exempt
def delete_recording(recording_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin file để xóa
        cursor.execute("SELECT file_path FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        recording = cursor.fetchone()
        
        # Xóa khỏi database
        cursor.execute("DELETE FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        conn.commit()
        
        # Xóa file vật lý nếu có
        if recording and recording['file_path']:
            file_path = os.path.join('static/recordings', recording['file_path'])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        flash('Xóa bản thu âm thành công!', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi khi xóa: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('banthuam_list'))

@app.route('/banthuam/edit/<int:idbanthuam>', methods=['GET', 'POST'])
@csrf.exempt
def edit_banthuam(idbanthuam):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin bản thu âm hiện tại
        cursor.execute("""
            SELECT bt.*, 
                   cs.tencasi,
                   bn.tenbannhac,
                   ns.tennhacsi
            FROM banthuam bt
            JOIN casi cs ON bt.idcasi = cs.idcasi
            JOIN bannhac bn ON bt.idbannhac = bn.idbannhac
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE bt.idbanthuam = %s
        """, (idbanthuam,))
        banthuam = cursor.fetchone()
        
        if not banthuam:
            flash('Không tìm thấy bản thu âm!', 'danger')
            return redirect(url_for('banthuam_list'))
        
        if request.method == 'GET':
            # Lấy danh sách bài hát và ca sĩ cho dropdown
            cursor.execute("""
                SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
                FROM bannhac b
                JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
                ORDER BY b.tenbannhac
            """)
            songs = cursor.fetchall()
            
            cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
            artists = cursor.fetchall()
            
            return render_template('banthuam_edit.html',
                                 banthuam=banthuam,
                                 songs=songs,
                                 artists=artists)
        
        elif request.method == 'POST':
            # Lấy dữ liệu từ form
            idbannhac = request.form.get('idbannhac')
            idcasi = request.form.get('idcasi')
            ngaythuam = request.form.get('ngaythuam')
            thoiluong = request.form.get('thoiluong')
            lyrics = request.form.get('lyrics', '').strip()
            ghichu = request.form.get('ghichu', '').strip()
            
            # Validate dữ liệu
            if not idbannhac or not idcasi:
                flash('Vui lòng chọn bài hát và ca sĩ', 'danger')
                return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
            
            # Xử lý file upload nếu có
            file_path = banthuam['file_path']  # Giữ file cũ
            if 'audio_file' in request.files:
                file = request.files['audio_file']
                if file and file.filename:
                    if not allowed_file(file.filename):
                        flash('Định dạng file không hợp lệ. Chỉ chấp nhận MP3, WAV, AAC', 'danger')
                        return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
                    
                    # Tạo tên file mới
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = secure_filename(f"recording_{idbanthuam}_{int(datetime.now().timestamp())}.{ext}")
                    save_path = os.path.join('static/recordings', filename)
                    
                    # Tạo thư mục nếu chưa tồn tại
                    os.makedirs('static/recordings', exist_ok=True)
                    
                    # Lưu file mới
                    file.save(save_path)
                    
                    # Xóa file cũ nếu có
                    if banthuam['file_path']:
                        old_file = os.path.join('static/recordings', banthuam['file_path'])
                        if os.path.exists(old_file):
                            os.remove(old_file)
                    
                    file_path = filename
            
            # Cập nhật database
            cursor.execute("""
                UPDATE banthuam 
                SET idbannhac = %s,
                    idcasi = %s,
                    ngaythuam = %s,
                    thoiluong = %s,
                    lyrics = %s,
                    ghichu = %s,
                    file_path = %s
                WHERE idbanthuam = %s
            """, (idbannhac, idcasi, ngaythuam, thoiluong, lyrics, ghichu, file_path, idbanthuam))
            
            conn.commit()
            flash('Cập nhật bản thu âm thành công!', 'success')
            return redirect(url_for('recording_detail', recording_id=idbanthuam))
            
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
    finally:
        cursor.close()
        conn.close()    

# Hàm lấy bản thu liên quan
def get_related_recordings(song_id, exclude_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT bt.idbanthuam, bt.ngaythuam, cs.tencasi
        FROM banthuam bt
        JOIN casi cs ON bt.idcasi = cs.idcasi
        WHERE bt.idbannhac = %s AND bt.idbanthuam != %s
        LIMIT 5
        """
        cursor.execute(query, (song_id, exclude_id))
        return cursor.fetchall()
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# Route xem chi tiết
@app.route('/banthuam/detail/<int:recording_id>')
def recording_detail(recording_id):
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        # SỬA: Thêm các trường cần thiết
        query = """
        SELECT 
            bt.idbanthuam,
            bt.idbannhac,
            bt.idcasi,
            bt.ngaythuam as ngaythu,
            bt.thoiluong,
            bt.file_path,
            bt.ghichu,
            bt.lyrics,
            cs.tencasi,
            cs.idcasi,
            bn.tenbannhac,
            bn.idnhacsi,
            ns.tennhacsi
        FROM banthuam bt
        JOIN casi cs ON bt.idcasi = cs.idcasi
        JOIN bannhac bn ON bt.idbannhac = bn.idbannhac
        JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        WHERE bt.idbanthuam = %s
        """
        cursor.execute(query, (recording_id,))
        recording = cursor.fetchone()
        
        if not recording:
            return "Bản thu không tồn tại", 404
        
        # Lấy bản thu liên quan (cùng bài hát)
        cursor.execute("""
            SELECT 
                bt.idbanthuam,
                cs.tencasi,
                bt.ngaythuam as ngaythu,
                bt.thoiluong
            FROM banthuam bt
            JOIN casi cs ON bt.idcasi = cs.idcasi
            WHERE bt.idbannhac = %s AND bt.idbanthuam != %s
            LIMIT 5
        """, (recording['idbannhac'], recording_id))
        related = cursor.fetchall()
        
        return render_template(
            'banthuam_detail.html',
            recording=recording,
            related_recordings=related
        )
    except Exception as e:
        print(f"Error: {e}")
        return "Internal server error", 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            

@app.route('/items')
def item_list():
    # Thiết lập phân trang
    page, per_page, offset = get_page_args(
        page_parameter='page',
        per_page_parameter='per_page'
    )
    per_page = 10  # Số item mỗi trang
    
    # Truy vấn database
    total = db.session.query(Item).count()
    items = db.session.query(Item).limit(per_page).offset(offset)
    
    # Tạo pagination object
    pagination = Pagination(
        page=page,
        per_page=per_page,
        total=total,
        css_framework='bootstrap5'
    )
    
    return render_template('item_list.html', items=items, pagination=pagination)

@app.route('/banthuam')
def banthuam_list():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    # Xử lý filter/tìm kiếm
    search_query = request.args.get('q', '').strip()
    artist_id = request.args.get('artist', '')
    sort_option = request.args.get('sort', 'newest')
    
    # Xây dựng query
    query = """
    SELECT bt.idbanthuam,bt.ngaythuam, bt.thoiluong,
           cs.idcasi, cs.tencasi,
           bn.idbannhac, bn.tenbannhac,
           ns.idnhacsi, ns.tennhacsi
    FROM banthuam bt
    JOIN casi cs ON bt.idcasi = cs.idcasi
    JOIN bannhac bn ON bt.idbannhac = bn.idbannhac
    JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
    WHERE 1=1
    """
    
    params = []
    
    if search_query:
        query += " AND (ns.tennhacsi LIKE %s OR bn.tenbannhac LIKE %s OR cs.tencasi LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    
    if artist_id:
        query += " AND bt.idcasi = %s"
        params.append(artist_id)
    
    # Sắp xếp
    if sort_option == 'newest':
        query += " ORDER BY bt.ngaythuam DESC"
    elif sort_option == 'oldest':
        query += " ORDER BY bt.ngaythuam ASC"
    elif sort_option == 'name_asc':
        query += " ORDER BY bn.tenbannhac ASC"
    elif sort_option == 'name_desc':
        query += " ORDER BY bn.tenbannhac DESC"
    
    # Thực thi query
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Đếm tổng số bản ghi
    count_query = "SELECT COUNT(*) as total FROM (" + query + ") as subquery"
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']
    
    # Lấy dữ liệu phân trang
    query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    cursor.execute(query, params)
    recordings = cursor.fetchall()
    
    # Lấy danh sách ca sĩ cho filter
    cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
    artists = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template(
        'banthuam_list.html',
        banthuam_list=recordings,
        artists=artists,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        search_query=search_query
    )

# Cấu hình upload
UPLOAD_FOLDER = 'static/recordings'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'aac'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/banthuam/add', methods=['GET', 'POST'])
@csrf.exempt
def add_banthuam():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if request.method == 'GET':
            # Lấy danh sách bài hát
            cursor.execute("""
                SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
                FROM bannhac b
                JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
                ORDER BY b.tenbannhac
            """)
            songs = cursor.fetchall()
            
            # Lấy danh sách ca sĩ
            cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
            artists = cursor.fetchall()
            
            return render_template('banthuam_add.html', 
                                 songs=songs, 
                                 artists=artists,
                                 now=datetime.now())
        
        elif request.method == 'POST':
            # In ra dữ liệu POST để debug
            print("Form data:", request.form)
            print("Files:", request.files)
            
            # Lấy dữ liệu từ form
            idbannhac = request.form.get('idbannhac')
            idcasi = request.form.get('idcasi')
            ngaythuam = request.form.get('ngaythuam')
            thoiluong = request.form.get('thoiluong')
            lyrics = request.form.get('lyrics', '').strip()
            ghichu = request.form.get('ghichu', '').strip()
            
            # Validate dữ liệu
            errors = []
            if not idbannhac:
                errors.append("Thiếu bài hát")
            if not idcasi:
                errors.append("Thiếu ca sĩ")
            
            if errors:
                flash(f'Lỗi: {", ".join(errors)}', 'danger')
                return redirect(url_for('add_banthuam'))
            
            # Xử lý file upload
            file_path = None
            if 'audio_file' in request.files:
                file = request.files['audio_file']
                if file and file.filename:
                    # Kiểm tra định dạng file
                    allowed_extensions = {'mp3', 'wav', 'aac', 'm4a'}
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                    
                    if ext not in allowed_extensions:
                        flash('Định dạng file không hợp lệ. Chỉ chấp nhận: MP3, WAV, AAC, M4A', 'danger')
                        return redirect(url_for('add_banthuam'))
                    
                    # Kiểm tra kích thước
                    file.seek(0, 2)
                    size = file.tell()
                    file.seek(0)
                    
                    if size > 20 * 1024 * 1024:  # 20MB
                        flash('File âm thanh không được vượt quá 20MB', 'danger')
                        return redirect(url_for('add_banthuam'))
                    
                    # Tạo tên file an toàn
                    filename = secure_filename(f"recording_{int(datetime.now().timestamp())}.{ext}")
                    save_path = os.path.join('static/recordings', filename)
                    
                    # Tạo thư mục nếu chưa tồn tại
                    os.makedirs('static/recordings', exist_ok=True)
                    
                    # Lưu file
                    file.save(save_path)
                    file_path = filename
                    print(f"File saved: {save_path}")
            
            if not file_path:
                flash('Vui lòng chọn file âm thanh', 'danger')
                return redirect(url_for('add_banthuam'))
            
            # Thêm vào database
            cursor.execute("""
                INSERT INTO banthuam 
                (idbannhac, idcasi, ngaythuam, thoiluong, lyrics, ghichu, file_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (idbannhac, idcasi, ngaythuam, thoiluong, lyrics, ghichu, file_path))
            
            conn.commit()
            flash('✅ Thêm bản thu âm thành công!', 'success')
            return redirect(url_for('banthuam_list'))
            
    except Exception as e:
        conn.rollback()
        print(f"Error: {str(e)}")
        flash(f'❌ Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_banthuam'))
    finally:
        cursor.close()
        conn.close()

@app.route('/banthuam/add', methods=['GET', 'POST'])
def add_recording():
    if request.method == 'GET':
        # Lấy danh sách bài hát và ca sĩ cho form
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Lấy danh sách bài hát kèm tên nhạc sĩ
            cursor.execute("""
                SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
                FROM bannhac b
                JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
                ORDER BY b.tenbannhac
            """)
            songs = cursor.fetchall()
            
            # Lấy danh sách ca sĩ
            cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
            artists = cursor.fetchall()
            
            return render_template('banthuam_add.html', 
                                songs=songs, 
                                artists=artists)
        
        finally:
            cursor.close()
            conn.close()
    
    elif request.method == 'POST':
        # Xử lý dữ liệu form
        try:
            # Validate dữ liệu
            idbannhac = request.form.get('idbannhac')
            idcasi = request.form.get('idcasi')
            
            if not idbannhac or not idcasi:
                flash('Vui lòng chọn bài hát và ca sĩ', 'danger')
                return redirect(url_for('add_recording'))
            
            # Xử lý file upload
            if 'audio_file' not in request.files:
                flash('Vui lòng chọn file âm thanh', 'danger')
                return redirect(url_for('add_recording'))
                
            file = request.files['audio_file']
            if file.filename == '':
                flash('Không có file được chọn', 'danger')
                return redirect(url_for('add_recording'))
                
            if not allowed_file(file.filename):
                flash('Định dạng file không hợp lệ. Chỉ chấp nhận MP3, WAV, AAC', 'danger')
                return redirect(url_for('add_recording'))
            
            # Tạo tên file an toàn
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Đảm bảo không trùng tên file
            counter = 1
            while os.path.exists(save_path):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{counter}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            
            # Lưu file
            file.save(save_path)
            
            # Chuẩn bị dữ liệu cho database
            recording_data = {
                'idbannhac': idbannhac,
                'idcasi': idcasi,
                'ngaythuam': request.form.get('ngaythuam') or datetime.now().strftime('%Y-%m-%d'),
                'thoiluong': request.form.get('thoiluong'),
                'file_path': filename,
                'ghichu': request.form.get('ghichu')
            }
            
            # Thêm vào database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query = """
            INSERT INTO banthuam 
            (idbannhac, idcasi, ngaythuam, thoiluong, file_path, ghichu)
            VALUES (%(idbannhac)s, %(idcasi)s, %(ngaythuam)s, %(thoiluong)s, %(file_path)s, %(ghichu)s)
            """
            cursor.execute(query, recording_data)
            conn.commit()
            
            flash('Thêm bản thu âm thành công!', 'success')
            return redirect(url_for('banthuam_list'))
            
        except Exception as e:
            # Xóa file đã upload nếu có lỗi
            if 'save_path' in locals() and os.path.exists(save_path):
                os.remove(save_path)
                
            flash(f'Lỗi khi thêm bản thu: {str(e)}', 'danger')
            return redirect(url_for('add_recording'))
        
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

# Cấu hình upload ảnh nhạc sĩ
ARTIST_IMAGE_FOLDER = 'static/images/artists'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['ARTIST_IMAGE_FOLDER'] = ARTIST_IMAGE_FOLDER
app.config['MAX_IMAGE_SIZE'] = 5 * 1024 * 1024  # 5MB
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
def allowed_image(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

@app.route('/nhacsi/add', methods=['GET', 'POST'])
@csrf.exempt 
def add_nhacsi():
    if request.method == 'GET':
        return render_template('nhacsi_add.html')
    
    elif request.method == 'POST':
        # Xử lý dữ liệu form
        try:
            # Validate dữ liệu bắt buộc
            tennhacsi = request.form.get('tennhacsi')
            if not tennhacsi:
                flash('Tên nhạc sĩ không được để trống', 'danger')
                return redirect(url_for('add_nhacsi'))

            # Xử lý file upload (không bắt buộc)
            avatar_path = None
            if 'avatar' in request.files:
                file = request.files['avatar']
                
                # Chỉ xử lý nếu có file được chọn
                if file.filename != '':
                    if not allowed_image(file.filename):
                        flash('Định dạng ảnh không hợp lệ. Chỉ chấp nhận PNG, JPG, JPEG, GIF', 'danger')
                        return redirect(url_for('add_nhacsi'))
                    
                    if file.content_length > app.config['MAX_IMAGE_SIZE']:
                        flash('Ảnh đại diện không được vượt quá 5MB', 'danger')
                        return redirect(url_for('add_nhacsi'))
                    
                    # Tạo tên file an toàn
                    filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                    save_path = os.path.join(app.config['ARTIST_IMAGE_FOLDER'], filename)
                    
                    # Đảm bảo thư mục tồn tại
                    os.makedirs(app.config['ARTIST_IMAGE_FOLDER'], exist_ok=True)
                    
                    # Lưu file
                    file.save(save_path)
                    avatar_path = f"images/artists/{filename}"

            # Chuẩn bị dữ liệu cho database
            nhacsi_data = {
                'tennhacsi': tennhacsi,
                'ngaysinh': request.form.get('ngaysinh'),
                'gioitinh': request.form.get('gioitinh'),
                'quequan': request.form.get('quequan'),
                'tieusu': request.form.get('tieusu'),
                'avatar': avatar_path
            }
            
            # Thêm vào database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            query = """
            INSERT INTO nhacsi 
            (tennhacsi, ngaysinh, gioitinh, quequan, tieusu, avatar)
            VALUES (%(tennhacsi)s, %(ngaysinh)s, %(gioitinh)s, %(quequan)s, %(tieusu)s, %(avatar)s)
            """
            cursor.execute(query, nhacsi_data)
            conn.commit()
            
            flash('Thêm nhạc sĩ thành công!', 'success')
            return redirect(url_for('nhacsi_list'))
            
        except Exception as e:
            # Xóa file đã upload nếu có lỗi
            if 'save_path' in locals() and os.path.exists(save_path):
                os.remove(save_path)
                
            flash(f'Lỗi khi thêm nhạc sĩ: {str(e)}', 'danger')
            return redirect(url_for('add_nhacsi'))
        
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

@app.route('/nhacsi/edit/<int:idnhacsi>', methods=['GET', 'POST'])
def edit_nhacsi(idnhacsi):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin nhạc sĩ hiện tại
        cursor.execute("SELECT * FROM nhacsi WHERE idnhacsi = %s", (idnhacsi,))
        nhacsi = cursor.fetchone()
        
        if not nhacsi:
            flash('Nhạc sĩ không tồn tại', 'danger')
            return redirect(url_for('nhacsi_list'))
        
        if request.method == 'POST':
            # Xử lý dữ liệu form
            tennhacsi = request.form.get('tennhacsi', '').strip()
            ngaysinh = request.form.get('ngaysinh')
            gioitinh = request.form.get('gioitinh')
            quequan = request.form.get('quequan', '').strip()
            tieusu = request.form.get('tieusu', '').strip()
            
            # Validate dữ liệu bắt buộc
            if not tennhacsi:
                flash('Tên nhạc sĩ không được để trống', 'danger')
                return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
            
            # Xử lý file upload (nếu có)
            avatar_path = nhacsi['avatar']  # Giữ nguyên avatar cũ nếu không upload mới
            
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file.filename != '':
                    if not allowed_image(file.filename):
                        flash('Định dạng ảnh không hợp lệ', 'danger')
                        return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
                    
                    # Tạo tên file mới
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
                    save_path = os.path.join(app.config['ARTIST_IMAGE_FOLDER'], filename)
                    
                    # Lưu file mới
                    file.save(save_path)
                    avatar_path = f"images/artists/{filename}"
                    
                    # Xóa file cũ (nếu có)
                    if nhacsi['avatar']:
                        old_file = os.path.join(app.config['ARTIST_IMAGE_FOLDER'], nhacsi['avatar'].split('/')[-1])
                        if os.path.exists(old_file):
                            os.remove(old_file)
            
            # Cập nhật database
            cursor.execute("""
                UPDATE nhacsi 
                SET tennhacsi = %s, 
                    ngaysinh = %s, 
                    gioitinh = %s, 
                    quequan = %s, 
                    tieusu = %s, 
                    avatar = %s
                WHERE idnhacsi = %s
            """, (tennhacsi, ngaysinh, gioitinh, quequan, tieusu, avatar_path, idnhacsi))
            
            conn.commit()
            flash('Cập nhật nhạc sĩ thành công!', 'success')
            return redirect(url_for('nhacsi_detail', id=idnhacsi))
        
        # Hiển thị form chỉnh sửa (GET request)
        return render_template('nhacsi_edit.html', nhacsi=nhacsi)
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi khi cập nhật nhạc sĩ: {str(e)}', 'danger')
        return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
        
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# --- KHỞI CHẠY ỨNG DỤNG --- #

if __name__ == '__main__':

    # TẮT CẢNH BÁO
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module='getpass')

    # Kiểm tra kết nối database
    print("🔍 Đang kiểm tra kết nối database...")

    test_conn = None
    try:
        test_conn = mysql.connector.connect(**DB_CONFIG)
        print("✅ Kết nối database thành công!")
    except Exception as e:
        print(f"❌ Lỗi kết nối database: {e}")
        print("👉 Kiểm tra lại config.py")
    finally:
        if test_conn and test_conn.is_connected():
            test_conn.close()

    # Lấy PORT từ Render
    port = int(os.environ.get("PORT", 5000))

    print(f"\n🚀 Ứng dụng đang chạy tại http://0.0.0.0:{port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
