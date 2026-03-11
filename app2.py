# -*- coding: utf-8 -*-
"""
MyMusic Flask Application
Quản lý nhạc sĩ, ca sĩ, bản nhạc và bản thu âm
"""

import os
import sys
import time
import json
import random
import argparse
import warnings
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, 
    url_for, flash, jsonify, make_response
)
from flask_paginate import Pagination, get_page_args
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Google AI
from google import genai
from google.genai import types

# Import AI Assistant
from ai_assistant import sql_assistant

# Load environment variables
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

class Config:
    """Application configuration"""
    # Base paths
    BASE_PATH = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.absolute()
    STATIC_DIR = BASE_PATH / 'static'
    TEMPLATE_DIR = BASE_PATH / 'templates'
    DATA_DIR = BASE_PATH / 'data'
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')
    
    # Upload folders
    SINGER_IMAGE_FOLDER = 'static/images/singers'
    ARTIST_IMAGE_FOLDER = 'static/images/artists'
    RECORDING_FOLDER = 'static/recordings'
    
    # File upload settings
    ALLOWED_AUDIO = {'mp3', 'wav', 'aac', 'm4a'}
    ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB
    
    # Database
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '3306')),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'mymusic'),
        'charset': 'utf8mb4',
        'use_unicode': True,
        'autocommit': False
    }
    
    # Google AI
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    # Rate limiting
    RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '5'))
    RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))


# ============================================
# INITIALIZATION
# ============================================

# Create necessary directories
for directory in [
    Config.STATIC_DIR, Config.TEMPLATE_DIR, Config.DATA_DIR,
    Path(Config.SINGER_IMAGE_FOLDER), Path(Config.ARTIST_IMAGE_FOLDER),
    Path(Config.RECORDING_FOLDER)
]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Warning: Cannot create directory {directory}: {e}")

# Initialize Flask app
app = Flask(
    __name__,
    template_folder=str(Config.TEMPLATE_DIR),
    static_folder=str(Config.STATIC_DIR)
)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_AUDIO_SIZE
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize Google AI client
if Config.GEMINI_API_KEY:
    ai_client = genai.Client(api_key=Config.GEMINI_API_KEY)
else:
    ai_client = None
    print("Warning: GEMINI_API_KEY not set. AI features will be disabled.")

# Rate limiting storage
request_history = {}


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_db_connection():
    """Get database connection"""
    try:
        conn = mysql.connector.connect(**Config.DB_CONFIG)
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None


def db_cursor(dictionary=False):
    """Context manager for database cursor"""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=dictionary) if dictionary else conn.cursor()
        yield cursor
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def allowed_file(filename, allowed_set):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def allowed_audio(filename):
    """Check if audio file is allowed"""
    return allowed_file(filename, Config.ALLOWED_AUDIO)


def allowed_image(filename):
    """Check if image file is allowed"""
    return allowed_file(filename, Config.ALLOWED_IMAGES)


def rate_limit(max_requests=None, time_window=None):
    """Rate limiting decorator"""
    if max_requests is None:
        max_requests = Config.RATE_LIMIT_REQUESTS
    if time_window is None:
        time_window = Config.RATE_LIMIT_WINDOW
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            
            if client_ip not in request_history:
                request_history[client_ip] = []
            
            # Clean old requests
            request_history[client_ip] = [
                req_time for req_time in request_history[client_ip]
                if current_time - req_time < time_window
            ]
            
            if len(request_history[client_ip]) >= max_requests:
                return jsonify({
                    "status": "error",
                    "message": f"Too many requests. Please wait {time_window} seconds.",
                    "feedback": f"Bạn đã gửi quá {max_requests} request trong {time_window} giây. Vui lòng đợi!"
                }), 429
            
            request_history[client_ip].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def call_gemini_with_retry(prompt, retries=3, delay=5):
    """Call Gemini API with retry logic"""
    if not ai_client:
        return "AI service not configured. Please set GEMINI_API_KEY."
    
    for i in range(retries):
        try:
            response = ai_client.models.generate_content(
                model='gemini-1.5-flash-8b',
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=500,
                    temperature=0.7
                )
            )
            return response.text
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                print(f"⚠️ Rate limit exceeded. Retrying in {delay} seconds... (Attempt {i+1}/{retries})")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"❌ AI Error: {str(e)}")
                return f"Error: {str(e)}"
    
    return "AI service temporarily unavailable. Please try again later."


def format_date(date_obj, format_str='%d/%m/%Y'):
    """Format date object"""
    if date_obj:
        return date_obj.strftime(format_str)
    return None


# ============================================
# ROUTES - MAIN PAGES
# ============================================

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/nhacsi')
def nhacsi_list():
    """List all composers"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('nhacsi_list.html', nhacsi_list=[])
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        nhacsi_list = []
    finally:
        cursor.close()
        conn.close()
    
    return render_template('nhacsi_list.html', nhacsi_list=nhacsi_list)


@app.route('/nhacsi/<int:id>')
def nhacsi_detail(id):
    """Composer detail page"""
    return render_template('nhacsi_detail.html', idnhacsi=id)


@app.route('/casi')
def casi_list():
    """List all singers with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    filter_by = request.args.get('filter', 'all')
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('casi_list.html', casi_list=[])
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Base query
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
        
        conditions = []
        if filter_by == 'has_records':
            conditions.append("b.idbanthuam IS NOT NULL")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY c.idcasi"
        
        # Sorting
        if filter_by == 'newest':
            query += " ORDER BY c.created_at DESC"
        elif filter_by == 'oldest':
            query += " ORDER BY c.created_at ASC"
        else:
            query += " ORDER BY c.tencasi ASC"
        
        # Pagination
        query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
        
        cursor.execute(query)
        casi_list = cursor.fetchall()
        
        # Count total
        count_query = "SELECT COUNT(*) as total FROM casi c"
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
        
        cursor.execute(count_query)
        total = cursor.fetchone()['total']
        total_pages = (total + per_page - 1) // per_page
        
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        casi_list = []
        total_pages = 0
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'casi_list.html',
        casi_list=casi_list,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        filter_by=filter_by
    )


@app.route('/casi/<int:id>')
def casi_detail(id):
    """Singer detail page"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get singer info
        cursor.execute("""
            SELECT 
                idcasi, 
                tencasi, 
                Ngaysinh as ngaysinh,
                Sunghiep as sunghiep,
                anhdaidien,
                DATE_FORMAT(created_at, '%%d/%%m/%%Y') as ngay_them
            FROM casi 
            WHERE idcasi = %s
        """, (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return render_template('404.html'), 404
        
        # Get recordings
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
        
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('404.html'), 404
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'casi_detail.html',
        casi=casi,
        banthuam=banthuam
    )


@app.route('/bannhac')
def bannhac_list():
    """List all songs with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    nhacsi_id = request.args.get('nhacsi', None)
    sort_by = request.args.get('sort', 'newest')
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('bannhac_list.html', bannhac_list=[])
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get composers for filter
        cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
        
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
        
        conditions = []
        if nhacsi_id:
            conditions.append(f"b.idnhacsi = {nhacsi_id}")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY b.idbannhac"
        
        # Sorting
        sort_options = {
            'newest': " ORDER BY b.created_at DESC",
            'oldest': " ORDER BY b.created_at ASC",
            'name_asc': " ORDER BY b.tenbannhac ASC",
            'name_desc': " ORDER BY b.tenbannhac DESC",
            'popular': " ORDER BY soluong_banthuam DESC"
        }
        query += sort_options.get(sort_by, sort_options['newest'])
        
        # Pagination
        query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
        
        cursor.execute(query)
        bannhac_list = cursor.fetchall()
        
        # Count total
        count_query = "SELECT COUNT(*) as total FROM bannhac"
        if conditions:
            count_query += " WHERE " + " AND ".join(conditions)
        
        cursor.execute(count_query)
        total = cursor.fetchone()['total']
        total_pages = (total + per_page - 1) // per_page
        
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        bannhac_list = []
        nhacsi_list = []
        total_pages = 0
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'bannhac_list.html',
        bannhac_list=bannhac_list,
        nhacsi_list=nhacsi_list,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        nhacsi_id=nhacsi_id,
        sort_by=sort_by
    )


@app.route('/bannhac/<int:id>')
def bannhac_detail(id):
    """Song detail page"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get song info
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
        
        # Get recordings
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
        
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('404.html'), 404
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'bannhac_detail.html',
        bannhac=bannhac,
        banthuam=banthuam
    )


@app.route('/banthuam')
def banthuam_list():
    """List all recordings with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    search_query = request.args.get('q', '').strip()
    artist_id = request.args.get('artist', '')
    sort_option = request.args.get('sort', 'newest')
    
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('banthuam_list.html', banthuam_list=[])
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get artists for filter
        cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
        artists = cursor.fetchall()
        
        # Build query
        query = """
            SELECT 
                bt.idbanthuam,
                bt.ngaythuam,
                bt.thoiluong,
                cs.idcasi,
                cs.tencasi,
                bn.idbannhac,
                bn.tenbannhac,
                ns.idnhacsi,
                ns.tennhacsi
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
        
        # Sorting
        sort_options = {
            'newest': " ORDER BY bt.ngaythuam DESC",
            'oldest': " ORDER BY bt.ngaythuam ASC",
            'name_asc': " ORDER BY bn.tenbannhac ASC",
            'name_desc': " ORDER BY bn.tenbannhac DESC"
        }
        query += sort_options.get(sort_option, sort_options['newest'])
        
        # Count total
        count_query = "SELECT COUNT(*) as total FROM (" + query + ") as subquery"
        cursor.execute(count_query, params)
        total = cursor.fetchone()['total']
        
        # Pagination
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, params)
        recordings = cursor.fetchall()
        
        total_pages = (total + per_page - 1) // per_page
        
    except Error as e:
        flash(f'Error: {str(e)}', 'danger')
        recordings = []
        artists = []
        total_pages = 0
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'banthuam_list.html',
        banthuam_list=recordings,
        artists=artists,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        search_query=search_query
    )


@app.route('/banthuam/detail/<int:recording_id>')
def recording_detail(recording_id):
    """Recording detail page"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get recording info
        cursor.execute("""
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
        """, (recording_id,))
        recording = cursor.fetchone()
        
        if not recording:
            return "Recording not found", 404
        
        # Get related recordings
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
        
    except Error as e:
        print(f"Error: {e}")
        return "Internal server error", 500
    finally:
        cursor.close()
        conn.close()
    
    return render_template(
        'banthuam_detail.html',
        recording=recording,
        related_recordings=related
    )


@app.route('/thuc-hanh-ai', methods=['GET', 'POST'])
@csrf.exempt
def thuc_hanh_ai():
    """AI Practice page"""
    if request.method == 'GET':
        return render_template('thuc_hanh_ai.html')
    
    # Handle POST request
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "No data received",
                "score": 0,
                "feedback": "Vui lòng nhập câu lệnh SQL!"
            })
        
        action = data.get('action', 'evaluate')
        sql_query = data.get('sql_query', '').strip()
        exercise_id = data.get('exercise_id', '1')
        
        if not sql_query:
            return jsonify({
                "status": "error",
                "message": "Empty SQL query",
                "score": 0,
                "feedback": "Vui lòng nhập câu lệnh SQL!"
            })
        
        if action == 'evaluate':
            result = sql_assistant.evaluate_sql(sql_query, exercise_id)
            
            if exercise_id in sql_assistant.sample_exercises:
                result['sql_chuan'] = sql_assistant.sample_exercises[exercise_id]['solution']
            
            return jsonify({
                "status": result.get('status', 'unknown'),
                "message": result.get('message', 'SQL evaluated'),
                "feedback": result.get('feedback', ''),
                "score": result.get('score', 0),
                "sql_chuan": result.get('sql_chuan', '')
            })
            
        elif action == 'execute':
            result = sql_assistant.execute_sql_safe(sql_query)
            return jsonify(result)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error: {str(e)}",
            "feedback": "Có lỗi xảy ra, vui lòng thử lại!",
            "score": 0,
            "sql_chuan": ""
        })


# ============================================
# API ROUTES
# ============================================

@app.route('/api/stats')
def get_stats():
    """Get database statistics"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        stats = {}
        
        tables = ['nhacsi', 'casi', 'bannhac', 'banthuam']
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            stats[table] = cursor.fetchone()['count']
        
        return jsonify(stats)
        
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/nhacsi')
def get_nhacsi():
    """Get all composers"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM nhacsi")
        data = cursor.fetchall()
        return jsonify(data)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/nhacsi/latest')
def get_latest_nhacsi():
    """Get latest composers"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM nhacsi ORDER BY created_at DESC LIMIT 5")
        data = cursor.fetchall()
        return jsonify(data)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/nhacsi/<int:id>')
def get_nhacsi_detail(id):
    """Get composer details"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Basic info
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
            return jsonify({"error": "Composer not found"}), 404
        
        # Songs
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
        
        # Count recordings per song
        for bh in baihat:
            cursor.execute("""
                SELECT COUNT(*) as soluong_banthuam
                FROM banthuam
                WHERE idbannhac = %s
            """, (bh['idbannhac'],))
            result = cursor.fetchone()
            bh['soluong_banthuam'] = result['soluong_banthuam'] if result else 0
        
        return jsonify({
            "nhacsi": nhacsi,
            "baihat": baihat
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/casi/latest')
def get_latest_casi():
    """Get latest singers"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT idcasi, tencasi, ngaysinh, DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them 
            FROM casi 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        data = cursor.fetchall()
        return jsonify(data)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/casi/<int:id>')
def get_casi_detail_api(id):
    """Get singer details"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Basic info
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
            return jsonify({"error": "Singer not found"}), 404
        
        # Recordings
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
        
        return jsonify({
            "casi": casi,
            "banthuam": banthuam
        })
        
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/casi/<int:id>', methods=['DELETE'])
@csrf.exempt
def delete_casi(id):
    """Delete singer"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if exists
        cursor.execute("SELECT * FROM casi WHERE idcasi = %s", (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return jsonify({
                "success": False,
                "message": "Singer not found"
            }), 404
        
        # Check for recordings
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idcasi = %s", (id,))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        
        if count > 0:
            return jsonify({
                "success": False,
                "message": "Cannot delete singer with recordings"
            }), 400
        
        # Delete image file
        if casi.get('anhdaidien'):
            file_path = os.path.join(Config.SINGER_IMAGE_FOLDER, casi['anhdaidien'])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete singer
        cursor.execute("DELETE FROM casi WHERE idcasi = %s", (id,))
        conn.commit()
        
        return jsonify({
            "success": True,
            "message": "Singer deleted successfully"
        })
        
    except Error as err:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": f"Database error: {str(err)}"
        }), 500
    except Exception as e:
        conn.rollback()
        return jsonify({
            "success": False,
            "message": f"System error: {str(e)}"
        }), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/bannhac/noibat')
def get_featured_songs():
    """Get featured songs"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
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
        return jsonify(data)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/bannhac/<int:id>', methods=['DELETE'])
@csrf.exempt
def delete_bannhac_api(id):
    """Delete song"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if exists
        cursor.execute("SELECT * FROM bannhac WHERE idbannhac = %s", (id,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            return jsonify({
                "success": False,
                "message": "Song not found"
            }), 404
        
        # Check for recordings
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idbannhac = %s", (id,))
        result = cursor.fetchone()
        count = result['count'] if result else 0
        
        if count > 0:
            return jsonify({
                "success": False,
                "message": "Cannot delete song with recordings"
            }), 400
        
        # Delete song
        cursor.execute("DELETE FROM bannhac WHERE idbannhac = %s", (id,))
        conn.commit()
        
        return jsonify({
            "success": True,
            "message": "Song deleted successfully"
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


@app.route('/api/banthuam/noibat')
def get_featured_recordings():
    """Get featured recordings"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
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
        return jsonify(data)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/banthuam', methods=['GET'])
def get_recordings():
    """Get recordings"""
    song_id = request.args.get('bannhac')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        if song_id:
            query = """
                SELECT bt.idbanthuam, bt.ngaythuam, cs.tencasi
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
            if 'ngaythuam' in rec and rec['ngaythuam']:
                if hasattr(rec['ngaythuam'], 'isoformat'):
                    rec['ngaythuam'] = rec['ngaythuam'].isoformat()
        
        return jsonify(recordings)
    except Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/banthuam/<int:id>', methods=['DELETE'])
def delete_banthuam(id):
    """Delete recording"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection error"}), 500
    
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
        }), 500
    finally:
        cursor.close()
        conn.close()


# ============================================
# AI ROUTES
# ============================================

@app.route('/api/execute-sql', methods=['POST'])
@csrf.exempt
def execute_sql_api():
    """Execute SQL safely (SELECT only)"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({
                "success": False,
                "error": "Please enter SQL query"
            })
        
        result = sql_assistant.execute_sql_safe(sql)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/generate-exercise', methods=['POST'])
@csrf.exempt
def generate_exercise_api():
    """Generate new SQL exercise using AI"""
    try:
        data = request.get_json() if request.is_json else request.form.to_dict() or {}
        topic = data.get('topic', '')
        
        print(f"📝 Generating new exercise with topic: {topic}")
        
        exercise = sql_assistant.generate_exercise(topic)
        
        if not isinstance(exercise, dict):
            exercise = {}
        
        # Fallback exercises
        if not exercise or 'title' not in exercise:
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
        
        print(f"✅ Generated exercise: {exercise.get('title', 'No title')}")
        return jsonify(exercise)
        
    except Exception as e:
        print(f"❌ Error generating exercise: {str(e)}")
        import traceback
        traceback.print_exc()
        
        fallback_exercise = {
            'title': 'Liệt kê tất cả bản nhạc',
            'description': 'Viết câu lệnh SQL để lấy danh sách tất cả bản nhạc trong database',
            'solution': 'SELECT * FROM bannhac',
            'hint': 'Sử dụng SELECT * FROM [tên_bảng]'
        }
        return jsonify(fallback_exercise)


@app.route('/api/exercises', methods=['GET'])
def get_exercises_api():
    """Get list of SQL exercises"""
    exercises = []
    for id, ex in sql_assistant.sample_exercises.items():
        exercises.append({
            'id': id,
            'title': ex['title'],
            'description': ex['description']
        })
    return jsonify(exercises)


@app.route('/api/exercises/<exercise_id>', methods=['GET'])
def get_exercise_detail_api(exercise_id):
    """Get exercise details"""
    if exercise_id in sql_assistant.sample_exercises:
        ex = sql_assistant.sample_exercises[exercise_id]
        return jsonify({
            'id': exercise_id,
            'title': ex['title'],
            'description': ex['description'],
            'hint': ex['hint'],
            'solution': ex['solution']
        })
    return jsonify({"error": "Exercise not found"}), 404


@app.route('/api/ai-chat', methods=['POST'])
@csrf.exempt
def ai_chat_api():
    """Chat with AI assistant about SQL"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data received"
            })
        
        message = data.get('message', '').strip()
        context = data.get('context', '')
        
        if not message:
            return jsonify({
                "success": False,
                "error": "Please enter a question"
            })
        
        response = sql_assistant.chat_response(message, context)
        if not response:
            return jsonify({
                "success": False,
                "error": "AI could not generate response"
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


@app.route('/api/validate-sql', methods=['POST'])
@csrf.exempt
def validate_sql_api():
    """Validate SQL syntax"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({
                "valid": False,
                "error": "Empty SQL query"
            })
        
        conn = mysql.connector.connect(**Config.DB_CONFIG)
        cursor = conn.cursor()
        
        try:
            cursor.execute(f"EXPLAIN {sql}")
            return jsonify({
                "valid": True,
                "message": "SQL syntax is valid"
            })
        except mysql.connector.Error as err:
            return jsonify({
                "valid": False,
                "error": f"Syntax error: {err.msg}"
            })
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({
            "valid": False,
            "error": str(e)
        })


@app.route('/api/learning-stats', methods=['GET'])
def learning_stats_api():
    """Get learning statistics"""
    return jsonify({
        "total_exercises": len(sql_assistant.sample_exercises),
        "completed": 0,
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


# ============================================
# FORM ROUTES - ADD/EDIT
# ============================================

@app.route('/casi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_casi():
    """Add new singer"""
    if request.method == 'GET':
        return render_template('casi_add.html')
    
    # POST request
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('add_casi'))
    
    cursor = conn.cursor()
    try:
        # Get form data
        tencasi = request.form.get('tencasi', '').strip()
        ngaysinh = request.form.get('ngaysinh')
        sunghiep = request.form.get('sunghiep', '').strip()
        
        # Validate
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('add_casi'))
        
        # Handle image upload
        anhdaidien_path = None
        if 'anhdaidien' in request.files:
            file = request.files['anhdaidien']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ. Chỉ chấp nhận: PNG, JPG, JPEG, GIF', 'danger')
                    return redirect(url_for('add_casi'))
                
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"casi_{int(datetime.now().timestamp())}.{ext}")
                save_path = os.path.join(Config.SINGER_IMAGE_FOLDER, filename)
                
                file.save(save_path)
                anhdaidien_path = filename
        
        # Insert into database
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


@app.route('/casi/edit/<int:idcasi>', methods=['GET'])
def edit_casi_form(idcasi):
    """Edit singer form"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('casi_list'))
    
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


@app.route('/casi/edit/<int:idcasi>', methods=['POST'])
@csrf.exempt
def edit_casi(idcasi):
    """Update singer"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('edit_casi_form', idcasi=idcasi))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get current singer
        cursor.execute("SELECT * FROM casi WHERE idcasi = %s", (idcasi,))
        casi = cursor.fetchone()
        
        if not casi:
            flash('Ca sĩ không tồn tại', 'danger')
            return redirect(url_for('casi_list'))
        
        # Get form data
        tencasi = request.form.get('tencasi', '').strip()
        ngaysinh = request.form.get('ngaysinh')
        sunghiep = request.form.get('sunghiep', '').strip()
        
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('edit_casi_form', idcasi=idcasi))
        
        # Handle image
        anhdaidien_path = casi['anhdaidien']
        remove_avatar = request.form.get('remove_avatar') == 'true'
        
        if remove_avatar:
            if casi['anhdaidien']:
                old_file = os.path.join(Config.SINGER_IMAGE_FOLDER, casi['anhdaidien'])
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
                save_path = os.path.join(Config.SINGER_IMAGE_FOLDER, filename)
                
                file.save(save_path)
                anhdaidien_path = filename
                
                if casi['anhdaidien'] and not remove_avatar:
                    old_file = os.path.join(Config.SINGER_IMAGE_FOLDER, casi['anhdaidien'])
                    if os.path.exists(old_file):
                        os.remove(old_file)
        
        # Update database
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


@app.route('/bannhac/add', methods=['GET', 'POST'])
@csrf.exempt
def add_bannhac():
    """Add new song"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('bannhac_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get composers for dropdown
        cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
        
        if request.method == 'GET':
            return render_template('bannhac_add.html', nhacsi_list=nhacsi_list)
        
        # POST request
        tenbannhac = request.form.get('tenbannhac', '').strip()
        theloai = request.form.get('theloai', '').strip()
        idnhacsi = request.form.get('idnhacsi')
        
        # Validate
        if not tenbannhac:
            flash('Tên bài hát không được để trống', 'danger')
            return redirect(url_for('add_bannhac'))
        
        if not idnhacsi:
            flash('Vui lòng chọn nhạc sĩ', 'danger')
            return redirect(url_for('add_bannhac'))
        
        # Insert
        cursor.execute("""
            INSERT INTO bannhac (tenbannhac, theloai, idnhacsi)
            VALUES (%s, %s, %s)
        """, (tenbannhac, theloai, idnhacsi))
        
        conn.commit()
        flash('Thêm bài hát thành công!', 'success')
        return redirect(url_for('bannhac_list'))
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_bannhac'))
    finally:
        cursor.close()
        conn.close()


@app.route('/bannhac/edit/<int:idbannhac>', methods=['GET', 'POST'])
@csrf.exempt
def edit_bannhac(idbannhac):
    """Edit song"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('bannhac_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get current song
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
        
        if request.method == 'GET':
            # Get composers for dropdown
            cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
            nhacsi_list = cursor.fetchall()
            
            return render_template('bannhac_edit.html', 
                                 bannhac=bannhac,
                                 nhacsi_list=nhacsi_list)
        
        # POST request
        tenbannhac = request.form.get('tenbannhac', '').strip()
        theloai = request.form.get('theloai', '').strip()
        idnhacsi = request.form.get('idnhacsi')
        
        # Validate
        if not tenbannhac:
            flash('Tên bài hát không được để trống', 'danger')
            return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
        
        if not idnhacsi:
            flash('Vui lòng chọn nhạc sĩ', 'danger')
            return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
        
        # Update
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
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('bannhac_list'))
    finally:
        cursor.close()
        conn.close()


@app.route('/banthuam/add', methods=['GET', 'POST'])
@csrf.exempt
def add_banthuam():
    """Add new recording"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('banthuam_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'GET':
            # Get songs for dropdown
            cursor.execute("""
                SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
                FROM bannhac b
                JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
                ORDER BY b.tenbannhac
            """)
            songs = cursor.fetchall()
            
            # Get artists for dropdown
            cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
            artists = cursor.fetchall()
            
            return render_template('banthuam_add.html', 
                                 songs=songs, 
                                 artists=artists,
                                 now=datetime.now())
        
        # POST request
        print("Form data:", request.form)
        print("Files:", request.files)
        
        # Get form data
        idbannhac = request.form.get('idbannhac')
        idcasi = request.form.get('idcasi')
        ngaythuam = request.form.get('ngaythuam')
        thoiluong = request.form.get('thoiluong')
        lyrics = request.form.get('lyrics', '').strip()
        ghichu = request.form.get('ghichu', '').strip()
        
        # Validate
        errors = []
        if not idbannhac:
            errors.append("Thiếu bài hát")
        if not idcasi:
            errors.append("Thiếu ca sĩ")
        
        if errors:
            flash(f'Lỗi: {", ".join(errors)}', 'danger')
            return redirect(url_for('add_banthuam'))
        
        # Handle file upload
        file_path = None
        if 'audio_file' in request.files:
            file = request.files['audio_file']
            if file and file.filename:
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if ext not in Config.ALLOWED_AUDIO:
                    flash('Định dạng file không hợp lệ. Chỉ chấp nhận: MP3, WAV, AAC, M4A', 'danger')
                    return redirect(url_for('add_banthuam'))
                
                # Check size
                file.seek(0, 2)
                size = file.tell()
                file.seek(0)
                
                if size > Config.MAX_AUDIO_SIZE:
                    flash('File âm thanh không được vượt quá 20MB', 'danger')
                    return redirect(url_for('add_banthuam'))
                
                # Save file
                filename = secure_filename(f"recording_{int(datetime.now().timestamp())}.{ext}")
                save_path = os.path.join(Config.RECORDING_FOLDER, filename)
                
                os.makedirs(Config.RECORDING_FOLDER, exist_ok=True)
                file.save(save_path)
                file_path = filename
                print(f"File saved: {save_path}")
        
        if not file_path:
            flash('Vui lòng chọn file âm thanh', 'danger')
            return redirect(url_for('add_banthuam'))
        
        # Insert into database
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


@app.route('/banthuam/edit/<int:idbanthuam>', methods=['GET', 'POST'])
@csrf.exempt
def edit_banthuam(idbanthuam):
    """Edit recording"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('banthuam_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get current recording
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
            # Get songs for dropdown
            cursor.execute("""
                SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
                FROM bannhac b
                JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
                ORDER BY b.tenbannhac
            """)
            songs = cursor.fetchall()
            
            # Get artists for dropdown
            cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
            artists = cursor.fetchall()
            
            return render_template('banthuam_edit.html',
                                 banthuam=banthuam,
                                 songs=songs,
                                 artists=artists)
        
        # POST request
        idbannhac = request.form.get('idbannhac')
        idcasi = request.form.get('idcasi')
        ngaythuam = request.form.get('ngaythuam')
        thoiluong = request.form.get('thoiluong')
        lyrics = request.form.get('lyrics', '').strip()
        ghichu = request.form.get('ghichu', '').strip()
        
        # Validate
        if not idbannhac or not idcasi:
            flash('Vui lòng chọn bài hát và ca sĩ', 'danger')
            return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
        
        # Handle file upload
        file_path = banthuam['file_path']
        if 'audio_file' in request.files:
            file = request.files['audio_file']
            if file and file.filename:
                if not allowed_audio(file.filename):
                    flash('Định dạng file không hợp lệ. Chỉ chấp nhận MP3, WAV, AAC', 'danger')
                    return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
                
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"recording_{idbanthuam}_{int(datetime.now().timestamp())}.{ext}")
                save_path = os.path.join(Config.RECORDING_FOLDER, filename)
                
                os.makedirs(Config.RECORDING_FOLDER, exist_ok=True)
                file.save(save_path)
                
                # Delete old file
                if banthuam['file_path']:
                    old_file = os.path.join(Config.RECORDING_FOLDER, banthuam['file_path'])
                    if os.path.exists(old_file):
                        os.remove(old_file)
                
                file_path = filename
        
        # Update database
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


@app.route('/banthuam/delete/<int:recording_id>', methods=['POST'])
@csrf.exempt
def delete_recording(recording_id):
    """Delete recording"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('banthuam_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get file info
        cursor.execute("SELECT file_path FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        recording = cursor.fetchone()
        
        # Delete from database
        cursor.execute("DELETE FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        conn.commit()
        
        # Delete file
        if recording and recording['file_path']:
            file_path = os.path.join(Config.RECORDING_FOLDER, recording['file_path'])
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


@app.route('/nhacsi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_nhacsi():
    """Add new composer"""
    if request.method == 'GET':
        return render_template('nhacsi_add.html')
    
    # POST request
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('add_nhacsi'))
    
    cursor = conn.cursor()
    try:
        # Validate
        tennhacsi = request.form.get('tennhacsi')
        if not tennhacsi:
            flash('Tên nhạc sĩ không được để trống', 'danger')
            return redirect(url_for('add_nhacsi'))

        # Handle image upload
        avatar_path = None
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ. Chỉ chấp nhận PNG, JPG, JPEG, GIF', 'danger')
                    return redirect(url_for('add_nhacsi'))
                
                # Check size
                file.seek(0, 2)
                size = file.tell()
                file.seek(0)
                
                if size > Config.MAX_IMAGE_SIZE:
                    flash('Ảnh đại diện không được vượt quá 5MB', 'danger')
                    return redirect(url_for('add_nhacsi'))
                
                # Save file
                filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
                save_path = os.path.join(Config.ARTIST_IMAGE_FOLDER, filename)
                
                os.makedirs(Config.ARTIST_IMAGE_FOLDER, exist_ok=True)
                file.save(save_path)
                avatar_path = f"images/artists/{filename}"

        # Prepare data
        nhacsi_data = {
            'tennhacsi': tennhacsi,
            'ngaysinh': request.form.get('ngaysinh'),
            'gioitinh': request.form.get('gioitinh'),
            'quequan': request.form.get('quequan'),
            'tieusu': request.form.get('tieusu'),
            'avatar': avatar_path
        }
        
        # Insert
        cursor.execute("""
            INSERT INTO nhacsi 
            (tennhacsi, ngaysinh, gioitinh, quequan, tieusu, avatar)
            VALUES (%(tennhacsi)s, %(ngaysinh)s, %(gioitinh)s, %(quequan)s, %(tieusu)s, %(avatar)s)
        """, nhacsi_data)
        
        conn.commit()
        flash('Thêm nhạc sĩ thành công!', 'success')
        return redirect(url_for('nhacsi_list'))
        
    except Exception as e:
        conn.rollback()
        # Delete uploaded file if error
        if 'save_path' in locals() and os.path.exists(save_path):
            os.remove(save_path)
            
        flash(f'Lỗi khi thêm nhạc sĩ: {str(e)}', 'danger')
        return redirect(url_for('add_nhacsi'))
        
    finally:
        cursor.close()
        conn.close()


@app.route('/nhacsi/edit/<int:idnhacsi>', methods=['GET', 'POST'])
def edit_nhacsi(idnhacsi):
    """Edit composer"""
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('nhacsi_list'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get current composer
        cursor.execute("SELECT * FROM nhacsi WHERE idnhacsi = %s", (idnhacsi,))
        nhacsi = cursor.fetchone()
        
        if not nhacsi:
            flash('Nhạc sĩ không tồn tại', 'danger')
            return redirect(url_for('nhacsi_list'))
        
        if request.method == 'POST':
            # Get form data
            tennhacsi = request.form.get('tennhacsi', '').strip()
            ngaysinh = request.form.get('ngaysinh')
            gioitinh = request.form.get('gioitinh')
            quequan = request.form.get('quequan', '').strip()
            tieusu = request.form.get('tieusu', '').strip()
            
            # Validate
            if not tennhacsi:
                flash('Tên nhạc sĩ không được để trống', 'danger')
                return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
            
            # Handle image
            avatar_path = nhacsi['avatar']
            
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and file.filename:
                    if not allowed_image(file.filename):
                        flash('Định dạng ảnh không hợp lệ', 'danger')
                        return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
                    
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
                    save_path = os.path.join(Config.ARTIST_IMAGE_FOLDER, filename)
                    
                    file.save(save_path)
                    avatar_path = f"images/artists/{filename}"
                    
                    # Delete old file
                    if nhacsi['avatar']:
                        old_file = os.path.join(Config.ARTIST_IMAGE_FOLDER, nhacsi['avatar'].split('/')[-1])
                        if os.path.exists(old_file):
                            os.remove(old_file)
            
            # Update
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
        
        # GET request - show form
        return render_template('nhacsi_edit.html', nhacsi=nhacsi)
        
    except Exception as e:
        conn.rollback()
        flash(f'Lỗi khi cập nhật nhạc sĩ: {str(e)}', 'danger')
        return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
        
    finally:
        cursor.close()
        conn.close()


# ============================================
# DATABASE FUNCTIONS
# ============================================

def get_db_config():
    """Get database config from user input"""
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
    """Restore database from SQL file"""
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
            # Check MySQL version
            cursor.execute("SELECT VERSION()")
            print(f"⚙️ MySQL Version: {cursor.fetchone()[0]}")
            
            print(f"\n📥 Đang import dữ liệu từ {backup_file}...")
            
            # Disable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            
            sql_command = ""
            
            with open(backup_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip comments
                    if line.startswith("--") or line == "":
                        continue
                    
                    sql_command += line + " "
                    
                    # Execute when encountering ;
                    if line.endswith(";"):
                        try:
                            cursor.execute(sql_command)
                        except Exception as e:
                            print("⚠️ SQL Error:", e)
                        
                        sql_command = ""
            
            # Enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        
        print("\n✅ DATABASE RESTORE SUCCESSFUL!")
        print("\n🔑 Connection info:")
        print(f"- Host: {config['host']}")
        print(f"- Port: {config['port']}")
        print(f"- Database: {config['database']}")
        print(f"- Username: {config['user']}")
        
    except pymysql.Error as e:
        print(f"\n❌ MySQL Error ({e.args[0]}): {e.args[1]}")
    except FileNotFoundError:
        print(f"\n❌ FILE NOT FOUND: {backup_file}")
    except Exception as e:
        print(f"\n❌ UNKNOWN ERROR: {str(e)}")
    finally:
        if conn:
            conn.close()


# ============================================
# MAIN ENTRY POINT
# ============================================

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
