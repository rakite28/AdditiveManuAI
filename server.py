import os
import re
import json
import time
import shutil
import sys
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
import easyocr
# from openpyxl import load_workbook, Workbook
# from openpyxl.styles import Font
# from openpyxl.utils import get_column_letter
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required, JWTManager, get_jwt

# --- Custom Modules ---
import database as db
from exceptions import InvalidAPIUsage
from helpers import (
    calculate_printer_hourly_rate,
    calculate_cogs_values,
    parse_time_string,
    extract_data_from_ocr,
    generate_quotation_pdf
)

# --- Server Configuration ---
UPLOAD_FOLDER = "uploads"
PROFILE_PICS_FOLDER = "data/profile_pics"
GENERATED_FILES_FOLDER = "generated_files"
SHARED_FOLDER = "shared"
SERVER_CONFIG_FILE = os.path.join(SHARED_FOLDER, "server_config.json")


# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "a-super-secret-key-that-you-should-change")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
jwt = JWTManager(app)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- Role-based Access Decorator ---
def admin_required():
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            current_user = get_jwt_identity()
            if current_user.get('role') != 'admin':
                raise InvalidAPIUsage("Admins only!", status_code=403)
            return fn(*args, **kwargs)
        return decorator
    return wrapper

# --- Error Handlers ---
@app.errorhandler(InvalidAPIUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@app.errorhandler(HTTPException)
def handle_http_exception(e):
    response = e.get_response()
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "error": e.description,
    })
    response.content_type = "application/json"
    return response

@app.errorhandler(Exception)
def handle_generic_exception(e):
    logging.error(f"Unhandled Exception: {e}", exc_info=True)
    response = jsonify({"error": "An unexpected internal server error occurred."})
    response.status_code = 500
    return response

# --- One-time Model Loading ---
logging.info("Loading EasyOCR model into memory...")
try:
    ocr_reader = easyocr.Reader(['en'])
    logging.info("EasyOCR model loaded successfully.")
except Exception as e:
    logging.critical(f"FATAL: Could not load EasyOCR model. Error: {e}")
    ocr_reader = None

# --- Initial File & Folder Setup ---
def initialize_server_folders():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FILES_FOLDER, exist_ok=True)
    os.makedirs(SHARED_FOLDER, exist_ok=True)
    os.makedirs("data", exist_ok=True)


# --- API Endpoints ---

# --- Authentication Endpoints ---
@app.route('/auth/register_company', methods=['POST'])
def register_company():
    data = request.get_json()
    if not data or not all(k in data for k in ['company_name', 'admin_username', 'admin_email', 'admin_password']):
        raise InvalidAPIUsage("Missing required fields for company registration.", status_code=400)

    result = db.create_company_and_admin(
        data['company_name'],
        data['admin_username'],
        data['admin_email'],
        data['admin_password']
    )

    if "error" in result:
        raise InvalidAPIUsage(result["error"], status_code=409)

    logging.info(f"New company registered: {data['company_name']}")
    return jsonify({"message": f"Company '{data['company_name']}' and admin user '{data['admin_username']}' registered successfully."}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('identifier') or not data.get('password'):
        raise InvalidAPIUsage("Missing username/email or password.", status_code=400)

    user = db.find_user_by_identifier(data['identifier'])

    if user and db.verify_password(data['password'], user['password_hash']):
        identity = { "id": user['id'], "username": user['username'], "role": user['role'], "company_id": user['company_id'] }
        access_token = create_access_token(identity=identity)
        refresh_token = create_refresh_token(identity=identity)
        logging.info(f"User '{user['username']}' logged in successfully.")
        return jsonify(token=access_token, refresh_token=refresh_token)

    raise InvalidAPIUsage("Invalid credentials.", status_code=401)

@app.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return jsonify(token=access_token)

@app.route('/auth/logout', methods=['POST'])
def logout():
    return jsonify({"message": "Logout successful."})

@app.route('/auth/create_user', methods=['POST'])
@admin_required()
def create_user():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']

    data = request.get_json()
    if not data or not all(k in data for k in ['username', 'email', 'password', 'role']):
        raise InvalidAPIUsage("Missing required fields for user creation.", status_code=400)

    result = db.create_user(data['username'], data['email'], data['password'], data['role'], company_id)
    if "error" in result:
        raise InvalidAPIUsage(result["error"], status_code=409)

    logging.info(f"Admin {current_user['username']} created new user {data['username']}.")
    return jsonify(result), 201

# --- User Profile Endpoints ---
@app.route('/user/profile', methods=['GET', 'POST'])
@jwt_required()
def user_profile():
    current_user = get_jwt_identity()
    user_id = current_user['id']

    if request.method == 'GET':
        profile = db.find_user_by_id(user_id)
        if not profile:
            raise InvalidAPIUsage("Profile not found.", status_code=404)
        profile_data = dict(profile)
        pic_path = os.path.join(PROFILE_PICS_FOLDER, f"{user_id}.png")
        if os.path.exists(pic_path):
            profile_data['profile_picture_url'] = f"/user/profile_picture/{user_id}"
        return jsonify(profile_data)

    if request.method == 'POST':
        data = request.get_json()
        result = db.update_user_profile(user_id, data)
        if "error" in result:
            raise InvalidAPIUsage(result['error'], status_code=409)
        logging.info(f"User {current_user['username']} updated their profile.")
        return jsonify(result)

@app.route('/user/change_password', methods=['POST'])
@jwt_required()
def change_password():
    current_user_identity = get_jwt_identity()
    user_id = current_user_identity['id']
    username = current_user_identity['username']

    data = request.get_json()
    if not data or not all(k in data for k in ['current_password', 'new_password']):
        raise InvalidAPIUsage("Missing current or new password.", status_code=400)

    # Fetch the full user object once to get the password hash
    user = db.find_user_by_identifier(username)
    if not user or not db.verify_password(data['current_password'], user['password_hash']):
        raise InvalidAPIUsage("Invalid current password.", status_code=401)

    result = db.update_user_password(user_id, data['new_password'])
    logging.info(f"User {username} changed their password.")
    return jsonify(result)

@app.route('/user/profile_picture', methods=['POST'])
@jwt_required()
def upload_profile_picture():
    current_user = get_jwt_identity()
    user_id = current_user['id']

    if 'file' not in request.files:
        raise InvalidAPIUsage("No file part in the request.", status_code=400)
    file = request.files['file']
    if file.filename == '':
        raise InvalidAPIUsage("No file selected for uploading.", status_code=400)

    filename = f"{user_id}.png"
    filepath = os.path.join(PROFILE_PICS_FOLDER, filename)
    file.save(filepath)

    logging.info(f"User {current_user['username']} uploaded a new profile picture.")
    return jsonify({"message": "Profile picture uploaded successfully."})

@app.route('/user/profile_picture/<int:user_id>', methods=['GET'])
@jwt_required()
def get_profile_picture(user_id):
    filepath = os.path.join(PROFILE_PICS_FOLDER, f"{user_id}.png")
    if not os.path.exists(filepath):
        abort(404)
    return send_from_directory(PROFILE_PICS_FOLDER, f"{user_id}.png")


# --- Server Management Endpoints (Admin Only) ---
@app.route('/server/settings', methods=['GET', 'POST'])
@admin_required()
def server_settings():
    if request.method == 'GET':
        try:
            with open(SERVER_CONFIG_FILE, 'r') as f:
                return jsonify(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({})

    if request.method == 'POST':
        data = request.get_json()
        if not data:
            raise InvalidAPIUsage("No data provided.", status_code=400)
        with open(SERVER_CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        logging.info("Server settings updated.")
        return jsonify({"status": "success", "message": "Server settings saved."})

def _get_safe_path(path_suffix):
    base_path = os.path.abspath(SHARED_FOLDER)
    requested_path = os.path.abspath(os.path.join(base_path, path_suffix))
    if not requested_path.startswith(base_path):
        raise InvalidAPIUsage("File path is outside the allowed directory.", status_code=403)
    return requested_path

@app.route('/server/files/', defaults={'path': ''})
@app.route('/server/files/<path:path>')
@admin_required()
def list_server_files(path):
    safe_path = _get_safe_path(path)
    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        raise InvalidAPIUsage("Path does not exist or is not a directory.", status_code=404)

    items = []
    for item in os.listdir(safe_path):
        item_path = os.path.join(safe_path, item)
        if os.path.isdir(item_path):
            items.append({"name": item, "type": "dir", "size": 0})
        else:
            items.append({"name": item, "type": "file", "size": os.path.getsize(item_path)})
    return jsonify(items)

@app.route('/server/upload/', defaults={'path': ''}, methods=['POST'])
@app.route('/server/upload/<path:path>', methods=['POST'])
@admin_required()
def upload_to_server_folder(path):
    safe_path = _get_safe_path(path)
    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        raise InvalidAPIUsage("Upload path does not exist or is not a directory.", status_code=404)

    if 'file' not in request.files:
        raise InvalidAPIUsage("No file part in the request.", status_code=400)
    file = request.files['file']
    if file.filename == '':
        raise InvalidAPIUsage("No file selected for uploading.", status_code=400)

    filename = secure_filename(file.filename)
    file.save(os.path.join(safe_path, filename))
    return jsonify({"status": "success", "message": f"File '{filename}' uploaded successfully."})

@app.route('/server/download/<path:path>', methods=['GET'])
@admin_required()
def download_from_server_folder(path):
    safe_path = _get_safe_path(path)
    if not os.path.exists(safe_path) or os.path.isdir(safe_path):
        raise InvalidAPIUsage("File not found.", status_code=404)

    dir_name = os.path.dirname(safe_path)
    file_name = os.path.basename(safe_path)
    return send_from_directory(dir_name, file_name, as_attachment=True)


# --- Data Endpoints (Scoped by Company) ---
@app.route('/printers', methods=['GET', 'POST'])
@jwt_required()
def handle_printers():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']

    if request.method == 'GET':
        printers = db.get_all_printers(company_id)
        for printer in printers:
            printer['hourly_rate'] = calculate_printer_hourly_rate(printer)
        return jsonify(printers)

    if request.method == 'POST':
        # This endpoint now replaces all printers for the company
        data = request.json
        if not isinstance(data, list):
            raise InvalidAPIUsage("Data must be a list of printer objects.", status_code=400)

        db.replace_all_printers(data, company_id)
        logging.info(f"User {current_user['username']} replaced all printers for company {company_id}.")
        return jsonify({"message": "Printers updated successfully."})

@app.route('/printers/<string:printer_id>', methods=['DELETE'])
@jwt_required()
def delete_printer(printer_id):
    # This endpoint is no longer used by the client but is kept for potential direct API access.
    current_user = get_jwt_identity()
    company_id = current_user['company_id']
    if not db.delete_printer_by_id(printer_id, company_id):
        raise InvalidAPIUsage("Printer not found or you don't have permission to delete it.", status_code=404)
    logging.info(f"User {current_user['username']} deleted printer with ID: {printer_id}")
    return jsonify({"message": "Printer deleted"}), 200

@app.route('/filaments', methods=['GET', 'POST'])
@jwt_required()
def handle_filaments():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']

    if request.method == 'GET':
        return jsonify(db.get_all_filaments(company_id))

    if request.method == 'POST':
        # This endpoint now replaces all filaments for the company
        data = request.json
        if not isinstance(data, dict):
            raise InvalidAPIUsage("Data must be a dictionary of filaments.", status_code=400)

        db.replace_all_filaments(data, company_id)
        logging.info(f"User {current_user['username']} replaced all filaments for company {company_id}.")
        return jsonify({"message": "Filaments updated successfully."})

@app.route('/filaments/<string:material>/<string:brand>', methods=['DELETE'])
@jwt_required()
def delete_filament(material, brand):
    # This endpoint is no longer used by the client but is kept for potential direct API access.
    current_user = get_jwt_identity()
    company_id = current_user['company_id']
    if not db.delete_filament_by_material_and_brand(material, brand, company_id):
        raise InvalidAPIUsage("Filament not found or you don't have permission to delete it.", status_code=404)
    logging.info(f"User {current_user['username']} deleted filament: {material}/{brand}")
    return jsonify({"message": "Filament deleted"}), 200

@app.route('/logs', methods=['GET'])
@jwt_required()
def handle_logs():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']
    return jsonify(db.get_all_logs(company_id))

@app.route('/processed_log', methods=['GET'])
@jwt_required()
def get_processed_log():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']
    return jsonify(db.get_processed_log_filenames(company_id))

@app.route('/process_image', methods=['POST'])
@jwt_required()
def process_image():
    current_user = get_jwt_identity()
    company_id = current_user['company_id']

    if 'image' not in request.files or 'json' not in request.form:
        raise InvalidAPIUsage("Request must include 'image' and 'json' parts.", status_code=400)

    try:
        log_data = json.loads(request.form['json'])
    except json.JSONDecodeError:
        raise InvalidAPIUsage("Invalid JSON data in form.", status_code=400)

    image_file = request.files['image']
    filename = secure_filename(image_file.filename)

    # We can decide on a more robust storage strategy later
    # For now, let's just log it.
    log_entry = {
        "filename": filename,
        "timestamp": log_data.get('timestamp', datetime.now().isoformat()),
        "data": log_data
    }
    db.add_log(log_entry, company_id)
    logging.info(f"User {current_user['username']} processed and logged file: {filename}")
    return jsonify({"status": "success", "message": "Log saved."})


@app.route('/ocr_upload', methods=['POST'])
@jwt_required()
def ocr_upload():
    if ocr_reader is None:
        raise InvalidAPIUsage("OCR service is not available.", status_code=503)
    if 'image' not in request.files:
        raise InvalidAPIUsage("No file part in the request.", status_code=400)
    file = request.files['image']
    if file.filename == '':
        raise InvalidAPIUsage("No file selected for uploading.", status_code=400)

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logging.info(f"Processing OCR for file: {filename}")

        try:
            ocr_results = ocr_reader.readtext(filepath)
            extracted_data = extract_data_from_ocr(ocr_results) # Placeholder
            return jsonify(extracted_data)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

@app.route('/generate_quotation', methods=['POST'])
@jwt_required()
def create_quotation():
    if 'json' not in request.form:
        raise InvalidAPIUsage("Request must include 'json' part.", status_code=400)
    try:
        data = json.loads(request.form['json'])
    except json.JSONDecodeError:
        raise InvalidAPIUsage("Invalid JSON data in form.", status_code=400)

    # Handle optional logo upload
    logo_filepath = None
    if 'logo' in request.files:
        logo_file = request.files['logo']
        if logo_file.filename != '':
            filename = secure_filename(logo_file.filename)
            logo_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            logo_file.save(logo_filepath)
            data['company_details']['logo_path'] = logo_filepath # Pass the server path to the generator

    customer_name = data.get('customer_name', 'quote')
    safe_customer_name = secure_filename(customer_name)
    filename = f"Quotation_{safe_customer_name}_{int(time.time())}.pdf"
    output_filepath = os.path.join(app.config['GENERATED_FILES_FOLDER'], filename)

    try:
        generate_quotation_pdf(output_filepath, data)
        return send_from_directory(app.config['GENERATED_FILES_FOLDER'], filename, as_attachment=True)
    finally:
        # Clean up uploaded logo if it exists
        if logo_filepath and os.path.exists(logo_filepath):
            os.remove(logo_filepath)

# --- Main Execution ---
if __name__ == '__main__':
    initialize_server_folders()
    db.initialize_database()
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
