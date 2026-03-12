# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_paginate import Pagination, get_page_args
import mysql.connector
from mysql.connector import Error
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
import sys
from pathlib import Path
import pymysql
from pymysql.constants import CLIENT
from dotenv import load_dotenv
import json
import time
from functools import wraps
import random
import uuid
import logging
import argparse

# Load environment variables
load_dotenv()

# =============================
# CẤU HÌNH LOGGING
# =============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================
# CẤU HÌNH DATABASE TỪ ENV (RAILWAY)
# =============================
DB_CONFIG = {
    'host': os.getenv('MYSQLHOST', 'localhost'),
    'port': int(os.getenv('MYSQLPORT', 3306)),
    'user': os.getenv('MYSQLUSER', 'root'),
    'password': os.getenv('MYSQLPASSWORD', ''),
    'database': os.getenv('MYSQLDATABASE', 'railway'),
    'charset': 'utf8mb4',
    'use_unicode': True,
    'connect_timeout': 10,
    'autocommit': True
}

# =============================
# CẤU HÌNH ĐƯỜNG DẪN
# =============================
if getattr(sys, 'frozen', False):
    base_path = Path(sys.executable).parent
else:
    base_path = Path(__file__).parent.absolute()

static_dir = base_path / 'static'
template_dir = base_path / 'templates'
data_dir = base_path / 'data'

# Tạo thư mục cần thiết
for dir_path in [static_dir, template_dir, data_dir, 
                 static_dir / 'images', 
                 static_dir / 'images/singers', 
                 static_dir / 'images/artists',
                 static_dir / 'recordings']:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Cannot create {dir_path}: {e}")

# =============================
# KHỞI TẠO FLASK APP
# =============================
app = Flask(__name__, 
            template_folder=str(template_dir),
            static_folder=str(static_dir))

# Cấu hình Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 giờ

# Cấu hình upload
app.config['SINGER_IMAGE_FOLDER'] = str(static_dir / 'images/singers')
app.config['ARTIST_IMAGE_FOLDER'] = str(static_dir / 'images/artists')
app.config['UPLOAD_FOLDER'] = str(static_dir / 'recordings')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB
app.config['MAX_IMAGE_SIZE'] = 5 * 1024 * 1024  # 5MB

# CORS và CSRF
CORS(app)  # Allow cross-origin requests
csrf = CSRFProtect(app)

# =============================
# HÀM TIỆN ÍCH
# =============================

def get_db_connection():
    """Kết nối database với xử lý lỗi"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def execute_query(query, params=None, fetch_one=False):
    """Thực thi query an toàn"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return None, "Không thể kết nối database"
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if query.strip().upper().startswith('SELECT'):
            if fetch_one:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()
        else:
            conn.commit()
            result = {"affected_rows": cursor.rowcount}
        
        return result, None
    except Error as e:
        logger.error(f"Query error: {e}")
        return None, str(e)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def allowed_file(filename):
    """Kiểm tra file âm thanh hợp lệ"""
    ALLOWED_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image(filename):
    """Kiểm tra file ảnh hợp lệ"""
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# Rate limiting
request_history = {}

def rate_limit(max_requests=60, time_window=60):
    """Giới hạn số request"""
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
                    "status": "error",
                    "message": f"Quá {max_requests} request trong {time_window} giây"
                }), 429
            
            request_history[client_ip].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================
# GOOGLE AI (SỬA LẠI CHO TƯƠNG THÍCH)
# =============================
try:
    # Thử import theo cách mới (google.genai)
    from google import genai
    from google.genai import types
    gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    logger.info("✅ Đã khởi tạo Gemini AI (phiên bản mới)")
    GEMINI_AVAILABLE = True
except (ImportError, AttributeError) as e:
    try:
        # Nếu lỗi, thử import theo cách cũ (google.generativeai)
        import google.generativeai as genai
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        # Sử dụng model cũ hơn nếu cần
        gemini_client = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("✅ Đã khởi tạo Gemini AI (phiên bản cũ)")
        GEMINI_AVAILABLE = True
    except ImportError:
        logger.warning("⚠️ Không thể khởi tạo Google AI. Tiếp tục chạy ở chế độ offline.")
        gemini_client = None
        GEMINI_AVAILABLE = False


# =============================
# AI ASSISTANT (fallback)
# =============================
try:
    from ai_assistant import sql_assistant
except ImportError:
    class SQLAssistant:
        def __init__(self):
            self.sample_exercises = {
                '1': {
                    'title': 'Tìm tất cả bản nhạc',
                    'description': 'Viết câu lệnh SQL để lấy tất cả bản nhạc',
                    'solution': 'SELECT * FROM bannhac',
                    'hint': 'Sử dụng SELECT * FROM'
                },
                '2': {
                    'title': 'Đếm số ca sĩ',
                    'description': 'Đếm tổng số ca sĩ',
                    'solution': 'SELECT COUNT(*) FROM casi',
                    'hint': 'Dùng COUNT(*)'
                }
            }
        
        def evaluate_sql(self, sql_query, exercise_id):
            return {
                'status': 'success',
                'score': 10,
                'feedback': 'Câu lệnh SQL hợp lệ',
                'message': 'Đã đánh giá'
            }
        
        def execute_sql_safe(self, sql_query):
            result, error = execute_query(sql_query)
            if error:
                return {'success': False, 'error': error}
            return {'success': True, 'data': result}
        
        def chat_response(self, message, context):
            return f"AI: {message}"
        
        def generate_exercise(self, topic):
            return {
                'title': f'Bài tập về {topic}',
                'description': f'Thực hành SQL chủ đề {topic}',
                'solution': 'SELECT * FROM bannhac',
                'hint': 'Thử nghiệm với SELECT'
            }
    
    sql_assistant = SQLAssistant()
    logger.info("Using fallback SQL Assistant")

# =============================
# ROUTES - TRANG CHÍNH
# =============================

@app.route('/')
def index():
    """Trang chủ"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check cho Railway"""
    # Kiểm tra database
    conn = get_db_connection()
    db_status = 'connected' if conn and conn.is_connected() else 'disconnected'
    if conn:
        conn.close()
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'database': db_status,
        'environment': os.getenv('FLASK_ENV', 'production')
    })

# =============================
# ROUTES - NHẠC SĨ
# =============================

@app.route('/nhacsi')
def nhacsi_list():
    """Danh sách nhạc sĩ"""
    result, error = execute_query("SELECT * FROM nhacsi ORDER BY tennhacsi")
    if error:
        flash(f'Lỗi: {error}', 'danger')
        return render_template('nhacsi_list.html', nhacsi_list=[])
    
    return render_template('nhacsi_list.html', nhacsi_list=result or [])

@app.route('/nhacsi/<int:id>')
def nhacsi_detail(id):
    """Chi tiết nhạc sĩ"""
    return render_template('nhacsi_detail.html', idnhacsi=id)

@app.route('/nhacsi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_nhacsi():
    """Thêm nhạc sĩ mới"""
    if request.method == 'GET':
        return render_template('nhacsi_add.html')
    
    # POST request
    try:
        tennhacsi = request.form.get('tennhacsi', '').strip()
        if not tennhacsi:
            flash('Tên nhạc sĩ không được để trống', 'danger')
            return redirect(url_for('add_nhacsi'))
        
        # Xử lý avatar
        avatar_path = None
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ', 'danger')
                    return redirect(url_for('add_nhacsi'))
                
                filename = secure_filename(f"ns_{int(time.time())}_{file.filename}")
                save_path = os.path.join(app.config['ARTIST_IMAGE_FOLDER'], filename)
                file.save(save_path)
                avatar_path = f"images/artists/{filename}"
        
        query = """
            INSERT INTO nhacsi (tennhacsi, ngaysinh, gioitinh, quequan, tieusu, avatar)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            tennhacsi,
            request.form.get('ngaysinh'),
            request.form.get('gioitinh'),
            request.form.get('quequan'),
            request.form.get('tieusu'),
            avatar_path
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm nhạc sĩ thành công!', 'success')
        
        return redirect(url_for('nhacsi_list'))
        
    except Exception as e:
        logger.error(f"Error adding nhacsi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_nhacsi'))

# =============================
# ROUTES - CA SĨ
# =============================

@app.route('/casi')
def casi_list():
    """Danh sách ca sĩ"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = """
        SELECT c.*, COUNT(b.idbanthuam) as soluong_banthuam
        FROM casi c
        LEFT JOIN banthuam b ON c.idcasi = b.idcasi
        GROUP BY c.idcasi
        ORDER BY c.tencasi
        LIMIT %s OFFSET %s
    """
    offset = (page - 1) * per_page
    result, error = execute_query(query, (per_page, offset))
    
    # Đếm tổng số
    count_result, _ = execute_query("SELECT COUNT(*) as total FROM casi", fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('casi_list.html',
                         casi_list=result or [],
                         page=page,
                         total_pages=total_pages)

@app.route('/casi/<int:id>')
def casi_detail(id):
    """Chi tiết ca sĩ"""
    conn = get_db_connection()
    if not conn:
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin ca sĩ
        cursor.execute("""
            SELECT idcasi, tencasi, Ngaysinh as ngaysinh, 
                   Sunghiep as sunghiep, anhdaidien
            FROM casi WHERE idcasi = %s
        """, (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return render_template('404.html'), 404
        
        # Lấy bản thu âm
        cursor.execute("""
            SELECT ba.*, bn.tenbannhac, ns.tennhacsi
            FROM banthuam ba
            JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE ba.idcasi = %s
            ORDER BY ba.created_at DESC
        """, (id,))
        banthuam = cursor.fetchall()
        
        return render_template('casi_detail.html',
                             casi=casi,
                             banthuam=banthuam)
    except Exception as e:
        logger.error(f"Error in casi_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/casi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_casi():
    """Thêm ca sĩ mới"""
    if request.method == 'GET':
        return render_template('casi_add.html')
    
    try:
        tencasi = request.form.get('tencasi', '').strip()
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('add_casi'))
        
        # Xử lý ảnh
        anhdaidien = None
        if 'anhdaidien' in request.files:
            file = request.files['anhdaidien']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ', 'danger')
                    return redirect(url_for('add_casi'))
                
                filename = secure_filename(f"cs_{int(time.time())}_{file.filename}")
                save_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], filename)
                file.save(save_path)
                anhdaidien = filename
        
        query = """
            INSERT INTO casi (tencasi, Ngaysinh, Sunghiep, anhdaidien)
            VALUES (%s, %s, %s, %s)
        """
        params = (
            tencasi,
            request.form.get('ngaysinh'),
            request.form.get('sunghiep'),
            anhdaidien
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm ca sĩ thành công!', 'success')
        
        return redirect(url_for('casi_list'))
        
    except Exception as e:
        logger.error(f"Error adding casi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_casi'))

# =============================
# ROUTES - BẢN NHẠC
# =============================

@app.route('/bannhac')
def bannhac_list():
    """Danh sách bản nhạc"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = """
        SELECT b.*, n.tennhacsi, COUNT(ba.idbanthuam) as soluong_banthuam
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        LEFT JOIN banthuam ba ON b.idbannhac = ba.idbannhac
        GROUP BY b.idbannhac
        ORDER BY b.created_at DESC
        LIMIT %s OFFSET %s
    """
    offset = (page - 1) * per_page
    result, error = execute_query(query, (per_page, offset))
    
    # Lấy danh sách nhạc sĩ cho filter
    composers, _ = execute_query("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
    
    # Đếm tổng số
    count_result, _ = execute_query("SELECT COUNT(*) as total FROM bannhac", fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('bannhac_list.html',
                         bannhac_list=result or [],
                         nhacsi_list=composers or [],
                         page=page,
                         total_pages=total_pages)

@app.route('/bannhac/<int:id>')
def bannhac_detail(id):
    """Chi tiết bản nhạc"""
    conn = get_db_connection()
    if not conn:
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin bản nhạc
        cursor.execute("""
            SELECT b.*, n.tennhacsi
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            WHERE b.idbannhac = %s
        """, (id,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            return render_template('404.html'), 404
        
        # Lấy bản thu âm
        cursor.execute("""
            SELECT ba.*, c.tencasi
            FROM banthuam ba
            JOIN casi c ON ba.idcasi = c.idcasi
            WHERE ba.idbannhac = %s
            ORDER BY ba.created_at DESC
        """, (id,))
        banthuam = cursor.fetchall()
        
        return render_template('bannhac_detail.html',
                             bannhac=bannhac,
                             banthuam=banthuam)
    except Exception as e:
        logger.error(f"Error in bannhac_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

# =============================
# ROUTES - BẢN THU ÂM
# =============================

@app.route('/banthuam')
def banthuam_list():
    """Danh sách bản thu âm"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = """
        SELECT ba.*, bn.tenbannhac, c.tencasi, ns.tennhacsi
        FROM banthuam ba
        JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
        JOIN casi c ON ba.idcasi = c.idcasi
        JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        ORDER BY ba.created_at DESC
        LIMIT %s OFFSET %s
    """
    offset = (page - 1) * per_page
    result, error = execute_query(query, (per_page, offset))
    
    # Lấy danh sách ca sĩ cho filter
    artists, _ = execute_query("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
    
    # Đếm tổng số
    count_result, _ = execute_query("SELECT COUNT(*) as total FROM banthuam", fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('banthuam_list.html',
                         banthuam_list=result or [],
                         artists=artists or [],
                         page=page,
                         total_pages=total_pages)

@app.route('/banthuam/detail/<int:recording_id>')
def recording_detail(recording_id):
    """Chi tiết bản thu âm"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT ba.*, bn.tenbannhac, c.tencasi, ns.tennhacsi
            FROM banthuam ba
            JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
            JOIN casi c ON ba.idcasi = c.idcasi
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE ba.idbanthuam = %s
        """, (recording_id,))
        recording = cursor.fetchone()
        
        if not recording:
            return render_template('404.html'), 404
        
        # Lấy bản thu liên quan
        cursor.execute("""
            SELECT ba.idbanthuam, c.tencasi, ba.ngaythuam
            FROM banthuam ba
            JOIN casi c ON ba.idcasi = c.idcasi
            WHERE ba.idbannhac = %s AND ba.idbanthuam != %s
            LIMIT 5
        """, (recording['idbannhac'], recording_id))
        related = cursor.fetchall()
        
        return render_template('banthuam_detail.html',
                             recording=recording,
                             related_recordings=related)
    except Exception as e:
        logger.error(f"Error in recording_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

# =============================
# API ROUTES
# =============================

@app.route('/api/stats')
def get_stats():
    """Thống kê database"""
    queries = {
        'nhacsi': "SELECT COUNT(*) as count FROM nhacsi",
        'casi': "SELECT COUNT(*) as count FROM casi",
        'bannhac': "SELECT COUNT(*) as count FROM bannhac",
        'banthuam': "SELECT COUNT(*) as count FROM banthuam"
    }
    
    stats = {}
    for key, query in queries.items():
        result, error = execute_query(query, fetch_one=True)
        if error:
            return jsonify({'error': error}), 500
        stats[key] = result['count'] if result else 0
    
    return jsonify(stats)

@app.route('/api/nhacsi')
def api_nhacsi():
    """API lấy danh sách nhạc sĩ"""
    result, error = execute_query("SELECT * FROM nhacsi ORDER BY tennhacsi")
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/casi')
def api_casi():
    """API lấy danh sách ca sĩ"""
    result, error = execute_query("SELECT * FROM casi ORDER BY tencasi")
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/bannhac')
def api_bannhac():
    """API lấy danh sách bản nhạc"""
    result, error = execute_query("""
        SELECT b.*, n.tennhacsi
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        ORDER BY b.created_at DESC
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/bannhac/noibat')
def api_bannhac_noibat():
    """API lấy bản nhạc nổi bật"""
    result, error = execute_query("""
        SELECT b.idbannhac, b.tenbannhac, n.tennhacsi,
               COUNT(ba.idbanthuam) as soluong_banthuam
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        LEFT JOIN banthuam ba ON b.idbannhac = ba.idbannhac
        GROUP BY b.idbannhac
        ORDER BY soluong_banthuam DESC
        LIMIT 5
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/casi/latest')
def api_casi_latest():
    """API lấy ca sĩ mới nhất"""
    result, error = execute_query("""
        SELECT idcasi, tencasi, Ngaysinh as ngaysinh,
               DATE_FORMAT(created_at, '%%d/%%m/%%Y') as ngay_them
        FROM casi
        ORDER BY created_at DESC
        LIMIT 5
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

# =============================
# ROUTES - AI FEATURES
# =============================

@app.route('/thuc-hanh-ai', methods=['GET', 'POST'])
@csrf.exempt
def thuc_hanh_ai():
    """Trang thực hành AI"""
    if request.method == 'GET':
        return render_template('thuc_hanh_ai.html')
    
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        if not data:
            return jsonify({'status': 'error', 'message': 'Không có dữ liệu'}), 400
        
        action = data.get('action', 'evaluate')
        sql_query = data.get('sql_query', '').strip()
        
        if not sql_query:
            return jsonify({'status': 'error', 'message': 'Vui lòng nhập SQL'}), 400
        
        if action == 'evaluate':
            result = sql_assistant.evaluate_sql(sql_query, data.get('exercise_id', '1'))
            return jsonify(result)
        elif action == 'execute':
            result = sql_assistant.execute_sql_safe(sql_query)
            return jsonify(result)
        
        return jsonify({'status': 'error', 'message': 'Action không hợp lệ'}), 400
        
    except Exception as e:
        logger.error(f"Error in thuc_hanh_ai: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ai-chat', methods=['POST'])
@csrf.exempt
def ai_chat_api():
    """API chat với AI"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Không có dữ liệu'}), 400
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'error': 'Vui lòng nhập câu hỏi'}), 400
        
        response = sql_assistant.chat_response(message, data.get('context', ''))
        return jsonify({'success': True, 'response': response})
        
    except Exception as e:
        logger.error(f"Error in ai_chat_api: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/generate-exercise', methods=['POST'])
@csrf.exempt
def generate_exercise_api():
    """API tạo bài tập mới"""
    try:
        data = request.get_json() or {}
        topic = data.get('topic', '')
        exercise = sql_assistant.generate_exercise(topic)
        return jsonify(exercise)
    except Exception as e:
        logger.error(f"Error generating exercise: {e}")
        return jsonify({'error': str(e)}), 500

# =============================
# ERROR HANDLERS
# =============================

@app.errorhandler(404)
def not_found(error):
    """Xử lý lỗi 404"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Xử lý lỗi 500"""
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# =============================
# CHẠY ỨNG DỤNG
# =============================

if __name__ == '__main__':
    # Kiểm tra kết nối database
    logger.info("Kiểm tra kết nối database...")
    conn = get_db_connection()
    if conn and conn.is_connected():
        logger.info("✅ Kết nối database thành công!")
        conn.close()
    else:
        logger.warning("⚠️ Không thể kết nối database. Kiểm lại cấu hình!")
    
    # Lấy port từ environment (Railway tự động set PORT)
    port = int(os.environ.get('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Server starting on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)