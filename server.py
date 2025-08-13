import os
import re
import json
import time
import shutil
import sys
from datetime import datetime, timedelta
import easyocr
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# --- Server Configuration ---
# These paths are relative to where the server.py script is run.
# On a platform like Render, these will be created in the instance's filesystem.
PRINTERS_JSON_PATH = "data/printers.json"
PRICING_JSON_PATH = "data/filament_costs.json"
APP_LOGS_PATH = "data/app_logs.json"
UPLOAD_FOLDER = "uploads"
GENERATED_FILES_FOLDER = "generated_files"

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app) # Allows the client to make requests to this server
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- One-time OCR Model Loading ---
# We load the model into memory once when the server starts.
print("Loading EasyOCR model into memory...")
try:
    ocr_reader = easyocr.Reader(['en'])
    print("EasyOCR model loaded successfully.")
except Exception as e:
    print(f"FATAL: Could not load EasyOCR model. Error: {e}")
    ocr_reader = None

# --- Initial File & Folder Setup ---
def initialize_server_files():
    """Ensures all necessary data files and folders exist."""
    os.makedirs("data", exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FILES_FOLDER, exist_ok=True)

    if not os.path.exists(PRINTERS_JSON_PATH):
        with open(PRINTERS_JSON_PATH, 'w') as f:
            json.dump([], f)
    if not os.path.exists(PRICING_JSON_PATH):
        with open(PRICING_JSON_PATH, 'w') as f:
            json.dump({}, f)
    if not os.path.exists(APP_LOGS_PATH):
        with open(APP_LOGS_PATH, 'w') as f:
            json.dump([], f)

# --- Helper Functions (Server-Side Logic) ---
# (Includes all calculation and data handling functions from the original app)

def load_json_file(path, default_data=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data if default_data is not None else []

def save_json_file(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def calculate_printer_hourly_rate(printer_data):
    try:
        total_cost = printer_data['setup_cost'] + (printer_data['maintenance_cost'] * printer_data['lifetime_years'])
        total_hours = printer_data['lifetime_years'] * 365 * 24 * (printer_data.get('uptime_percent', 50) / 100)
        if total_hours == 0: return 0.0
        depreciation = total_cost / total_hours
        electricity = (printer_data['power_w'] / 1000) * printer_data['price_kwh']
        return depreciation + electricity
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0

def calculate_cogs_values(form_data, printer_data, filament_data):
    try:
        filament_g = float(form_data.get("Filament (g)", 0))
        time_str = form_data.get("Time (e.g. 7h 30m)", "0h 0m")
        labour_time_min = float(form_data.get("Labour Time (min)", 0))
        labour_rate_user = float(form_data.get("Labour Rate (₹/hr)", 100))
        
        print_time_hours = parse_time_string(time_str)
        mat_cost = (filament_data.get('price', 0) / 1000) * filament_g * filament_data.get('efficiency_factor', 1.0)
        labour_cogs = (labour_rate_user / 60) * labour_time_min
        printer_hourly_rate = calculate_printer_hourly_rate(printer_data)
        printer_cogs = printer_hourly_rate * printer_data.get('buffer_factor', 1.0) * print_time_hours
        
        total_cogs = mat_cost + labour_cogs + printer_cogs
        return {"user_cogs": total_cogs}
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return {"user_cogs": 0.0}

def parse_time_string(time_str):
    h = m = s = 0
    h_match = re.search(r'(\d+)\s*h', time_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*m', time_str, re.IGNORECASE)
    s_match = re.search(r'(\d+)\s*s', time_str, re.IGNORECASE)
    if h_match: h = int(h_match.group(1))
    if m_match: m = int(m_match.group(1))
    if s_match: s = int(s_match.group(1))
    return round(h + (m / 60.0) + (s / 3600.0), 2)

# --- API Endpoints ---

@app.route('/printers', methods=['GET', 'POST'])
def handle_printers():
    if request.method == 'GET':
        printers = load_json_file(PRINTERS_JSON_PATH, [])
        for printer in printers:
            printer['hourly_rate'] = calculate_printer_hourly_rate(printer)
        return jsonify(printers)
    
    if request.method == 'POST':
        data = request.json
        printers = load_json_file(PRINTERS_JSON_PATH, [])
        if 'id' in data and data['id']: # Update
            printers = [data if p.get("id") == data['id'] else p for p in printers]
        else: # Add new
            data['id'] = str(time.time())
            printers.append(data)
        save_json_file(PRINTERS_JSON_PATH, printers)
        return jsonify(data), 201

@app.route('/printers/<string:printer_id>', methods=['DELETE'])
def delete_printer(printer_id):
    printers = load_json_file(PRINTERS_JSON_PATH, [])
    printers = [p for p in printers if p.get("id") != printer_id]
    save_json_file(PRINTERS_JSON_PATH, printers)
    return jsonify({"message": "Printer deleted"}), 200

@app.route('/filaments', methods=['GET', 'POST'])
def handle_filaments():
    if request.method == 'GET':
        return jsonify(load_json_file(PRICING_JSON_PATH, {}))
    
    if request.method == 'POST':
        data = request.json # Expects {"material": "PLA", "brand": "Generic", "details": {...}}
        filaments = load_json_file(PRICING_JSON_PATH, {})
        material, brand = data['material'], data['brand']
        if material not in filaments:
            filaments[material] = {}
        filaments[material][brand] = data['details']
        save_json_file(PRICING_JSON_PATH, filaments)
        return jsonify(data), 201

@app.route('/filaments/<string:material>/<string:brand>', methods=['DELETE'])
def delete_filament(material, brand):
    filaments = load_json_file(PRICING_JSON_PATH, {})
    if material in filaments and brand in filaments[material]:
        del filaments[material][brand]
        if not filaments[material]:
            del filaments[material]
        save_json_file(PRICING_JSON_PATH, filaments)
    return jsonify({"message": "Filament deleted"}), 200

@app.route('/logs', methods=['GET', 'POST'])
def handle_logs():
    if request.method == 'GET':
        return jsonify(load_json_file(APP_LOGS_PATH, []))
    
    if request.method == 'POST':
        log_entry = request.json
        logs = load_json_file(APP_LOGS_PATH, [])
        logs.append(log_entry)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        save_json_file(APP_LOGS_PATH, logs)
        return jsonify(log_entry), 201

@app.route('/ocr', methods=['POST'])
def process_ocr():
    if ocr_reader is None:
        return jsonify({"error": "OCR service is not available"}), 503
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            ocr_results = ocr_reader.readtext(filepath)
            # This function needs access to printer/filament data for better matching
            # We pass the paths so it can load them itself.
            extracted_data = extract_data_from_ocr(ocr_results)
            return jsonify(extracted_data)
        except Exception as e:
            return jsonify({"error": f"OCR processing failed: {e}"}), 500
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

@app.route('/generate-quotation', methods=['POST'])
def create_quotation():
    data = request.json
    try:
        filename = f"Quotation_{data.get('customer_name', 'quote').replace(' ', '_')}_{int(time.time())}.pdf"
        filepath = os.path.join(app.config['GENERATED_FILES_FOLDER'], filename)
        
        generate_quotation_pdf(filepath, data)
        
        # Return a URL the client can use to download the file
        download_url = f"/downloads/{filename}"
        return jsonify({"download_url": download_url, "filename": filename})
    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {e}"}), 500

@app.route('/downloads/<string:filename>', methods=['GET'])
def download_file(filename):
    """Endpoint to serve the generated files."""
    return send_from_directory(app.config['GENERATED_FILES_FOLDER'], filename, as_attachment=True)

# --- Main Execution ---
if __name__ == '__main__':
    initialize_server_files()
    port = int(os.environ.get("PORT", 5000))
    # Setting host to '0.0.0.0' makes the server publicly accessible
    app.run(host='0.0.0.0', port=port, debug=True)
