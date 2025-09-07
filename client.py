import os
import re
import json
import time
import shutil
import threading
import queue
import sys
import traceback
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageOps
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import Toplevel, messagebox, simpledialog, scrolledtext, filedialog
import requests
from io import BytesIO
import jwt
from jwt import PyJWTError

# --- [CONFIG] SERVER CONFIGURATION ---
SERVER_URL = "https://server.fabra-forma.com" # Use your server's local or network IP address
# ------------------------------------

CLIENT_CONFIG_PATH = "client_config.json"

# --- API CLIENT ---
class APIClient:
    """Handles all communication with the Flask server with JWT authentication."""
    def __init__(self):
        self.token = None
        self.user_info = {}

    def _get_auth_header(self):
        if not self.token:
            print("Auth Error: No authentication token found.")
            return None
        return {'Authorization': f'Bearer {self.token}'}

    def _handle_error(self, error, response=None):
        title = "API Error"
        message = str(error)
        if response is not None:
            if response.status_code in [401, 403]:
                message = "Your session has expired or you lack permissions. Please log in again."
            else:
                try:
                    server_error = response.json()
                    if 'message' in server_error: message = server_error['message']
                    elif 'error' in server_error: message = server_error['error']
                except json.JSONDecodeError:
                    message = response.text
        print(f"API Error: {message}")
        # messagebox.showerror(title, f"An error occurred:\n\n{message}")


    def login(self, identifier, password, remember_me=False):
        try:
            payload = {'identifier': identifier, 'password': password, 'remember_me': remember_me}
            response = requests.post(f"{SERVER_URL}/auth/login", json=payload); response.raise_for_status()
            data = response.json()
            if data and 'token' in data:
                self.token = data['token']
                try:
                    self.user_info = jwt.decode(self.token, options={"verify_signature": False})
                except PyJWTError as e:
                    messagebox.showerror("Token Error", f"Could not decode user info: {e}"); self.logout(); return None
                return data
            return None
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def refresh_token(self, remember_token):
        try:
            payload = {'remember_token': remember_token}
            response = requests.post(f"{SERVER_URL}/auth/refresh", json=payload); response.raise_for_status()
            data = response.json()
            if data and 'token' in data:
                self.token = data['token']
                try:
                    self.user_info = jwt.decode(self.token, options={"verify_signature": False})
                except PyJWTError as e:
                    messagebox.showerror("Token Error", f"Could not decode user info: {e}"); self.logout(); return False
                return True
            return False
        except requests.exceptions.RequestException:
            return False

    def logout(self, remember_token=None):
        headers = self._get_auth_header()
        if headers and remember_token:
            try:
                requests.post(f"{SERVER_URL}/auth/logout", json={'remember_token': remember_token}, headers=headers)
            except requests.exceptions.RequestException:
                pass
        self.token = None
        self.user_info = {}

    def register_company(self, company_name, admin_username, admin_email, admin_password):
        try:
            payload = {'company_name': company_name, 'admin_username': admin_username, 'admin_email': admin_email, 'admin_password': admin_password}
            response = requests.post(f"{SERVER_URL}/auth/register_company", json=payload); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def create_user(self, username, email, password, role):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            payload = {'username': username, 'email': email, 'password': password, 'role': role}
            response = requests.post(f"{SERVER_URL}/auth/create_user", json=payload, headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def get_profile(self):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            response = requests.get(f"{SERVER_URL}/user/profile", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def update_profile(self, profile_data):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            response = requests.post(f"{SERVER_URL}/user/profile", json=profile_data, headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def change_password(self, current_password, new_password):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            payload = {'current_password': current_password, 'new_password': new_password}
            response = requests.post(f"{SERVER_URL}/user/change_password", json=payload, headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def upload_profile_picture(self, file_path):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f)}
                response = requests.post(f"{SERVER_URL}/user/profile_picture", files=files, headers=headers)
                response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None
        except FileNotFoundError: messagebox.showerror("File Error", f"File not found: {file_path}"); return None

    def get_server_settings(self):
        headers = self._get_auth_header()
        if not headers: return {}
        try:
            response = requests.get(f"{SERVER_URL}/server/settings", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return {}

    def save_server_settings(self, data):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            response = requests.post(f"{SERVER_URL}/server/settings", json=data, headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None

    def list_server_files(self, path):
        headers = self._get_auth_header()
        if not headers: return []
        try:
            response = requests.get(f"{SERVER_URL}/server/files/{path}", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return []

    def upload_file_to_server(self, local_path, server_subpath):
        headers = self._get_auth_header()
        if not headers: return None
        try:
            with open(local_path, 'rb') as f:
                files = {'file': (os.path.basename(local_path), f)}
                response = requests.post(f"{SERVER_URL}/server/upload/{server_subpath}", files=files, headers=headers)
                response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return None
        except FileNotFoundError: messagebox.showerror("File Error", f"File not found: {local_path}"); return None

    def download_server_file(self, server_filepath, local_save_path):
        headers = self._get_auth_header()
        if not headers: return False
        try:
            with requests.get(f"{SERVER_URL}/server/download/{server_filepath}", stream=True, headers=headers) as r:
                r.raise_for_status()
                with open(local_save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            return True
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return False

    def get_printers(self):
        headers = self._get_auth_header()
        if not headers: return []
        try:
            response = requests.get(f"{SERVER_URL}/printers", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return []

    def save_printers(self, data):
        headers = self._get_auth_header()
        if not headers: return False
        try:
            response = requests.post(f"{SERVER_URL}/printers", json=data, headers=headers); response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return False

    def get_filaments(self):
        headers = self._get_auth_header()
        if not headers: return {}
        try:
            response = requests.get(f"{SERVER_URL}/filaments", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return {}

    def save_filaments(self, data):
        headers = self._get_auth_header()
        if not headers: return False
        try:
            response = requests.post(f"{SERVER_URL}/filaments", json=data, headers=headers); response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return False

    def get_logs(self):
        headers = self._get_auth_header()
        if not headers: return []
        try:
            response = requests.get(f"{SERVER_URL}/logs", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return []

    def get_processed_log(self):
        headers = self._get_auth_header()
        if not headers: return {}
        try:
            response = requests.get(f"{SERVER_URL}/processed_log", headers=headers); response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e: print(f"Could not fetch processed log: {e}"); return {}

    def process_image(self, file_path, verification_data):
        headers = self._get_auth_header()
        if not headers: return {"status": "error"}
        try:
            with open(file_path, 'rb') as f:
                files = {'image': (os.path.basename(file_path), f)}
                data = {'json': json.dumps(verification_data)}
                response = requests.post(f"{SERVER_URL}/process_image", files=files, data=data, headers=headers)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return {"status": "error", "message": "Network error"}
        except FileNotFoundError: return {"status": "error", "message": f"File not found: {file_path}"}

    def generate_quotation(self, data, save_path):
        headers = self._get_auth_header()
        if not headers: return False
        try:
            logo_path = data.get("company_details", {}).get("logo_path")
            files = {'logo': (os.path.basename(logo_path), open(logo_path, 'rb'))} if logo_path and os.path.exists(logo_path) else None
            payload = {'json': json.dumps(data)}

            with requests.post(f"{SERVER_URL}/generate_quotation", data=payload, files=files, headers=headers, stream=True) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            # Try to decode error json if the server sent one
            try:
                error_info = json.loads(e.response.text)
                messagebox.showerror("API Error", f"An error occurred:\n\n{error_info.get('message', e.response.text)}")
            except (json.JSONDecodeError, AttributeError):
                self._handle_error(e, e.response)
            return False
        except FileNotFoundError as e:
            messagebox.showerror("File Error", f"Logo file not found: {e}")
            return False

    def upload_for_ocr(self, file_path):
        headers = self._get_auth_header()
        if not headers: return {}
        try:
            with open(file_path, 'rb') as f:
                files = {'image': (os.path.basename(file_path), f)}
                response = requests.post(f"{SERVER_URL}/ocr_upload", files=files, headers=headers); response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return {}
        except FileNotFoundError: messagebox.showerror("File Error", f"File not found: {file_path}"); return {}

    def download_file(self, endpoint, save_path):
        headers = self._get_auth_header()
        if not headers: return False
        try:
            with requests.get(f"{SERVER_URL}/{endpoint}", stream=True, headers=headers) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            return True
        except requests.exceptions.RequestException as e: self._handle_error(e, e.response); return False

# --- HELPER FUNCTIONS ---
def load_client_config():
    try:
        with open(CLIENT_CONFIG_PATH, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}
def save_client_config(data):
    with open(CLIENT_CONFIG_PATH, 'w') as f: json.dump(data, f, indent=4)
def parse_time_string(time_str):
    h_match = re.search(r'(\d+)\s*h', time_str, re.IGNORECASE); h = int(h_match.group(1)) if h_match else 0
    m_match = re.search(r'(\d+)\s*m', time_str, re.IGNORECASE); m = int(m_match.group(1)) if m_match else 0
    s_match = re.search(r'(\d+)\s*s', time_str, re.IGNORECASE); s = int(s_match.group(1)) if s_match else 0
    return round(h + (m / 60.0) + (s / 3600.0), 2)
def calculate_printer_hourly_rate(printer_data):
    try:
        total_cost = printer_data['setup_cost'] + (printer_data['maintenance_cost'] * printer_data['lifetime_years'])
        total_hours = printer_data['lifetime_years'] * 365 * 24 * (printer_data.get('uptime_percent', 50) / 100)
        if total_hours == 0: return 0.0
        return (total_cost / total_hours) + ((printer_data['power_w'] / 1000) * printer_data['price_kwh'])
    except (KeyError, TypeError, ZeroDivisionError): return 0.0
def calculate_cogs_values(form_data, printer_data, filament_data):
    try:
        filament_g = float(form_data.get("Filament (g)", 0)); time_str = form_data.get("Time (e.g. 7h 30m)", "0h 0m")
        labour_time_min = float(form_data.get("Labour Time (min)", 0)); labour_rate_user = float(form_data.get("Labour Rate (₹/hr)", 0))
        print_time_hours = parse_time_string(time_str)
        mat_cost = (filament_data.get('price', 0) / 1000) * filament_g * filament_data.get('efficiency_factor', 1.0)
        labour_cogs = (labour_rate_user / 60) * labour_time_min
        printer_cogs = calculate_printer_hourly_rate(printer_data) * printer_data.get('buffer_factor', 1.0) * print_time_hours
        total_cogs_user = mat_cost + labour_cogs + printer_cogs
        mat_cost_default = (filament_data.get('price', 0) / 1000) * filament_g
        labour_cogs_default = (100 / 60) * labour_time_min
        printer_cogs_default = calculate_printer_hourly_rate(printer_data) * print_time_hours
        total_cogs_default = mat_cost_default + labour_cogs_default + printer_cogs_default
        return {"user_cogs": total_cogs_user, "default_cogs": total_cogs_default}
    except (ValueError, TypeError, KeyError, ZeroDivisionError): return {"user_cogs": 0.0, "default_cogs": 0.0}
def create_circular_image(image, size):
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    output_image = ImageOps.fit(image, (size, size), centering=(0.5, 0.5))
    output_image.putalpha(mask)
    return output_image

# --- GUI ---
class Page(ttk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def show(self): self.lift()
    def on_show(self): pass

class LoginPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        self.container = ttk.Frame(self)
        self.container.place(relx=0.5, rely=0.5, anchor="center")

        self.create_login_widgets()
        self.create_register_widgets()

        self.show_login()

    def create_login_widgets(self):
        self.login_frame = ttk.Frame(self.container)

        title = ttk.Label(self.login_frame, text="FabraForma AL Login", font=('Montserrat', 16, 'bold'), bootstyle="primary")
        title.pack(pady=(0, 20))

        ttk.Label(self.login_frame, text="Email or Username:").pack(anchor='w', padx=10)
        self.identifier_var = ttk.StringVar()
        ttk.Entry(self.login_frame, textvariable=self.identifier_var, width=40).pack(pady=(0, 10), padx=10)

        ttk.Label(self.login_frame, text="Password:").pack(anchor='w', padx=10)
        self.password_var = ttk.StringVar()
        ttk.Entry(self.login_frame, textvariable=self.password_var, show="*", width=40).pack(pady=(0, 10), padx=10)

        self.remember_me_var = ttk.BooleanVar()
        ttk.Checkbutton(self.login_frame, text="Remember Me", variable=self.remember_me_var, bootstyle="primary").pack(pady=5, padx=10, anchor='w')

        self.login_button = ttk.Button(self.login_frame, text="Login", command=self.attempt_login, bootstyle="primary")
        self.login_button.pack(pady=10, fill=X, padx=10)

        self.switch_to_reg_button = ttk.Button(self.login_frame, text="Register New Company", command=self.show_register, bootstyle="secondary")
        self.switch_to_reg_button.pack(pady=(5,10), fill=X, padx=10)

        self.status_label = ttk.Label(self.login_frame, text="", bootstyle="danger")
        self.status_label.pack()

    def create_register_widgets(self):
        self.register_frame = ttk.Frame(self.container)

        title = ttk.Label(self.register_frame, text="Register New Company", font=('Montserrat', 16, 'bold'), bootstyle="primary")
        title.pack(pady=(0, 20))

        fields = {
            "Company Name:": ttk.StringVar(),
            "Your Username:": ttk.StringVar(),
            "Your Email:": ttk.StringVar(),
            "Password:": ttk.StringVar(),
            "Confirm Password:": ttk.StringVar()
        }
        self.reg_vars = fields

        for label, var in fields.items():
            ttk.Label(self.register_frame, text=label).pack(anchor='w', padx=10)
            show_char = "*" if "Password" in label else ""
            ttk.Entry(self.register_frame, textvariable=var, show=show_char, width=40).pack(pady=(0, 10), padx=10)

        self.register_button = ttk.Button(self.register_frame, text="Register", command=self.attempt_register, bootstyle="primary")
        self.register_button.pack(pady=10, fill=X, padx=10)

        self.switch_to_login_button = ttk.Button(self.register_frame, text="Back to Login", command=self.show_login, bootstyle="secondary")
        self.switch_to_login_button.pack(pady=(5,10), fill=X, padx=10)

    def show_login(self):
        self.register_frame.pack_forget()
        self.login_frame.pack(fill="both", expand=True)

    def show_register(self):
        self.login_frame.pack_forget()
        self.register_frame.pack(fill="both", expand=True)

    def attempt_login(self):
        identifier = self.identifier_var.get()
        password = self.password_var.get()
        remember = self.remember_me_var.get()

        if not all([identifier, password]):
            self.status_label.config(text="Username/Email and password are required."); return
        self.login_button.config(state="disabled"); self.status_label.config(text="")

        def login_task():
            response_data = self.app.api.login(identifier, password, remember)
            self.master.after(0, self._process_login_result, response_data)

        self.app.run_threaded_task(login_task, "Logging In...")

    def _process_login_result(self, response_data):
        self.login_button.config(state="normal")
        if response_data and 'token' in response_data:
            if 'remember_token' in response_data:
                config = load_client_config()
                config['remember_token'] = response_data['remember_token']
                save_client_config(config)
            self.status_label.config(text=""); self.app.on_login_success()
        else:
            self.status_label.config(text="Login failed. Check credentials."); self.password_var.set("")

    def attempt_register(self):
        company = self.reg_vars["Company Name:"].get()
        user = self.reg_vars["Your Username:"].get()
        email = self.reg_vars["Your Email:"].get()
        pwd1 = self.reg_vars["Password:"].get()
        pwd2 = self.reg_vars["Confirm Password:"].get()

        if not all([company, user, email, pwd1, pwd2]):
            messagebox.showerror("Input Error", "All fields are required.", parent=self); return
        if pwd1 != pwd2:
            messagebox.showerror("Input Error", "Passwords do not match.", parent=self); return

        def task():
            result = self.app.api.register_company(company, user, email, pwd1)
            if result and result.get('message'):
                messagebox.showinfo("Success", result['message'], parent=self)
                if "successfully" in result['message']:
                    self.show_login()

        self.app.run_threaded_task(task, "Registering...")

class MonitorPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        ttk.Label(self, text="Monitoring Log", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,0))
        top_frame = ttk.Frame(self); top_frame.pack(pady=10, padx=10, fill="x")
        self.start_button = ttk.Button(top_frame, text="Start Monitoring", command=app.on_start, bootstyle="primary"); self.start_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(top_frame, text="Stop Monitoring", command=app.on_stop, state="disabled", bootstyle="secondary"); self.stop_button.pack(side="left", padx=5)
        self.skip_button = ttk.Button(top_frame, text="Process Skipped Files", command=self.process_skipped, bootstyle="info"); self.skip_button.pack(side="right", padx=5)

        self.status_text = scrolledtext.ScrolledText(self, height=15, width=100,
                                                      bg="#3a4be3", fg="#ffafda", relief="flat", bd=5,
                                                      font=("Consolas", 11), insertbackground="#ffafda")

        self.status_text.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        self.status_text.insert(END, "📡 Bot is idle. Press Start to begin monitoring.\n")

    def get_status_box(self): return self.status_text

    def set_bot_status(self, is_running):
        self.start_button.config(state="disabled" if is_running else "normal")
        self.stop_button.config(state="normal" if is_running else "disabled")
        self.skip_button.config(state="disabled" if is_running else "normal")
        self.app.update_sidebar_state(is_running)

    def process_skipped(self):
        if self.app.monitor_controller:
            self.app.run_threaded_task(self.app.monitor_controller.requeue_skipped_files, "Processing Skipped Files...")

class LogsPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.logs = []; self.sort_column_name = "Date"; self.sort_reverse = True
        ttk.Label(self, text="Processed Logs", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))
        self.list_frame = ttk.Frame(self)
        controls_frame = ttk.Frame(self.list_frame); controls_frame.pack(fill='x', pady=5, padx=5)
        self.search_var = ttk.StringVar(); self.search_var.trace_add("write", lambda *args: self.filter_and_populate_tree())
        ttk.Label(controls_frame, text="Search:").pack(side='left', padx=(0,5)); ttk.Entry(controls_frame, textvariable=self.search_var, width=30).pack(side='left')
        ttk.Button(controls_frame, text="Download Selected", command=self.download_selected_logs, bootstyle="success-outline").pack(side='right', padx=5)
        ttk.Button(controls_frame, text="Refresh Logs", command=self.on_show, bootstyle="info").pack(side='right')
        tree_container = ttk.Frame(self.list_frame); tree_container.pack(fill='both', expand=True, padx=5, pady=5)
        columns = ("Date", "Filename", "Material", "User COGS (₹)"); self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", bootstyle="primary")
        for col in columns: self.tree.heading(col, text=col, command=lambda _col=col: self.sort_column(_col))
        self.tree.column("Date", width=160); self.tree.column("Filename", width=200); self.tree.column("Material", width=150); self.tree.column("User COGS (₹)", width=100, anchor="e")
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, bootstyle="round"); self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y"); self.tree.bind("<<TreeviewSelect>>", self.on_log_select)

        self.total_frame = ttk.Frame(self.list_frame); self.total_frame.pack(fill='x', padx=5, pady=(5,0))
        self.total_cogs_label = ttk.Label(self.total_frame, text="Total COGS: ₹0.00", font=('-weight', 'bold'))
        self.total_cogs_label.pack(side='right')

        self.loading_label = ttk.Label(self.list_frame, text="Loading logs...")
        self.details_frame = ttk.Frame(self); ttk.Button(self.details_frame, text="← Back to List", command=self.show_list_view, bootstyle="secondary").pack(anchor="w", pady=5, padx=5)
        main_pane = ttk.PanedWindow(self.details_frame, orient=HORIZONTAL); main_pane.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.image_canvas = ImageCanvas(main_pane); main_pane.add(self.image_canvas, weight=3)
        right_details_frame = ttk.Frame(main_pane)
        self.details_text = scrolledtext.ScrolledText(right_details_frame, height=8, bg="#1c246d", fg="#ffafda", relief="flat", bd=5, insertbackground="#ffafda")
        self.details_text.pack(fill="both", expand=True)
        download_frame = ttk.Frame(right_details_frame); download_frame.pack(pady=10)
        ttk.Button(download_frame, text="Download Excel Log", command=self.download_log, bootstyle="success").pack(side="left", padx=10)
        ttk.Button(download_frame, text="Download Master Log", command=self.download_master_log, bootstyle="success-outline").pack(side="left", padx=10)
        main_pane.add(right_details_frame, weight=1)
        self.show_list_view()

    def on_show(self):
        self.show_list_view()
        self.tree.delete(*self.tree.get_children())
        self.loading_label.place(relx=0.5, rely=0.4, anchor="center")
        self.app.run_threaded_task(self.fetch_logs_thread, "Refreshing Logs...")

    def fetch_logs_thread(self):
        try:
            logs = self.app.api.get_logs()
            self.after(0, self.update_tree_with_logs, logs)
        except Exception as e:
            print(f"Error fetching logs thread: {e}")
            self.after(0, self.show_load_error)

    def update_tree_with_logs(self, logs):
        self.loading_label.place_forget()
        self.logs = logs
        self.filter_and_populate_tree()

    def show_load_error(self):
        self.loading_label.config(text="Failed to load logs. Check connection and refresh.")

    def show_list_view(self):
        self.details_frame.pack_forget(); self.list_frame.pack(fill="both", expand=True, padx=10, pady=0)
        if self.tree.selection(): self.tree.selection_remove(self.tree.selection()[0])

    def on_log_select(self, event):
        if not (selected_items := self.tree.selection()): return
        if len(selected_items) > 1: return # Don't go to detail view on multi-select
        self.list_frame.pack_forget(); self.details_frame.pack(fill="both", expand=True, padx=10, pady=0)
        if log_entry := next((log for log in self.logs if log['timestamp'] == selected_items[0]), None):
            self.image_canvas.load_image_from_url(f"{SERVER_URL}/images/{log_entry['image_path']}")
            self.details_text.delete('1.0', END); self.details_text.insert('1.0', "\n".join(f"{k}: {v}" for k, v in log_entry['data'].items()))

    def filter_and_populate_tree(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        search_term = self.search_var.get().lower()

        filtered_logs = []
        for log in self.logs:
            log_filename = log.get('filename', '')
            log_material = log.get('data', {}).get('Material', '')
            log_brand = log.get('data', {}).get('Brand', '')
            if not search_term or any(search_term in str(val).lower() for val in (log_filename, log_material, log_brand)):
                filtered_logs.append(log)

        sort_key_map = {
            "Date": lambda log: log.get('timestamp', ''),
            "Filename": lambda log: log.get('filename', ''),
            "Material": lambda log: f"{log.get('data', {}).get('Material', '')} {log.get('data', {}).get('Brand', '')}",
            "User COGS (₹)": lambda log: float(log.get('data', {}).get('User COGS (₹)', 0))
        }

        sort_function = sort_key_map.get(self.sort_column_name, sort_key_map["Date"])
        filtered_logs.sort(key=sort_function, reverse=self.sort_reverse)

        for i, log in enumerate(filtered_logs):
            try:
                dt_obj = datetime.fromisoformat(log['timestamp']); date_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                data = log.get('data', {})
                values = (date_str, log.get('filename', 'N/A'), f"{data.get('Material', 'N/A')} ({data.get('Brand', 'N/A')})", data.get('User COGS (₹)', '0.00'))
                self.tree.insert('', 'end', iid=log['timestamp'], values=values, tags=('oddrow' if i % 2 else 'evenrow',))
            except (KeyError, ValueError, Exception) as e:
                print(f"Skipping malformed log entry: {log.get('timestamp')}. Error: {e}")
        self.update_total_cogs()

    def update_total_cogs(self):
        total_cogs = 0.0
        for item_id in self.tree.get_children():
            try:
                cogs_value = self.tree.item(item_id, 'values')[3]
                total_cogs += float(cogs_value)
            except (ValueError, IndexError):
                continue
        self.total_cogs_label.config(text=f"Total COGS: ₹{total_cogs:.2f}")

    def sort_column(self, col):
        self.sort_reverse = not self.sort_reverse if self.sort_column_name == col else True
        self.sort_column_name = col
        self.filter_and_populate_tree()

    def download_log(self):
        if not (selected_items := self.tree.selection()) or len(selected_items) > 1:
            return messagebox.showwarning("Selection Error", "Please select exactly one log to download.")

        if not (log_entry := next((log for log in self.logs if log['timestamp'] == selected_items[0]), None)): return
        filename = f"{log_entry['filename']}.xlsx"
        if not (save_path := filedialog.asksaveasfilename(initialfile=filename, defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])): return

        def task():
            if self.app.api.download_file(f"download/log/{filename}", save_path):
                messagebox.showinfo("Success", f"Log downloaded to:\n{save_path}")

        self.app.run_threaded_task(task, "Downloading...")

    def download_selected_logs(self):
        selected_items = self.tree.selection()
        if not selected_items:
            return messagebox.showwarning("No Selection", "Please select one or more logs to download.")

        folder_selected = filedialog.askdirectory(title="Select Folder to Save Logs")
        if not folder_selected:
            return

        logs_to_download = [log for log in self.logs if log['timestamp'] in selected_items]

        def task():
            for log_entry in logs_to_download:
                filename = f"{log_entry['filename']}.xlsx"
                save_path = os.path.join(folder_selected, filename)
                self.app.api.download_file(f"download/log/{filename}", save_path)
            messagebox.showinfo("Success", f"{len(logs_to_download)} logs downloaded to:\n{folder_selected}")

        self.app.run_threaded_task(task, f"Downloading {len(logs_to_download)} logs...")

    def download_master_log(self):
        year = simpledialog.askstring("Input", "Enter Year (e.g., 2024):", parent=self)
        month = simpledialog.askstring("Input", "Enter Month Name (e.g., January):", parent=self)

        if not year or not month:
            return

        year_month = f"{year}_{month.capitalize()}"
        filename = f"master_log_{month.capitalize()}.xlsx"
        if not (save_path := filedialog.asksaveasfilename(initialfile=filename, defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])): return

        def task():
            if self.app.api.download_file(f"download/masterlog/{year_month}", save_path):
                messagebox.showinfo("Success", f"Master log for {month} {year} downloaded to:\n{save_path}")

        self.app.run_threaded_task(task, "Downloading Master Log...")

class ImageCanvas(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.original_image = None
        self.zoom_factor = 1.0
        self.image_tk = None

        self.canvas = ttk.Canvas(self, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas.bind('<MouseWheel>', self.zoom)
        self.canvas.bind('<ButtonPress-1>', self.start_pan)
        self.canvas.bind('<B1-Motion>', self.pan)

    def load_image_from_url(self, url):
        self.canvas.delete("all")
        self.canvas.create_text(self.winfo_width()/2, self.winfo_height()/2, text="Loading image...", fill="#ffafda", font=('Montserrat', 12))
        self.original_image = None
        threading.Thread(target=self._fetch_image, args=(url,), daemon=True).start()

    def _fetch_image(self, url):
        try:
            api_client = self.winfo_toplevel().app.api
            headers = api_client._get_auth_header()
            if not headers: raise Exception("Authentication failed.")
            response = requests.get(url, stream=True, headers=headers); response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            self.after(0, self._display_fetched_image, image)
        except (requests.exceptions.RequestException, IOError, Exception) as e:
            self.after(0, self._display_fetch_error, e)

    def _display_fetched_image(self, image):
        self.original_image = image
        self.after(100, self.fit_image_to_canvas)

    def _display_fetch_error(self, e):
        self.canvas.delete("all")
        self.canvas.create_text(self.winfo_width()/2, self.winfo_height()/2, text=f"Image not found\n{e}", fill="#ffafda", font=('Montserrat', 12))
        self.original_image = None

    def load_image_from_path(self, path):
        try:
            self.original_image = Image.open(path)
            self.after(100, self.fit_image_to_canvas)
        except (IOError) as e:
            self.canvas.delete("all")
            self.canvas.create_text(self.winfo_width()/2, self.winfo_height()/2, text=f"Image not found\n{e}", fill="#ffafda", font=('Montserrat', 12))
            self.original_image = None

    def fit_image_to_canvas(self):
        if not self.original_image: return
        if (canvas_width := self.winfo_width()) <= 1 or (canvas_height := self.winfo_height()) <= 1: return self.after(100, self.fit_image_to_canvas)
        img_width, img_height = self.original_image.size
        self.zoom_factor = min(canvas_width / img_width, canvas_height / img_height)
        self.display_image()

    def display_image(self):
        if not self.original_image: return
        width = int(self.original_image.width * self.zoom_factor)
        height = int(self.original_image.height * self.zoom_factor)
        resized_image = self.original_image.resize((width, height), Image.Resampling.LANCZOS)
        self.image_tk = ImageTk.PhotoImage(resized_image); self.canvas.delete("all")
        self.canvas.create_image((self.winfo_width() - width) / 2, (self.winfo_height() - height) / 2, anchor='nw', image=self.image_tk)
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def zoom(self, event):
        if not self.original_image: return
        self.zoom_factor *= 1.1 if event.delta > 0 else 1/1.1
        self.zoom_factor = max(0.1, min(5.0, self.zoom_factor))
        self.display_image()

    def start_pan(self, event): self.canvas.scan_mark(event.x, event.y)

    def pan(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)

class PrintersPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.selected_printer_id = None
        self.printers_data = []
        ttk.Label(self, text="Printer Management", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))
        self.list_frame = ttk.Frame(self)
        button_frame = ttk.Frame(self.list_frame); button_frame.pack(fill='x', pady=5, padx=5)
        ttk.Button(button_frame, text="Add New Printer", command=self.show_form_view, bootstyle="primary").pack(side='left')
        ttk.Button(button_frame, text="Edit Selected", command=self.edit_selected, bootstyle="secondary").pack(side='left', padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_printer, bootstyle="danger-outline").pack(side='left')
        ttk.Button(button_frame, text="Refresh", command=self.on_show, bootstyle="info").pack(side='right', padx=5)
        tree_container = ttk.Frame(self.list_frame); tree_container.pack(fill='both', expand=True, padx=5, pady=5)
        columns = ("Brand", "Model", "Setup Cost (₹)", "Maintenance (₹/yr)", "Lifetime (yrs)", "Power (W)", "Price/kWh (₹)", "Uptime (%)", "Buffer Factor", "Hourly Rate (₹)")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", bootstyle="primary")
        for col in columns: self.tree.heading(col, text=col, command=lambda _col=col: self.sort_column(_col, False)); self.tree.column(col, width=95, anchor="w")
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, bootstyle="round"); self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_double_click); self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.loading_label = ttk.Label(self.list_frame, text="Loading printers...")
        self.form_frame = ttk.Frame(self); self.form_title = ttk.Label(self.form_frame, font=('Montserrat', 14, 'bold'), bootstyle="info"); self.form_title.pack(anchor="w", pady=(0, 10))
        form_fields_container = ttk.Frame(self.form_frame); form_fields_container.pack(fill="x")
        self.fields = {}; labels = ["Brand", "Model", "Setup Cost (₹)", "Maintenance (₹/yr)", "Lifetime (yrs)", "Power (W)", "Price/kWh (₹)", "Uptime (%)", "Buffer Factor"]
        for i, label in enumerate(labels):
            ttk.Label(form_fields_container, text=f"{label}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[label] = ttk.StringVar(); ttk.Entry(form_fields_container, textvariable=self.fields[label], width=40).grid(row=i, column=1, padx=5, pady=6, sticky="ew")
        form_fields_container.columnconfigure(1, weight=1)
        form_button_frame = ttk.Frame(self.form_frame); form_button_frame.pack(pady=20)
        ttk.Button(form_button_frame, text="Save", command=self.save_printer, bootstyle="primary").pack(side="left", padx=10)
        ttk.Button(form_button_frame, text="Cancel", command=self.show_list_view, bootstyle="secondary").pack(side="left", padx=10)
        self.show_list_view()

    def on_show(self):
        self.show_list_view()
        self.tree.delete(*self.tree.get_children())
        self.loading_label.place(relx=0.5, rely=0.4, anchor="center")
        self.app.run_threaded_task(self.fetch_printers_thread, "Refreshing Printers...")

    def fetch_printers_thread(self):
        try:
            self.printers_data = self.app.api.get_printers()
            self.after(0, self.populate_tree)
        except Exception as e:
            print(f"Error fetching printers: {e}")
            self.after(0, self.loading_label.config, {"text": "Failed to load printers."})

    def show_list_view(self):
        self.form_frame.pack_forget()
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=0)

    def show_form_view(self, printer_id=None):
        self.list_frame.pack_forget(); self.form_frame.pack(fill="both", expand=True, padx=20, pady=10)
        if printer_id: self.form_title.config(text="Edit Printer"); self.populate_form_for_edit(printer_id)
        else: self.form_title.config(text="Add New Printer"); self.clear_form()

    def populate_form_for_edit(self, printer_id):
        self.selected_printer_id = printer_id
        printer_to_edit = next((p for p in self.printers_data if p.get("id") == printer_id), None)
        if not printer_to_edit: return messagebox.showerror("Error", "Could not find the selected printer.", parent=self)
        for key, field in {"brand": "Brand", "model": "Model", "setup_cost": "Setup Cost (₹)", "maintenance_cost": "Maintenance (₹/yr)", "lifetime_years": "Lifetime (yrs)", "power_w": "Power (W)", "price_kwh": "Price/kWh (₹)", "uptime_percent": "Uptime (%)", "buffer_factor": "Buffer Factor"}.items():
            self.fields[field].set(printer_to_edit.get(key, ""))

    def clear_form(self): self.selected_printer_id = None; [var.set("") for var in self.fields.values()]; self.fields["Uptime (%)"].set("50"); self.fields["Buffer Factor"].set("1.0")

    def edit_selected(self):
        if self.selected_printer_id: self.show_form_view(printer_id=self.selected_printer_id)
        else: messagebox.showwarning("No Selection", "Please select a printer to edit.", parent=self)

    def on_double_click(self, event):
        if self.selected_printer_id: self.show_form_view(printer_id=self.selected_printer_id)

    def populate_tree(self, sort_by='Brand', reverse=False):
        self.loading_label.place_forget()
        self.tree.delete(*self.tree.get_children())

        display_data = [(p.get("brand", ""), p.get("model", ""), p.get("setup_cost", 0), p.get("maintenance_cost", 0), p.get("lifetime_years", 0), p.get("power_w", 0), p.get("price_kwh", 0), p.get("uptime_percent", 50), p.get("buffer_factor", 1.0), f"{calculate_printer_hourly_rate(p):.2f}", p.get("id")) for p in self.printers_data]
        try:
            col_index = self.tree["columns"].index(sort_by)
            numeric_cols = ["Setup Cost (₹)", "Maintenance (₹/yr)", "Lifetime (yrs)", "Power (W)", "Price/kWh (₹)", "Uptime (%)", "Buffer Factor", "Hourly Rate (₹)"]
            display_data.sort(key=lambda x: float(x[col_index]) if sort_by in numeric_cols else str(x[col_index]).lower(), reverse=reverse)
        except (ValueError, IndexError):
            display_data.sort(key=lambda x: x[0], reverse=reverse)

        for i, item in enumerate(display_data):
            self.tree.insert('', 'end', iid=item[10], values=item[:10], tags=('oddrow' if i % 2 else 'evenrow',))

    def sort_column(self, col, reverse):
        self.populate_tree(sort_by=col, reverse=reverse)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def on_tree_select(self, event): self.selected_printer_id = self.tree.selection()[0] if self.tree.selection() else None

    def save_printer(self):
        try:
            if float(self.fields["Buffer Factor"].get()) < 1: return messagebox.showerror("Validation Error", "Buffer Factor cannot be less than 1.", parent=self)
            new_data = {"id": self.selected_printer_id or str(time.time()), "brand": self.fields["Brand"].get().strip(), "model": self.fields["Model"].get().strip(), "setup_cost": float(self.fields["Setup Cost (₹)"].get()), "maintenance_cost": float(self.fields["Maintenance (₹/yr)"].get()), "lifetime_years": int(self.fields["Lifetime (yrs)"].get()), "power_w": float(self.fields["Power (W)"].get()), "price_kwh": float(self.fields["Price/kWh (₹)"].get()), "uptime_percent": float(self.fields["Uptime (%)"].get()), "buffer_factor": float(self.fields["Buffer Factor"].get())}
            if not new_data["brand"] or not new_data["model"]: return messagebox.showerror("Validation Error", "Brand and Model are required.", parent=self)
        except (ValueError, TypeError): return messagebox.showerror("Validation Error", "Please enter valid numbers for all numeric fields.", parent=self)

        printers_to_save = self.printers_data.copy()
        if self.selected_printer_id:
            printers_to_save = [new_data if p.get("id") == self.selected_printer_id else p for p in printers_to_save]
        else:
            printers_to_save.append(new_data)

        def task():
            if self.app.api.save_printers(printers_to_save):
                messagebox.showinfo("Success", "Printer saved successfully.", parent=self)
                self.on_show()

        self.app.run_threaded_task(task, "Saving Printer...")

    def delete_printer(self):
        if not self.selected_printer_id: return messagebox.showwarning("No Selection", "Please select a printer to delete.", parent=self)

        printer_to_delete = next((p for p in self.printers_data if p["id"] == self.selected_printer_id), None)
        if printer_to_delete and messagebox.askyesno("Confirm Delete", f"Delete {printer_to_delete['brand']} {printer_to_delete['model']}?", parent=self):
            printers_to_save = [p for p in self.printers_data if p["id"] != self.selected_printer_id]

            def task():
                if self.app.api.save_printers(printers_to_save):
                    self.on_show()
                    messagebox.showinfo("Success", "Printer deleted.", parent=self)

            self.app.run_threaded_task(task, "Deleting Printer...")

class FilamentsPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.selected_filament_key = None
        self.filaments_data = {}
        ttk.Label(self, text="Filament Management", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))
        self.list_frame = ttk.Frame(self)
        button_frame = ttk.Frame(self.list_frame); button_frame.pack(fill='x', pady=5, padx=5)
        ttk.Button(button_frame, text="Add New Filament", command=self.show_form_view, bootstyle="primary").pack(side='left')
        ttk.Button(button_frame, text="Edit Selected", command=self.edit_selected, bootstyle="secondary").pack(side='left', padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_filament, bootstyle="danger-outline").pack(side='left')
        ttk.Button(button_frame, text="Refresh", command=self.on_show, bootstyle="info").pack(side='right', padx=5)
        tree_container = ttk.Frame(self.list_frame); tree_container.pack(fill='both', expand=True, padx=5, pady=5)
        columns = ("Material", "Brand", "Price (₹/kg)", "Stock (g)", "Efficiency Factor"); self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", bootstyle="primary")
        for col in columns: self.tree.heading(col, text=col, command=lambda _col=col: self.sort_column(_col, False)); self.tree.column(col, width=130, anchor="w")
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, bootstyle="round-light"); self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.on_double_click); self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.loading_label = ttk.Label(self.list_frame, text="Loading filaments...")

        self.form_frame = ttk.Frame(self); self.form_title = ttk.Label(self.form_frame, font=('Montserrat', 14, 'bold'), bootstyle="info"); self.form_title.pack(anchor="w", pady=(0, 10))
        form_fields_container = ttk.Frame(self.form_frame); form_fields_container.pack(fill="x")
        self.fields = {}; labels = ["Material", "Brand", "Price (₹/kg)", "Stock (g)", "Efficiency Factor"]
        for i, label in enumerate(labels):
            ttk.Label(form_fields_container, text=f"{label}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[label] = ttk.StringVar(); ttk.Entry(form_fields_container, textvariable=self.fields[label], width=40).grid(row=i, column=1, padx=5, pady=6, sticky="ew")
        form_fields_container.columnconfigure(1, weight=1)
        form_button_frame = ttk.Frame(self.form_frame); form_button_frame.pack(pady=20)
        ttk.Button(form_button_frame, text="Save", command=self.save_filament, bootstyle="primary").pack(side="left", padx=10)
        ttk.Button(form_button_frame, text="Cancel", command=self.show_list_view, bootstyle="secondary").pack(side="left", padx=10)
        self.show_list_view()

    def on_show(self):
        self.show_list_view()
        self.tree.delete(*self.tree.get_children())
        self.loading_label.place(relx=0.5, rely=0.4, anchor="center")
        self.app.run_threaded_task(self.fetch_filaments_thread, "Refreshing Filaments...")

    def fetch_filaments_thread(self):
        try:
            self.filaments_data = self.app.api.get_filaments()
            self.after(0, self.populate_tree)
        except Exception as e:
            print(f"Error fetching filaments: {e}")
            self.after(0, self.loading_label.config, {"text": "Failed to load filaments."})

    def show_list_view(self):
        self.form_frame.pack_forget()
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=0)

    def show_form_view(self, key=None):
        self.list_frame.pack_forget(); self.form_frame.pack(fill="both", expand=True, padx=20, pady=10)
        if key: self.form_title.config(text="Edit Filament"); self.populate_form_for_edit(key)
        else: self.form_title.config(text="Add New Filament"); self.clear_form()

    def populate_form_for_edit(self, key):
        self.selected_filament_key = key; material, brand = key
        filament_data = self.filaments_data.get(material, {}).get(brand)
        if not filament_data: return messagebox.showerror("Error", "Could not find the selected filament.", parent=self)
        self.fields["Material"].set(material); self.fields["Brand"].set(brand)
        for k, field in {"price": "Price (₹/kg)", "stock_g": "Stock (g)", "efficiency_factor": "Efficiency Factor"}.items():
            self.fields[field].set(filament_data.get(k, ""))

    def clear_form(self): self.selected_filament_key = None; [var.set("") for var in self.fields.values()]; self.fields["Efficiency Factor"].set("1.0")

    def edit_selected(self):
        if self.selected_filament_key: self.show_form_view(key=self.selected_filament_key)
        else: messagebox.showwarning("No Selection", "Please select a filament to edit.", parent=self)

    def on_double_click(self, event):
        if self.selected_filament_key: self.show_form_view(key=self.selected_filament_key)

    def populate_tree(self, sort_by='Material', reverse=False):
        self.loading_label.place_forget()
        self.tree.delete(*self.tree.get_children())
        all_filaments = [(m, b, d.get("price", 0), d.get("stock_g", 0), d.get("efficiency_factor", 1.0)) for m, bs in self.filaments_data.items() for b, d in bs.items()]
        try:
            col_index = self.tree["columns"].index(sort_by)
            numeric_cols = ["Price (₹/kg)", "Stock (g)", "Efficiency Factor"]
            all_filaments.sort(key=lambda x: float(x[col_index]) if sort_by in numeric_cols else str(x[col_index]).lower(), reverse=reverse)
        except (ValueError, IndexError): all_filaments.sort(key=lambda x: x[0], reverse=reverse)
        for i, item in enumerate(all_filaments): self.tree.insert('', 'end', values=item, tags=('oddrow' if i % 2 else 'evenrow',))

    def sort_column(self, col, reverse):
        self.populate_tree(sort_by=col, reverse=reverse)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def on_tree_select(self, event):
        if selected_items := self.tree.selection(): self.selected_filament_key = self.tree.item(selected_items[0])['values'][:2]
        else: self.selected_filament_key = None

    def save_filament(self):
        try:
            material = self.fields["Material"].get().strip().upper(); brand = self.fields["Brand"].get().strip()
            if not all([material, brand]): return messagebox.showerror("Validation Error", "Material and Brand are required.", parent=self)
            new_data = {"price": float(self.fields["Price (₹/kg)"].get()), "stock_g": float(self.fields["Stock (g)"].get()), "efficiency_factor": float(self.fields["Efficiency Factor"].get())}
        except (ValueError, TypeError): return messagebox.showerror("Validation Error", "Price, Stock, and Efficiency must be valid numbers.", parent=self)

        pricing_data_to_save = self.filaments_data.copy()
        if self.selected_filament_key and tuple(self.selected_filament_key) != (material, brand):
            old_material, old_brand = self.selected_filament_key
            if old_material in pricing_data_to_save and old_brand in pricing_data_to_save[old_material]:
                del pricing_data_to_save[old_material][old_brand]
                if not pricing_data_to_save[old_material]: del pricing_data_to_save[old_material]

        if material not in pricing_data_to_save: pricing_data_to_save[material] = {}
        pricing_data_to_save[material][brand] = new_data

        def task():
            if self.app.api.save_filaments(pricing_data_to_save):
                messagebox.showinfo("Success", f"Saved: {brand} {material}", parent=self)
                self.on_show()

        self.app.run_threaded_task(task, "Saving Filament...")

    def delete_filament(self):
        if not self.selected_filament_key: return messagebox.showwarning("No Selection", "Please select a filament to delete.", parent=self)
        material, brand = self.selected_filament_key
        if messagebox.askyesno("Confirm Delete", f"Delete {brand} {material}?", parent=self):
            pricing_data_to_save = self.filaments_data.copy()
            if material in pricing_data_to_save and brand in pricing_data_to_save[material]:
                del pricing_data_to_save[material][brand]
                if not pricing_data_to_save[material]: del pricing_data_to_save[material]

                def task():
                    if self.app.api.save_filaments(pricing_data_to_save):
                        self.on_show()
                        messagebox.showinfo("Success", f"{brand} {material} deleted.", parent=self)

                self.app.run_threaded_task(task, "Deleting Filament...")

class SettingsPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.fields = {}
        ttk.Label(self, text="Client Settings", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))
        container = ttk.Frame(self); container.pack(fill="both", expand=True, padx=10, pady=5)
        canvas = ttk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview, bootstyle="round-light")
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw"); canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self.build_form(); self.load_settings()

    def build_form(self):
        company_frame = ttk.Labelframe(self.scrollable_frame, text="Your Company Details (for Quotations)", bootstyle="info"); company_frame.pack(fill="x", expand=True, padx=10, pady=10)
        self.COMPANY_KEYS = {"COMPANY_NAME": "entry", "COMPANY_ADDRESS": "entry", "COMPANY_CONTACT": "entry", "COMPANY_LOGO_PATH": "file", "TAX_RATE_PERCENT": "entry"}
        for i, (key, field_type) in enumerate(self.COMPANY_KEYS.items()):
            ttk.Label(company_frame, text=f"{key}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[key] = ttk.StringVar(); ttk.Entry(company_frame, textvariable=self.fields[key], width=60).grid(row=i, column=1, padx=5, pady=6, sticky="ew")
            if field_type == "file": ttk.Button(company_frame, text="Browse...", command=lambda k=key: self.browse_file(k), bootstyle="secondary-outline").grid(row=i, column=2, padx=(5, 10), pady=6)
        company_frame.columnconfigure(1, weight=1)

        path_frame = ttk.Labelframe(self.scrollable_frame, text="File & Folder Paths", bootstyle="info"); path_frame.pack(fill="x", expand=True, padx=10, pady=10)
        self.PATH_KEYS = {"IMAGE_INPUT_FOLDER": "folder", "PROCESSED_IMAGES_FOLDER": "folder", "SKIPPED_IMAGES_FOLDER": "folder"}
        for i, (key, field_type) in enumerate(self.PATH_KEYS.items()):
            ttk.Label(path_frame, text=f"{key}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[key] = ttk.StringVar(); ttk.Entry(path_frame, textvariable=self.fields[key], width=60).grid(row=i, column=1, padx=5, pady=6, sticky="ew")
            if field_type == "folder": ttk.Button(path_frame, text="Browse...", command=lambda k=key: self.browse_folder(k), bootstyle="secondary-outline").grid(row=i, column=2, padx=(5, 10), pady=6)
        path_frame.columnconfigure(1, weight=1)

        other_frame = ttk.Labelframe(self.scrollable_frame, text="Other Settings", bootstyle="info"); other_frame.pack(fill="x", expand=True, padx=10, pady=10)
        self.OTHER_KEYS = {"labour_rate": "entry"}
        for i, (key, field_type) in enumerate(self.OTHER_KEYS.items()):
            ttk.Label(other_frame, text=f"{key}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[key] = ttk.StringVar(); ttk.Entry(other_frame, textvariable=self.fields[key], width=60).grid(row=i, column=1, padx=5, pady=6, sticky="ew")
        other_frame.columnconfigure(1, weight=1)

        self.ALL_KEYS = {**self.COMPANY_KEYS, **self.PATH_KEYS, **self.OTHER_KEYS}

        button_frame = ttk.Frame(self.scrollable_frame); button_frame.pack(pady=20)
        ttk.Button(button_frame, text="Save Settings", command=self.save_settings, bootstyle="primary").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Reload Current Settings", command=self.load_settings, bootstyle="secondary").pack(side="left", padx=10)

    def browse_folder(self, key):
        if folder_selected := filedialog.askdirectory(title=f"Select Folder for {key}"): self.fields[key].set(folder_selected)

    def browse_file(self, key):
        filetypes = [("Image files", "*.png *.jpg"), ("All files", "*.*")]
        if file_selected := filedialog.askopenfilename(title=f"Select File for {key}", filetypes=filetypes): self.fields[key].set(file_selected)

    def load_settings(self):
        config = load_client_config(); [var.set(config.get(key, "")) for key, var in self.fields.items()]
        self.app.get_status_box().insert(END, "⚙️ Client settings loaded.\n")

    def save_settings(self):
        save_client_config({key: var.get() for key, var in self.fields.items()})
        messagebox.showinfo("Success", "Settings have been saved.", parent=self)
        self.app.get_status_box().insert(END, "✔️ Settings saved successfully.\n")

class ServerPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        self.current_path = ""

        ttk.Label(self, text="Server Management", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))

        main_pane = ttk.PanedWindow(self, orient=HORIZONTAL)
        main_pane.pack(fill=BOTH, expand=True, padx=10, pady=10)

        browser_frame = ttk.Labelframe(main_pane, text="File Browser (Shared Folder)", bootstyle="info")

        browser_controls = ttk.Frame(browser_frame)
        browser_controls.pack(fill='x', padx=5, pady=5)
        ttk.Button(browser_controls, text="⬆️ Up", command=self.go_up_dir, bootstyle="secondary").pack(side='left')
        ttk.Button(browser_controls, text="🔄 Refresh", command=self.refresh_all, bootstyle="secondary").pack(side='left', padx=5)
        self.path_label = ttk.Label(browser_controls, text="Path: /")
        self.path_label.pack(side='left', padx=10)

        tree_container = ttk.Frame(browser_frame)
        tree_container.pack(fill='both', expand=True, padx=5, pady=(0, 5))
        self.tree = ttk.Treeview(tree_container, columns=("Name", "Type", "Size"), show="headings", bootstyle="primary")
        self.tree.heading("Name", text="Name"); self.tree.heading("Type", text="Type"); self.tree.heading("Size", text="Size")
        self.tree.column("Name", width=250); self.tree.column("Type", width=80); self.tree.column("Size", width=100, anchor='e')
        self.tree.bind("<Double-1>", self.on_item_double_click)

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, bootstyle="round-light"); self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")

        action_buttons = ttk.Frame(browser_frame)
        action_buttons.pack(fill='x', padx=5, pady=5)
        ttk.Button(action_buttons, text="Download Selected", command=self.download_selected, bootstyle="secondary").pack(side='left')
        ttk.Button(action_buttons, text="Upload to This Folder", command=self.upload_file, bootstyle="primary").pack(side='right')

        main_pane.add(browser_frame, weight=1)

        settings_frame = ttk.Labelframe(main_pane, text="Server Config (server_config.json)", bootstyle="info")
        self.settings_text = scrolledtext.ScrolledText(settings_frame, height=15, width=60,
                                                      bg="#1c246d", fg="#ffafda", relief="flat", bd=5,
                                                      font=("Consolas", 10), insertbackground="#ffafda")
        self.settings_text.pack(fill='both', expand=True, padx=5, pady=5)

        settings_buttons = ttk.Frame(settings_frame)
        settings_buttons.pack(fill='x', pady=5)
        ttk.Button(settings_buttons, text="Load from Server", command=self.load_settings, bootstyle="secondary").pack(side='left', padx=5)
        ttk.Button(settings_buttons, text="Save to Server", command=self.save_settings, bootstyle="success").pack(side='right', padx=5)

        main_pane.add(settings_frame, weight=1)

    def on_show(self):
        self.refresh_all()

    def refresh_all(self):
        self.app.run_threaded_task(self.populate_browser, "Loading Files...")
        self.load_settings()

    def populate_browser(self):
        files = self.app.api.list_server_files(self.current_path)
        self.after(0, self._update_browser_ui, files)

    def _update_browser_ui(self, files):
        for i in self.tree.get_children(): self.tree.delete(i)

        if files is None: return

        files.sort(key=lambda x: (x['type'] == 'file', x['name'].lower()))

        for item in files:
            if item['type'] == 'dir':
                self.tree.insert('', 'end', values=(f"📁 {item['name']}", "Folder", ""), tags=('dir', item['name']))
            else:
                size_mb = item['size'] / (1024 * 1024)
                size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{item['size'] / 1024:.2f} KB"
                self.tree.insert('', 'end', values=(f"📄 {item['name']}", "File", size_str), tags=('file', item['name']))

        self.path_label.config(text=f"Path: /{self.current_path}")

    def on_item_double_click(self, event):
        selected_item_id = self.tree.focus()
        if not selected_item_id: return

        tags = self.tree.item(selected_item_id, 'tags')
        if 'dir' in tags:
            dir_name = tags[1]
            self.current_path = os.path.join(self.current_path, dir_name).replace("\\", "/")
            self.app.run_threaded_task(self.populate_browser, "Loading Files...")

    def go_up_dir(self):
        if not self.current_path: return
        self.current_path = os.path.dirname(self.current_path).replace("\\", "/")
        self.app.run_threaded_task(self.populate_browser, "Loading Files...")

    def download_selected(self):
        selected_item_id = self.tree.focus()
        if not selected_item_id:
            messagebox.showwarning("No Selection", "Please select a file to download.", parent=self)
            return

        tags = self.tree.item(selected_item_id, 'tags')
        if 'file' not in tags:
            messagebox.showwarning("Invalid Selection", "Please select a file, not a folder.", parent=self)
            return

        filename = tags[1]
        server_filepath = os.path.join(self.current_path, filename).replace("\\", "/")

        local_save_path = filedialog.asksaveasfilename(initialfile=filename, parent=self)
        if not local_save_path: return

        def task():
            success = self.app.api.download_server_file(server_filepath, local_save_path)
            if success:
                messagebox.showinfo("Success", f"File downloaded successfully to:\n{local_save_path}", parent=self)
        self.app.run_threaded_task(task, "Downloading...")

    def upload_file(self):
        local_path = filedialog.askopenfilename(parent=self)
        if not local_path: return

        def task():
            result = self.app.api.upload_file_to_server(local_path, self.current_path)
            self.after(0, self._on_upload_complete, result)

        self.app.run_threaded_task(task, "Uploading...")

    def _on_upload_complete(self, result):
        if result and result.get("status") == "success":
            messagebox.showinfo("Success", result.get("message", "File uploaded successfully!"), parent=self)
            self.app.run_threaded_task(self.populate_browser, "Refreshing Files...")
            if "template path updated" in result.get("message", ""):
                self.load_settings()

    def load_settings(self):
        self.app.run_threaded_task(self._load_settings_task, "Loading Settings...")

    def _load_settings_task(self):
        settings = self.app.api.get_server_settings()
        self.after(0, self._update_settings_ui, settings)

    def _update_settings_ui(self, settings):
        if settings:
            self.settings_text.delete('1.0', END)
            self.settings_text.insert('1.0', json.dumps(settings, indent=4))

    def save_settings(self):
        try:
            settings_str = self.settings_text.get('1.0', END)
            data_to_save = json.loads(settings_str)
        except json.JSONDecodeError:
            messagebox.showerror("JSON Error", "The settings text is not valid JSON. Please correct it and try again.", parent=self)
            return

        if messagebox.askyesno("Confirm Save", "Are you sure you want to overwrite the server's configuration file? This could break the server if done incorrectly.", parent=self):
            def task():
                result = self.app.api.save_server_settings(data_to_save)
                if result and result.get('status') == 'success':
                    messagebox.showinfo("Success", "Server settings saved and reloaded successfully.", parent=self)
            self.app.run_threaded_task(task, "Saving Settings...")

class UserManagementPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app

        ttk.Label(self, text="User Management", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))

        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True, padx=10)

        # Centering vertically
        ttk.Frame(container).pack(fill="y", expand=True)

        form_frame = ttk.Labelframe(container, text="Create New User", bootstyle="info")
        form_frame.pack(fill="x", expand=False)

        ttk.Label(form_frame, text="Username:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.username = ttk.StringVar()
        ttk.Entry(form_frame, textvariable=self.username, width=40).grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(form_frame, text="Email:").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.email = ttk.StringVar()
        ttk.Entry(form_frame, textvariable=self.email, width=40).grid(row=1, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(form_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self.password = ttk.StringVar()
        ttk.Entry(form_frame, textvariable=self.password, show="*", width=40).grid(row=2, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(form_frame, text="Role:").grid(row=3, column=0, sticky="w", padx=10, pady=6)
        self.role = ttk.StringVar(value='user')
        role_dropdown = ttk.Combobox(form_frame, textvariable=self.role, state="readonly", values=['user', 'admin'])
        role_dropdown.grid(row=3, column=1, padx=10, pady=6, sticky="ew")

        form_frame.columnconfigure(1, weight=1)

        ttk.Button(container, text="Create User", command=self.create_user, bootstyle="primary").pack(pady=20)

        # Centering vertically
        ttk.Frame(container).pack(fill="y", expand=True)

    def on_show(self):
        self.username.set(""); self.email.set(""); self.password.set(""); self.role.set("user")

    def create_user(self):
        user = self.username.get(); email = self.email.get(); pwd = self.password.get(); role = self.role.get()
        if not all([user, email, pwd, role]):
            messagebox.showerror("Input Error", "Username, Email, Password, and Role are required.", parent=self); return

        def task():
            result = self.app.api.create_user(user, email, pwd, role)
            if result:
                messagebox.showinfo("Success", result.get("message", "User created successfully!"), parent=self)
                self.on_show()

        self.app.run_threaded_task(task, "Creating User...")

class ProfilePage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app
        self.profile_photo = None

        ttk.Label(self, text="User Profile", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=20, pady=(10,5))

        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        details_frame = ttk.Labelframe(main_frame, text="Profile Details", bootstyle="info", padding=15)
        details_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        details_frame.columnconfigure(1, weight=1)
        details_frame.rowconfigure(5, weight=1)

        self.username_var = ttk.StringVar()
        self.email_var = ttk.StringVar()
        self.phone_var = ttk.StringVar()
        self.dob_var = ttk.StringVar()

        ttk.Label(details_frame, text="Username:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(details_frame, textvariable=self.username_var, width=40).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(details_frame, text="Email:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(details_frame, textvariable=self.email_var, state="readonly", width=40).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(details_frame, text="Phone Number:").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(details_frame, textvariable=self.phone_var, width=40).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(details_frame, text="Date of Birth (YYYY-MM-DD):").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(details_frame, textvariable=self.dob_var, width=40).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Button(details_frame, text="Save Profile Changes", command=self.save_profile, bootstyle="primary").grid(row=4, column=0, columnspan=2, pady=(20, 5))

        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")

        pic_frame = ttk.Labelframe(right_frame, text="Profile Picture", bootstyle="info", padding=15)
        pic_frame.pack(fill="x", pady=(0, 20))

        self.pic_label = ttk.Label(pic_frame, text="No Image", width=20, anchor=CENTER)
        self.pic_label.pack(pady=5)
        ttk.Button(pic_frame, text="Upload New Picture", command=self.upload_picture, bootstyle="secondary").pack(pady=(5,0))

        pass_frame = ttk.Labelframe(right_frame, text="Change Password", bootstyle="info", padding=15)
        pass_frame.pack(fill="x")
        pass_frame.columnconfigure(1, weight=1)
        pass_frame.rowconfigure(4, weight=1)

        self.current_pass_var = ttk.StringVar()
        self.new_pass1_var = ttk.StringVar()
        self.new_pass2_var = ttk.StringVar()

        ttk.Label(pass_frame, text="Current Password:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(pass_frame, textvariable=self.current_pass_var, show="*", width=30).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(pass_frame, text="New Password:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(pass_frame, textvariable=self.new_pass1_var, show="*", width=30).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(pass_frame, text="Confirm New Password:").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(pass_frame, textvariable=self.new_pass2_var, show="*", width=30).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Button(pass_frame, text="Change Password", command=self.change_password, bootstyle="info").grid(row=3, column=0, columnspan=2, pady=(20, 5))

        ttk.Button(main_frame, text="Logout", command=self.app.on_logout, bootstyle="danger").grid(row=1, column=0, columnspan=2, pady=(30, 10), sticky="s")
        main_frame.rowconfigure(1, weight=1)

    def on_show(self):
        # 1. Try to load from cache for an instant display
        cached_data = self.app.get_cached_data('profile')
        if cached_data:
            self.populate_form(cached_data)
            if cached_data.get('profile_picture_url'):
                # Also try to load image from cache if possible (advanced)
                # For now, we'll just show text and refresh image in background
                self.pic_label.config(image='', text="Loading...")
        else:
            self.clear_form() # Show "Loading..." state if no cache

        # 2. Start a silent background refresh, no matter what
        threading.Thread(target=self._refresh_profile_data, daemon=True).start()

    def _refresh_profile_data(self):
        # This runs in a background thread without a global loader.
        profile_data = self.app.api.get_profile()
        if profile_data:
            # Update the cache with fresh data
            self.app.cache_data('profile', profile_data)

            # Schedule the form population on the main thread
            self.after(0, self.populate_form, profile_data)

            # If there's an image URL, process it
            if profile_data.get('profile_picture_url'):
                try:
                    # Fetch and process the image in this same background thread
                    headers = self.app.api._get_auth_header()
                    if not headers: return
                    response = requests.get(profile_data['profile_picture_url'], stream=True, headers=headers)
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content))
                    resized_image = ImageOps.fit(image, (150, 150), Image.Resampling.LANCZOS)

                    # Now, schedule the final UI update on the main thread
                    self.after(0, self._update_image_ui, resized_image)
                except Exception as e:
                    print(f"Failed to load profile page image: {e}")
                    # Schedule an error state update on the main thread
                    self.after(0, self._update_image_ui, None)

    def populate_form(self, data):
        # This runs on the main thread.
        self.username_var.set(data.get('username', ''))
        self.email_var.set(data.get('email', ''))
        self.phone_var.set(data.get('phone_number', ''))
        self.dob_var.set(data.get('dob', ''))

    def _update_image_ui(self, pil_image):
        # This runs on the main thread to safely interact with Tkinter.
        if pil_image:
            try:
                # This is the potentially slow part that MUST be on the main thread
                self.profile_photo = ImageTk.PhotoImage(pil_image)
                self.pic_label.config(image=self.profile_photo, text="")
            except Exception as e:
                print(f"Failed to create Tkinter image for profile page: {e}")
                self.pic_label.config(image='', text="Load Failed")
        else:
            self.pic_label.config(image='', text="Load Failed")

    def clear_form(self):
        # This sets the initial state
        self.username_var.set("Loading...")
        self.email_var.set("Loading...")
        self.phone_var.set("Loading...")
        self.dob_var.set("Loading...")
        self.current_pass_var.set(""); self.new_pass1_var.set(""); self.new_pass2_var.set("")
        self.pic_label.config(image='', text="Loading...")

    def save_profile(self):
        data_to_save = {
            "username": self.username_var.get(),
            "phone_number": self.phone_var.get(),
            "dob": self.dob_var.get()
        }
        def task():
            result = self.app.api.update_profile(data_to_save)
            if result:
                messagebox.showinfo("Success", "Profile updated successfully.", parent=self)
                self.app.update_profile_widget(force_refresh=True)
        self.app.run_threaded_task(task, "Saving Profile...")

    def upload_picture(self):
        file_path = filedialog.askopenfilename(title="Select Profile Picture", filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if not file_path: return

        def task():
            result = self.app.api.upload_profile_picture(file_path)
            if result:
                messagebox.showinfo("Success", "Profile picture uploaded. It will update shortly.", parent=self)
                self.on_show()
                self.app.update_profile_widget(force_refresh=True)
        self.app.run_threaded_task(task, "Uploading Picture...")

    def change_password(self):
        current_pass = self.current_pass_var.get()
        new_pass1 = self.new_pass1_var.get()
        new_pass2 = self.new_pass2_var.get()

        if not all([current_pass, new_pass1, new_pass2]):
            messagebox.showerror("Input Error", "All password fields are required.", parent=self)
            return
        if new_pass1 != new_pass2:
            messagebox.showerror("Input Error", "New passwords do not match.", parent=self)
            return

        def task():
            result = self.app.api.change_password(current_pass, new_pass1)
            if result:
                messagebox.showinfo("Success", "Password changed successfully.", parent=self)
                self.current_pass_var.set(""); self.new_pass1_var.set(""); self.new_pass2_var.set("")

        self.app.run_threaded_task(task, "Changing Password...")

class VerificationPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.vars = {}; self.printers = []; self.printer_ids = {}
        main_pane = ttk.PanedWindow(self, orient=HORIZONTAL); main_pane.pack(fill=BOTH, expand=True, padx=10, pady=10)
        image_frame = ttk.Labelframe(main_pane, text="Print Summary Image", bootstyle="info")
        self.canvas = ImageCanvas(image_frame); self.canvas.pack(fill="both", expand=True, padx=5, pady=5); main_pane.add(image_frame, weight=1)
        form_scroll_frame = ttk.Frame(main_pane)
        self.form_frame = ttk.Labelframe(form_scroll_frame, text="Verify OCR Data", bootstyle="info"); self.form_frame.pack(fill="both", expand=True); main_pane.add(form_scroll_frame, weight=1)
        self.build_widgets()
        self.is_active = False

    def load_data(self, image_path, ocr_data):
        self.is_active = True
        self.original_image_path = image_path; self.image_timestamp = datetime.fromtimestamp(os.path.getmtime(image_path)).isoformat(); self.ocr_data = ocr_data
        self.canvas.load_image_from_path(image_path)
        self.app.run_threaded_task(self._load_dropdown_data, "Loading Data...")

    def _load_dropdown_data(self):
        """Fetch printer and filament data in a background thread."""
        printers = self.app.api.get_printers()
        pricing_data = self.app.api.get_filaments()
        self.after(0, self._on_data_loaded, printers, pricing_data)

    def _on_data_loaded(self, printers, pricing_data):
        """Populate the form on the main thread once data is loaded."""
        self.printers = printers
        self.pricing_data = pricing_data
        self.populate_form()
        self.calculate_cogs()

    def build_widgets(self):
        for widget in self.form_frame.winfo_children(): widget.destroy()
        row_counter = 0
        fields_to_build = ["Filename", "Date", "Printer", "Material", "Brand", "Filament Cost (₹/kg)", "Filament (g)", "Time (e.g. 7h 30m)", "Labour Time (min)", "Labour Rate (₹/hr)"]
        for label_text in fields_to_build:
            ttk.Label(self.form_frame, text=f"{label_text}:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
            self.vars[label_text] = ttk.StringVar()
            if "Printer" in label_text:
                p_frame = ttk.Frame(self.form_frame)
                self.printer_dropdown = ttk.Combobox(p_frame, textvariable=self.vars["Printer"], state="readonly", width=35); self.printer_dropdown.pack(side="left", fill="x", expand=True)
                ttk.Button(p_frame, text="Add New...", command=self.add_new_printer, bootstyle="outline-secondary").pack(side="left", padx=(5,0))
                p_frame.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10)
            elif "Material" in label_text:
                self.material_dropdown = ttk.Combobox(self.form_frame, textvariable=self.vars["Material"], state="readonly"); self.material_dropdown.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10)
            elif "Brand" in label_text:
                b_frame = ttk.Frame(self.form_frame)
                self.brand_dropdown = ttk.Combobox(b_frame, textvariable=self.vars["Brand"], state="readonly"); self.brand_dropdown.pack(side="left", fill="x", expand=True)
                ttk.Button(b_frame, text="Add New...", command=self.add_new_filament, bootstyle="outline-secondary").pack(side="left", padx=(5,0))
                b_frame.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10)
            else:
                entry = ttk.Entry(self.form_frame, textvariable=self.vars[label_text])
                if "Filament Cost" in label_text:
                    entry.config(state="readonly")
                entry.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10)
            row_counter += 1

        self.form_frame.grid_columnconfigure(1, weight=1)
        ttk.Separator(self.form_frame).grid(row=row_counter, column=0, columnspan=2, sticky="ew", pady=15); row_counter += 1
        ttk.Label(self.form_frame, text="User COGS (₹):", font="-weight bold").grid(row=row_counter, column=0, sticky="w", padx=10)
        self.user_cogs_label = ttk.Label(self.form_frame, text="0.00", font="-weight bold"); self.user_cogs_label.grid(row=row_counter, column=1, sticky="w", padx=10); row_counter += 1
        btn_frame = ttk.Frame(self.form_frame); btn_frame.grid(row=row_counter, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Confirm", command=self.confirm, bootstyle="primary").pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Cancel (Redo)", command=self.cancel, bootstyle="secondary").pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Skip", command=self.skip, bootstyle="secondary").pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Stop Monitoring", command=self.stop_monitoring, bootstyle="danger-outline").pack(side="right", padx=20)

        for var in self.vars.values(): var.trace_add("write", self.calculate_cogs)
        self.material_dropdown.bind("<<ComboboxSelected>>", self.on_material_select); self.brand_dropdown.bind("<<ComboboxSelected>>", self.on_brand_select)

    def stop_monitoring(self):
        if messagebox.askyesno("Confirm Stop", "This will stop the monitoring bot.\nThe current file will not be processed and will remain in the input folder.\n\nAre you sure you want to stop?", parent=self):
            self.is_active = False
            self.app.on_stop()
            self.app.show_page("Monitor")

    def add_new_printer(self):
        dialog = AddNewPrinterDialog(self, self.app)
        self.wait_window(dialog)
        if hasattr(dialog, 'result') and dialog.result:
            self.app.run_threaded_task(self._load_dropdown_data, "Refreshing Data...")
            # We can't set the value immediately, it will be set when the data reloads.
            # Consider passing the new printer name to the reload function to select it.

    def add_new_filament(self):
        dialog = AddNewFilamentDialog(self, self.app)
        self.wait_window(dialog)
        if hasattr(dialog, 'result') and dialog.result:
            self.app.run_threaded_task(self._load_dropdown_data, "Refreshing Data...")
            # Same as above, we can't set it immediately.

    def populate_form(self):
        printer_names = [f"{p['brand']} {p['model']}" for p in self.printers]
        self.printer_ids = {f"{p['brand']} {p['model']}": p['id'] for p in self.printers}
        self.printer_dropdown['values'] = sorted(printer_names)

        material_options = sorted(list(self.pricing_data.keys()))
        self.material_dropdown['values'] = material_options

        client_config = load_client_config()
        self.vars["Filename"].set(os.path.splitext(os.path.basename(self.original_image_path))[0])
        self.vars["Date"].set(datetime.fromisoformat(self.image_timestamp).strftime("%Y-%m-%d"))

        detected_printer_name = next((name for name, pid in self.printer_ids.items() if pid == self.ocr_data.get("detected_printer_id")), None)
        if detected_printer_name:
            self.vars["Printer"].set(detected_printer_name)
        elif self.printer_dropdown['values']:
            self.vars["Printer"].set(self.printer_dropdown['values'][0])

        detected_material = self.ocr_data.get("material", "")
        if detected_material and detected_material.upper() in self.material_dropdown['values']:
            self.vars["Material"].set(detected_material.upper())
        elif self.material_dropdown['values']:
            self.vars["Material"].set(self.material_dropdown['values'][0])

        self.vars["Filament (g)"].set(self.ocr_data.get("filament", 0.0)); self.vars["Time (e.g. 7h 30m)"].set(self.ocr_data.get("time_str", "0h 0m"))
        self.vars["Labour Time (min)"].set("30"); self.vars["Labour Rate (₹/hr)"].set(client_config.get("labour_rate", 100)); self.update_brands_list()

    def calculate_cogs(self, *args):
        try:
            form_data = {label: var.get() for label, var in self.vars.items()}
            printer_id = self.printer_ids.get(form_data["Printer"])
            printer_data = next((p for p in self.printers if p["id"] == printer_id), None)
            filament_data = self.pricing_data.get(form_data["Material"], {}).get(form_data["Brand"], {})
            if not printer_data or not filament_data: return
            cogs = calculate_cogs_values(form_data, printer_data, filament_data)
            self.user_cogs_label.config(text=f"{cogs['user_cogs']:.2f}")
        except (ValueError, TypeError, KeyError): self.user_cogs_label.config(text="Error")

    def update_brands_list(self, brand_to_select=None):
        material = self.vars["Material"].get(); brand_options = sorted(list(self.pricing_data.get(material, {}).keys()))
        self.brand_dropdown['values'] = brand_options
        if brand_to_select and brand_to_select in brand_options: self.vars["Brand"].set(brand_to_select)
        elif brand_options: self.vars["Brand"].set(brand_options[0])
        else: self.vars["Brand"].set("")
        self.update_cost_from_brand()

    def update_cost_from_brand(self, *args):
        brand, material = self.vars["Brand"].get(), self.vars["Material"].get()
        cost = self.pricing_data.get(material, {}).get(brand, {}).get("price", 0) if brand and material else "0"
        self.vars["Filament Cost (₹/kg)"].set(str(cost)); self.calculate_cogs()

    def on_material_select(self, event): self.update_brands_list()
    def on_brand_select(self, event): self.update_cost_from_brand()

    def confirm(self):
        if not self.vars["Printer"].get(): return messagebox.showerror("Error", "Please select a printer.", parent=self)
        result = {label: var.get() for label, var in self.vars.items()}
        result["printer_id"] = self.printer_ids[self.vars["Printer"].get()]; result["timestamp"] = self.image_timestamp
        self.is_active = False
        self.app.on_verification_complete(self.original_image_path, result)

    def cancel(self):
        self.is_active = False
        self.app.on_verification_complete(self.original_image_path, None)

    def skip(self):
        self.is_active = False
        self.app.on_verification_complete(self.original_image_path, "skip")

class AddNewPrinterDialog(Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title("Add New Printer")
        self.transient(parent); self.grab_set()

        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        self.fields = {}
        labels = ["Brand", "Model", "Setup Cost (₹)", "Maintenance (₹/yr)", "Lifetime (yrs)", "Power (W)", "Price/kWh (₹)", "Uptime (%)", "Buffer Factor"]
        for i, label in enumerate(labels):
            ttk.Label(container, text=f"{label}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[label] = ttk.StringVar()
            ttk.Entry(container, textvariable=self.fields[label], width=30).grid(row=i, column=1, padx=5, pady=6, sticky="ew")

        self.fields["Uptime (%)"].set("50")
        self.fields["Buffer Factor"].set("1.0")

        button_frame = ttk.Frame(container); button_frame.grid(row=len(labels), column=0, columnspan=2, pady=20)
        self.save_button = ttk.Button(button_frame, text="Save", command=self.save, bootstyle="primary"); self.save_button.pack(side="left", padx=10)
        ttk.Button(button_frame, text="Cancel", command=self.destroy, bootstyle="secondary").pack(side="left", padx=10)

    def save(self):
        try:
            if float(self.fields["Buffer Factor"].get()) < 1:
                messagebox.showerror("Validation Error", "Buffer Factor cannot be less than 1.", parent=self)
                return
            self.new_data = {
                "id": str(time.time()),
                "brand": self.fields["Brand"].get().strip(),
                "model": self.fields["Model"].get().strip(),
                "setup_cost": float(self.fields["Setup Cost (₹)"].get()),
                "maintenance_cost": float(self.fields["Maintenance (₹/yr)"].get()),
                "lifetime_years": int(self.fields["Lifetime (yrs)"].get()),
                "power_w": float(self.fields["Power (W)"].get()),
                "price_kwh": float(self.fields["Price/kWh (₹)"].get()),
                "uptime_percent": float(self.fields["Uptime (%)"].get()),
                "buffer_factor": float(self.fields["Buffer Factor"].get())
            }
            if not self.new_data["brand"] or not self.new_data["model"]:
                messagebox.showerror("Validation Error", "Brand and Model are required.", parent=self)
                return
        except (ValueError, TypeError):
            messagebox.showerror("Validation Error", "Please enter valid numbers for all numeric fields.", parent=self)
            return

        self.save_button.config(state="disabled")
        threading.Thread(target=self._save_task, daemon=True).start()

    def _save_task(self):
        """Runs on a background thread to avoid freezing the UI."""
        try:
            printers = self.app.api.get_printers()
            printers.append(self.new_data)
            success = self.app.api.save_printers(printers)
            self.after(0, self._on_save_complete, success)
        except Exception as e:
            print(f"Error saving printer: {e}")
            self.after(0, self._on_save_complete, False)

    def _on_save_complete(self, success):
        """Runs on the main UI thread to process the result."""
        self.save_button.config(state="normal")
        if success:
            self.result = f"{self.new_data['brand']} {self.new_data['model']}"
            self.destroy()
        else:
            messagebox.showerror("API Error", "Failed to save the new printer.", parent=self)

class AddNewFilamentDialog(Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title("Add New Filament")
        self.transient(parent); self.grab_set()

        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)

        self.fields = {}
        labels = ["Material", "Brand", "Price (₹/kg)", "Stock (g)", "Efficiency Factor"]
        for i, label in enumerate(labels):
            ttk.Label(container, text=f"{label}:").grid(row=i, column=0, padx=5, pady=6, sticky="w")
            self.fields[label] = ttk.StringVar()
            ttk.Entry(container, textvariable=self.fields[label], width=30).grid(row=i, column=1, padx=5, pady=6, sticky="ew")

        self.fields["Efficiency Factor"].set("1.0")

        button_frame = ttk.Frame(container); button_frame.grid(row=len(labels), column=0, columnspan=2, pady=20)
        self.save_button = ttk.Button(button_frame, text="Save", command=self.save, bootstyle="primary"); self.save_button.pack(side="left", padx=10)
        ttk.Button(button_frame, text="Cancel", command=self.destroy, bootstyle="secondary").pack(side="left", padx=10)

    def save(self):
        try:
            self.material = self.fields["Material"].get().strip().upper()
            self.brand = self.fields["Brand"].get().strip()
            if not all([self.material, self.brand]):
                messagebox.showerror("Validation Error", "Material and Brand are required.", parent=self)
                return
            self.new_data = {
                "price": float(self.fields["Price (₹/kg)"].get()),
                "stock_g": float(self.fields["Stock (g)"].get()),
                "efficiency_factor": float(self.fields["Efficiency Factor"].get())
            }
        except (ValueError, TypeError):
            messagebox.showerror("Validation Error", "Price, Stock, and Efficiency must be valid numbers.", parent=self)
            return

        self.save_button.config(state="disabled")
        threading.Thread(target=self._save_task, daemon=True).start()

    def _save_task(self):
        try:
            filaments = self.app.api.get_filaments()
            if self.material not in filaments:
                filaments[self.material] = {}
            filaments[self.material][self.brand] = self.new_data
            success = self.app.api.save_filaments(filaments)
            self.after(0, self._on_save_complete, success)
        except Exception as e:
            print(f"Error saving filament: {e}")
            self.after(0, self._on_save_complete, False)

    def _on_save_complete(self, success):
        self.save_button.config(state="normal")
        if success:
            self.result = (self.material, self.brand)
            self.destroy()
        else:
            messagebox.showerror("API Error", "Failed to save the new filament.", parent=self)

class QuotationPage(Page):
    def __init__(self, master, app, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.app = app; self.vars = {}; self.part_vars = {}; self.printers = []; self.printer_ids = {}; self.pricing_data = {}; self.current_part_cogs = 0.0
        ttk.Label(self, text="Quotation Generator", font=('Montserrat', 16, 'bold'), bootstyle="primary").pack(anchor="w", padx=10, pady=(5,10))
        main_pane = ttk.PanedWindow(self, orient=HORIZONTAL); main_pane.pack(fill=BOTH, expand=True, padx=10, pady=10)
        left_frame = ttk.Frame(main_pane)
        customer_frame = ttk.Labelframe(left_frame, text="Customer Details", bootstyle="info"); customer_frame.pack(fill="x", pady=(0, 10))
        for i, label in enumerate(["Customer Name", "Company Name"]):
            ttk.Label(customer_frame, text=f"{label}:").grid(row=i, column=0, sticky="w", padx=10, pady=5)
            self.vars[label] = ttk.StringVar(); ttk.Entry(customer_frame, textvariable=self.vars[label], width=40).grid(row=i, column=1, sticky="ew", padx=10, pady=5)
        customer_frame.columnconfigure(1, weight=1)
        load_frame = ttk.Labelframe(left_frame, text="Load Data for a New Part", bootstyle="info"); load_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(load_frame, text="Load from Image (OCR)", command=self.load_from_image, bootstyle="secondary").pack(side="left", padx=10, pady=5)
        ttk.Button(load_frame, text="Load from Logs", command=self.load_from_logs, bootstyle="secondary").pack(side="left", padx=10, pady=5)
        self.build_add_part_widgets(left_frame); main_pane.add(left_frame, weight=1)
        right_pane = ttk.PanedWindow(main_pane, orient=VERTICAL)
        items_frame = ttk.Labelframe(right_pane, text="Quotation Items", bootstyle="info")
        tree_container = ttk.Frame(items_frame); tree_container.pack(fill='both', expand=True, padx=5, pady=5)
        columns = ("Part Name", "Material", "COGS (₹)"); self.parts_tree = ttk.Treeview(tree_container, columns=columns, show="headings", bootstyle="primary")
        for col in columns: self.parts_tree.heading(col, text=col)
        self.parts_tree.column("Part Name", width=200); self.parts_tree.column("Material", width=150); self.parts_tree.column("COGS (₹)", width=100, anchor="e")
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.parts_tree.yview, bootstyle="round-light"); self.parts_tree.configure(yscroll=scrollbar.set)
        self.parts_tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        parts_btn_frame = ttk.Frame(items_frame); parts_btn_frame.pack(pady=5)
        ttk.Button(parts_btn_frame, text="Remove Selected", command=self.remove_part, bootstyle="danger-outline").pack(side="left", padx=5)
        ttk.Button(parts_btn_frame, text="Clear All", command=self.clear_all_parts, bootstyle="secondary-outline").pack(side="left", padx=5)
        right_pane.add(items_frame, weight=1)
        bottom_right_frame = ttk.Frame(right_pane)
        pricing_frame = ttk.Labelframe(bottom_right_frame, text="Pricing", bootstyle="info"); pricing_frame.pack(fill="x", padx=5)
        self.build_pricing_widgets(pricing_frame)
        ttk.Button(bottom_right_frame, text="Generate Quotation PDF", command=self.generate_pdf, bootstyle="primary").pack(pady=20)
        right_pane.add(bottom_right_frame, weight=1); main_pane.add(right_pane, weight=1)
    def build_add_part_widgets(self, parent):
        calc_frame = ttk.Labelframe(parent, text="Add Part Details", bootstyle="info"); calc_frame.pack(fill="x")
        row_counter = 0
        ttk.Label(calc_frame, text="Part Name:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
        self.part_vars["Part Name"] = ttk.StringVar(); ttk.Entry(calc_frame, textvariable=self.part_vars["Part Name"]).grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10); row_counter += 1
        ttk.Label(calc_frame, text="Printer Used:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
        self.part_vars["Printer"] = ttk.StringVar(); self.printer_dropdown = ttk.Combobox(calc_frame, textvariable=self.part_vars["Printer"], state="readonly", width=35); self.printer_dropdown.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10); row_counter += 1
        ttk.Label(calc_frame, text="Material:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
        self.part_vars["Material"] = ttk.StringVar(); self.material_dropdown = ttk.Combobox(calc_frame, textvariable=self.part_vars["Material"], state="readonly"); self.material_dropdown.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10); row_counter += 1
        ttk.Label(calc_frame, text="Filament Brand:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
        self.part_vars["Brand"] = ttk.StringVar(); self.brand_dropdown = ttk.Combobox(calc_frame, textvariable=self.part_vars["Brand"], state="readonly"); self.brand_dropdown.grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10); row_counter += 1
        for label in ["Filament (g)", "Time (e.g. 7h 30m)", "Labour Time (min)"]:
            ttk.Label(calc_frame, text=f"{label}:").grid(row=row_counter, column=0, sticky="w", pady=5, padx=10)
            self.part_vars[label] = ttk.StringVar(value="0"); ttk.Entry(calc_frame, textvariable=self.part_vars[label]).grid(row=row_counter, column=1, sticky="ew", pady=5, padx=10); row_counter += 1
        calc_frame.grid_columnconfigure(1, weight=1)
        ttk.Button(calc_frame, text="Add Part to Quote", command=self.add_part, bootstyle="success").grid(row=row_counter, column=0, columnspan=2, pady=10)
        for key in ["Printer", "Material", "Brand", "Filament (g)", "Time (e.g. 7h 30m)", "Labour Time (min)"]: self.part_vars[key].trace_add("write", self.calculate_part_cogs)
        self.printer_dropdown.bind("<<ComboboxSelected>>", self.calculate_part_cogs); self.material_dropdown.bind("<<ComboboxSelected>>", self.on_material_select); self.brand_dropdown.bind("<<ComboboxSelected>>", self.calculate_part_cogs)
    def build_pricing_widgets(self, parent):
        ttk.Label(parent, text="Total COGS:", font="-weight bold").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.cogs_label = ttk.Label(parent, text="₹ 0.00", font="-weight bold"); self.cogs_label.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        ttk.Separator(parent).grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(parent, text="Select Margin:", font="-weight bold").grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=5)
        self.margin_var = ttk.IntVar(value=50); self.custom_margin_var = ttk.StringVar(value="90"); self.custom_margin_var.trace_add("write", self.on_margin_select)
        margin_options_frame = ttk.Frame(parent); margin_options_frame.grid(row=3, column=0, columnspan=3, sticky="w")
        for i, (text, val) in enumerate([("50%", 50), ("60%", 60), ("70%", 70), ("80%", 80)]): ttk.Radiobutton(margin_options_frame, text=text, variable=self.margin_var, value=val, command=self.on_margin_select, bootstyle="primary-toolbutton").pack(side="left", padx=5)
        self.custom_rb = ttk.Radiobutton(margin_options_frame, text="Custom:", variable=self.margin_var, value=999, command=self.on_margin_select, bootstyle="primary-toolbutton"); self.custom_rb.pack(side="left", padx=(10, 0))
        self.custom_margin_entry = ttk.Entry(margin_options_frame, textvariable=self.custom_margin_var, width=5, state="disabled"); self.custom_margin_entry.pack(side="left", padx=(0, 2))
        ttk.Label(margin_options_frame, text="%").pack(side="left")
        ttk.Separator(parent).grid(row=4, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(parent, text="Subtotal:").grid(row=5, column=0, sticky="e", padx=10, pady=2)
        self.subtotal_label = ttk.Label(parent, text="₹ 0.00"); self.subtotal_label.grid(row=5, column=1, sticky="w", padx=10, pady=2)
        ttk.Label(parent, text="Tax:").grid(row=6, column=0, sticky="e", padx=10, pady=2)
        self.tax_label = ttk.Label(parent, text="₹ 0.00"); self.tax_label.grid(row=6, column=1, sticky="w", padx=10, pady=2)
        ttk.Label(parent, text="Total Price:", font="-size 12 -weight bold").grid(row=7, column=0, sticky="e", padx=10, pady=(5,10))
        self.total_price_label = ttk.Label(parent, text="₹ 0.00", font="-size 12 -weight bold", bootstyle="success"); self.total_price_label.grid(row=7, column=1, sticky="w", padx=10, pady=(5,10))
        parent.columnconfigure(1, weight=1)
    def on_show(self):
        self.app.run_threaded_task(self._load_page_data, "Loading Quotation Data...")

    def _load_page_data(self):
        client_config = load_client_config()
        pricing_data = self.app.api.get_filaments()
        printers = self.app.api.get_printers()
        self.after(0, self._on_page_data_loaded, client_config, pricing_data, printers)

    def _on_page_data_loaded(self, client_config, pricing_data, printers):
        self.part_vars["Labour Rate (₹/hr)"] = ttk.StringVar(value=client_config.get("labour_rate", 100))
        self.pricing_data = pricing_data
        self.printers = printers
        printer_names = [f"{p['brand']} {p['model']}" for p in self.printers]
        self.printer_ids = {f"{p['brand']} {p['model']}": p['id'] for p in self.printers}
        self.printer_dropdown['values'] = sorted(printer_names)
        if printer_names: self.part_vars["Printer"].set(sorted(printer_names)[0])
        material_options = sorted(list(self.pricing_data.keys())); self.material_dropdown['values'] = material_options
        if material_options: self.part_vars["Material"].set(material_options[0])
        self.update_brands_list(); self.calculate_part_cogs()

    def load_from_image(self):
        if not (image_path := filedialog.askopenfilename(title="Select Print Summary Image", filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")])): return

        def task():
            ocr_data = self.app.api.upload_for_ocr(image_path)
            self.after(0, self._process_ocr_result, ocr_data, image_path)

        self.app.run_threaded_task(task, "Performing OCR...")

    def _process_ocr_result(self, ocr_data, image_path):
        if ocr_data:
            self.part_vars["Part Name"].set(os.path.splitext(os.path.basename(image_path))[0]); self.populate_form_with_data(ocr_data)
            self.app.get_status_box().insert(END, "✔️ OCR data loaded. Review and add part.\n")
        else: self.app.get_status_box().insert(END, f"❌ Failed to get OCR data for {os.path.basename(image_path)}.\n")

    def load_from_logs(self):
        self.app.run_threaded_task(self._load_logs_task, "Loading Logs...")

    def _load_logs_task(self):
        logs = self.app.api.get_logs()
        self.after(0, self._on_logs_loaded, logs)

    def _on_logs_loaded(self, logs):
        if not logs: return messagebox.showinfo("No Logs", "No processed logs found to load from.", parent=self)
        dialog = LogSelectionDialog(self, logs); self.wait_window(dialog)
        if dialog.result:
            self.part_vars["Part Name"].set(dialog.result['filename']); self.populate_form_with_data(dialog.result['data'])

    def populate_form_with_data(self, data):
        self.part_vars["Filament (g)"].set(data.get('filament') or data.get('Filament (g)', '0'))
        self.part_vars["Time (e.g. 7h 30m)"].set(data.get('time_str') or data.get('Time', '0h 0m'))
        if (printer_name := data.get('Printer')) and printer_name in self.printer_dropdown['values']: self.part_vars["Printer"].set(printer_name)
        if (material := data.get('material') or data.get('Material')) and material in self.material_dropdown['values']:
            self.part_vars["Material"].set(material); self.update_brands_list()
            if (brand := data.get('brand') or data.get('Brand')) and brand in self.brand_dropdown['values']: self.part_vars["Brand"].set(brand)
        self.calculate_part_cogs()
    def on_material_select(self, *args): self.update_brands_list(); self.calculate_part_cogs()
    def update_brands_list(self):
        material = self.part_vars["Material"].get(); brand_options = sorted(list(self.pricing_data.get(material, {}).keys()))
        self.brand_dropdown['values'] = brand_options
        if brand_options: self.part_vars["Brand"].set(brand_options[0])
        else: self.part_vars["Brand"].set("")
    def calculate_part_cogs(self, *args):
        try:
            form_data = {label: var.get() for label, var in self.part_vars.items()}
            printer_data = next((p for p in self.printers if p["id"] == self.printer_ids.get(form_data.get("Printer"))), None)
            filament_data = self.pricing_data.get(form_data.get("Material"), {}).get(form_data.get("Brand"), {})
            if not all([printer_data, filament_data]): self.current_part_cogs = 0.0; return
            self.current_part_cogs = calculate_cogs_values(form_data, printer_data, filament_data)['user_cogs']
        except (ValueError, TypeError, KeyError): self.current_part_cogs = 0.0
    def add_part(self):
        if not (part_name := self.part_vars["Part Name"].get()): return messagebox.showwarning("Input Error", "Please enter a name for the part.", parent=self)
        self.calculate_part_cogs()
        values = (part_name, f"{self.part_vars['Material'].get()} ({self.part_vars['Brand'].get()})", f"{self.current_part_cogs:.2f}")
        data_to_store = {key: var.get() for key, var in self.part_vars.items()}; data_to_store['cogs'] = self.current_part_cogs
        self.parts_tree.insert('', 'end', values=values, tags=(json.dumps(data_to_store),)); self.update_total_cogs()
    def remove_part(self):
        if not (selected_items := self.parts_tree.selection()): return
        for item in selected_items: self.parts_tree.delete(item)
        self.update_total_cogs()
    def clear_all_parts(self):
        for item in self.parts_tree.get_children(): self.parts_tree.delete(item)
        self.update_total_cogs()
    def update_total_cogs(self):
        total_cogs = sum(json.loads(self.parts_tree.item(item_id, 'tags')[0]).get('cogs', 0.0) for item_id in self.parts_tree.get_children())
        self.cogs_label.config(text=f"₹ {total_cogs:.2f}"); self.update_final_price(total_cogs)
    def on_margin_select(self, *args):
        self.custom_margin_entry.config(state="normal" if self.margin_var.get() == 999 else "disabled"); self.update_total_cogs()
    def update_final_price(self, total_cogs=None):
        if total_cogs is None: total_cogs = sum(json.loads(self.parts_tree.item(item_id, 'tags')[0]).get('cogs', 0.0) for item_id in self.parts_tree.get_children())
        try:
            margin_percent = float(self.custom_margin_var.get()) if self.margin_var.get() == 999 else self.margin_var.get()
            subtotal = 0.0 if margin_percent >= 100 else total_cogs / (1 - (margin_percent / 100.0))
            tax_rate = float(load_client_config().get("TAX_RATE_PERCENT", 0)); tax_amount = subtotal * (tax_rate / 100.0); total = subtotal + tax_amount
            self.subtotal_label.config(text=f"₹ {subtotal:.2f}"); self.tax_label.config(text=f"₹ {tax_amount:.2f} ({tax_rate}%)"); self.total_price_label.config(text=f"₹ {total:.2f}")
        except (AttributeError, ValueError, ZeroDivisionError):
            self.subtotal_label.config(text="₹ 0.00"); self.tax_label.config(text="₹ 0.00"); self.total_price_label.config(text="₹ 0.00")

    def generate_pdf(self):
        customer_name = self.vars["Customer Name"].get()
        if not customer_name:
            return messagebox.showerror("Input Error", "Customer Name is required.", parent=self)

        parts_data = [{"name": d.get("Part Name"), "cogs": d.get("cogs")} for item_id in self.parts_tree.get_children() if (d := json.loads(self.parts_tree.item(item_id, 'tags')[0]))]
        if not parts_data:
            return messagebox.showerror("Input Error", "Please add at least one part to the quotation.", parent=self)

        # --- PROMPT USER TO SAVE THE FILE FIRST ---
        customer_name_safe = re.sub(r'[^a-zA-Z0-9_]', '', customer_name.replace(' ', '_'))
        initial_filename = f"Quotation_{customer_name_safe}.pdf"
        save_path = filedialog.asksaveasfilename(
            initialfile=initial_filename,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")]
        )
        if not save_path:
            return # User cancelled the save dialog

        # --- GATHER DATA AND CALL API IN BACKGROUND ---
        def task():
            client_config = load_client_config()
            margin_percent = float(self.custom_margin_var.get()) if self.margin_var.get() == 999 else self.margin_var.get()
            quotation_data = {
                "customer_name": customer_name,
                "customer_company": self.vars["Company Name"].get(),
                "parts": parts_data,
                "margin_percent": margin_percent,
                "tax_rate_percent": float(client_config.get("TAX_RATE_PERCENT", 0)),
                "company_details": {k: client_config.get(v) for k, v in {"name": "COMPANY_NAME", "address": "COMPANY_ADDRESS", "contact": "COMPANY_CONTACT", "logo_path": "COMPANY_LOGO_PATH"}.items()}
            }

            # The API call now requires the save_path
            success = self.app.api.generate_quotation(quotation_data, save_path)

            if success:
                self.after(0, lambda: messagebox.showinfo("Success", f"Quotation PDF downloaded successfully!\n\nSaved to: {save_path}", parent=self))
            # Error messages are now handled by the APIClient method itself.

        self.app.run_threaded_task(task, "Generating PDF...")

class LogSelectionDialog(Toplevel):
    def __init__(self, parent, logs):
        super().__init__(parent); self.title("Select Log Entry"); self.transient(parent); self.grab_set(); self.result = None; self.logs = logs
        search_frame = ttk.Frame(self); search_frame.pack(fill='x', padx=10, pady=5)
        self.search_var = ttk.StringVar(); self.search_var.trace_add("write", lambda *args: self.filter_and_populate_tree())
        ttk.Label(search_frame, text="Search:").pack(side='left', padx=(0,5)); ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side='left')
        tree_container = ttk.Frame(self); tree_container.pack(fill='both', expand=True, padx=10, pady=5)
        columns = ("Filename", "Material", "Filament (g)", "Time"); self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", bootstyle="primary")
        for col in columns: self.tree.heading(col, text=col); self.tree.column(col, width=120)
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview, bootstyle="round-light"); self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y"); self.tree.bind("<Double-1>", self.on_ok)
        self.filter_and_populate_tree()
        button_frame = ttk.Frame(self); button_frame.pack(pady=10)
        ttk.Button(button_frame, text="OK", command=self.on_ok, bootstyle="primary").pack(side="left", padx=10)
        ttk.Button(button_frame, text="Cancel", command=self.destroy, bootstyle="secondary").pack(side="left", padx=10)
        self.geometry("600x400")
    def filter_and_populate_tree(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        search_term = self.search_var.get().lower()
        filtered_logs = [log for log in self.logs if not search_term or any(search_term in str(val).lower() for val in (log['filename'], log['data']['Material'], log['data']['Brand']))]
        for i, log in enumerate(filtered_logs):
            values = (log['filename'], f"{log['data']['Material']} ({log['data']['Brand']})", log['data']['Filament (g)'], log['data']['Time'])
            self.tree.insert('', 'end', iid=log['timestamp'], values=values, tags=('oddrow' if i % 2 else 'evenrow',))
    def on_ok(self, event=None):
        if not (selected_items := self.tree.selection()): return messagebox.showwarning("No Selection", "Please select a log entry.", parent=self)
        self.result = next((log for log in self.logs if log['timestamp'] == selected_items[0]), None); self.destroy()

class MonitorController:
    """
    Manages the background thread for monitoring the image input folder.
    """
    def __init__(self, app):
        self.app = app
        self.stop_event = threading.Event()
        self.file_queue = queue.Queue()
        self.dialog_result_queue = queue.Queue(maxsize=1)
        self.monitor_thread = None
        self.known_files = set()

    def _log_status(self, message):
        """Thread-safe method to log messages to the GUI's status box."""
        self.app.master.after(0, self.app.get_status_box().insert, END, f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
        self.app.master.after(0, self.app.get_status_box().see, END)

    def start(self):
        """Starts the monitoring background thread."""
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self._log_status("✅ Monitoring started...")

    def stop(self):
        """Signals the monitoring thread to stop."""
        self.stop_event.set()
        self._log_status("🛑 Monitoring stopped.")

    def put_dialog_result(self, image_path, result):
        """Receives the result from the verification dialog and puts it in a queue for the monitor thread."""
        if not self.dialog_result_queue.empty():
            try: self.dialog_result_queue.get_nowait()
            except queue.Empty: pass
        self.dialog_result_queue.put(result)

    def _get_config_paths(self):
        """Safely loads and returns required folder paths from the client config."""
        config = load_client_config()
        return {
            "input": config.get("IMAGE_INPUT_FOLDER"),
            "processed": config.get("PROCESSED_IMAGES_FOLDER"),
            "skipped": config.get("SKIPPED_IMAGES_FOLDER")
        }

    def requeue_skipped_files(self):
        """Moves all files from the skipped folder back to the input folder for processing."""
        paths = self._get_config_paths()
        if not paths["input"] or not paths["skipped"]:
            self._log_status("❌ Error: Input or Skipped folder not configured.")
            return

        try:
            skipped_files = [f for f in os.listdir(paths["skipped"]) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if not skipped_files:
                self._log_status("ℹ️ No skipped files found to re-process.")
                return

            self._log_status(f"➡️ Re-queueing {len(skipped_files)} skipped files...")
            for filename in skipped_files:
                shutil.move(os.path.join(paths["skipped"], filename), os.path.join(paths["input"], filename))
            self._log_status("✅ All skipped files moved back to the input folder.")
        except Exception as e:
            self._log_status(f"❌ Error re-queueing files: {e}")

    def _monitor_loop(self):
        """The main loop that runs in the background thread."""
        time.sleep(1)
        paths = self._get_config_paths()
        if not all(paths.values()):
            self._log_status("❌ CRITICAL: Monitoring stopped. Please configure all folder paths in Settings.")
            self.app.master.after(0, self.app.on_stop)
            return

        processed_server_log = self.app.api.get_processed_log()

        while not self.stop_event.is_set():
            try:
                current_files = {f for f in os.listdir(paths["input"]) if f.lower().endswith(('.png', '.jpg', '.jpeg'))}
                new_files = current_files - self.known_files

                for f in new_files:
                    if f not in processed_server_log:
                        self.file_queue.put(os.path.join(paths["input"], f))
                        self.known_files.add(f)
                        self._log_status(f"📂 New file detected: {f}")

                if not self.file_queue.empty():
                    image_path = self.file_queue.get()
                    filename = os.path.basename(image_path)

                    if not os.path.exists(image_path):
                        self._log_status(f"⚠️ File no longer exists, skipping: {filename}")
                        self.known_files.discard(filename)
                        continue

                    self._log_status(f"🧠 Processing with OCR: {filename}")
                    self.app.master.after(0, self.app.show_loader, f"Performing OCR on\n{filename}")
                    ocr_data = self.app.api.upload_for_ocr(image_path)

                    if not ocr_data or "error" in ocr_data:
                        self._log_status(f"❌ OCR failed for {filename}. Moving to skipped.")
                        self.app.master.after(0, self.app.hide_loader)
                        shutil.move(image_path, os.path.join(paths["skipped"], filename))
                        self.known_files.discard(filename)
                        continue

                    self._log_status(f"👤 Waiting for user verification for: {filename}")
                    self.app.master.after(0, self.app.show_verification_page, image_path, ocr_data)

                    dialog_result = self.dialog_result_queue.get()

                    if self.stop_event.is_set(): break

                    if dialog_result is None:
                        self._log_status(f"↩️ Verification cancelled. Re-queueing: {filename}")
                        self.file_queue.put(image_path)
                    elif dialog_result == "skip":
                        self._log_status(f"⏭️ File skipped by user. Moving to skipped folder: {filename}")
                        shutil.move(image_path, os.path.join(paths["skipped"], filename))
                        self.known_files.discard(filename)
                    else:
                        self.app.master.after(0, self.app.show_loader, f"Saving Log for\n{filename}")
                        self._log_status(f"➡️ Submitting final data for: {filename}")
                        response = self.app.api.process_image(image_path, dialog_result)
                        if response and response.get("status") == "success":
                            self._log_status(f"✅ Successfully processed and logged: {filename}")
                            shutil.move(image_path, os.path.join(paths["processed"], filename))
                            self.known_files.discard(filename)
                        else:
                            self._log_status(f"❌ Server failed to process {filename}. Re-queueing.")
                            self.file_queue.put(image_path)
                        self.app.master.after(0, self.app.hide_loader)

                time.sleep(2)

            except Exception as e:
                self._log_status(f"💥 Unhandled error in monitor loop: {e}")
                traceback.print_exc(file=sys.stdout)
                time.sleep(5)

class MainApp:
    def __init__(self, master):
        self.master = master
        master.title("FabraForma AL - Additive Ledger Client")
        master.minsize(1024, 600)
        master.app = self
        self.api = APIClient()
        self.monitor_controller = None
        self.main_ui_built = False
        self.sidebar_frame = None
        self.main_frame = None
        self.pages = {}
        self.sidebar_buttons = {}
        self.profile_photo = None
        self.cache = {}

        self.login_page = LoginPage(self.master, self)
        self.login_page.pack(fill="both", expand=True)

        # Create the loading widget once and keep it hidden
        self.loading_frame = None
        self._create_loading_widget()

        master.after(100, self.attempt_auto_login)

    def _create_loading_widget(self):
        self.loading_frame = ttk.Frame(self.master, bootstyle="dark")
        container = ttk.Frame(self.loading_frame, padding=20, bootstyle="dark")
        container.place(relx=0.5, rely=0.5, anchor="center")

        self.loading_label = ttk.Label(container, text="Loading...", font=('-size', 12), bootstyle="inverse-dark")
        self.loading_label.pack(pady=(0, 10))

        progress = ttk.Progressbar(container, mode='indeterminate', bootstyle="primary")
        progress.pack()
        progress.start(10)

    def show_loader(self, title="Processing..."):
        if self.loading_frame:
            self.loading_label.config(text=title)
            self.loading_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.loading_frame.lift()

    def hide_loader(self):
        if self.loading_frame:
            self.loading_frame.place_forget()

    def _update_row_heights(self, event=None):
        try:
            current_height = self.main_frame.winfo_height()
            base_height = 30
            scaling_factor = current_height // 150
            new_row_height = max(30, min(50, base_height + scaling_factor))
            style = ttk.Style()
            style.configure("Treeview", rowheight=new_row_height)
        except Exception:
            pass

    def run_threaded_task(self, task_func, loader_title="Processing..."):
        self.show_loader(loader_title)
        def task_wrapper():
            try:
                task_func()
            except Exception as e:
                print(f"Error in threaded task: {e}")
                traceback.print_exc()
            finally:
                self.master.after(0, self.hide_loader)
        threading.Thread(target=task_wrapper, daemon=True).start()

    def attempt_auto_login(self):
        config = load_client_config()
        remember_token = config.get('remember_token')
        if remember_token:
            def auto_login_task():
                success = self.api.refresh_token(remember_token)
                self.master.after(0, self._on_auto_login_complete, success)

            self.show_loader("Logging In...")
            threading.Thread(target=auto_login_task, daemon=True).start()

    def _on_auto_login_complete(self, success):
        self.hide_loader()
        if success:
            self.on_login_success()

    def on_login_success(self):
        self.login_page.pack_forget()
        if not self.main_ui_built:
            self.build_main_ui()
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.update_ui_for_role()
        self.show_page("Monitor")
        self.update_profile_widget()
        self.master.after(100, self._update_row_heights)

    def on_logout(self):
        if self.monitor_controller and not self.monitor_controller.stop_event.is_set():
            self.on_stop()

        self.cache = {} # Clear cache on logout
        config = load_client_config()
        remember_token = config.pop('remember_token', None)
        save_client_config(config)

        self.api.logout(remember_token=remember_token)

        if self.sidebar_frame: self.sidebar_frame.grid_forget()
        if self.main_frame: self.main_frame.grid_forget()
        self.login_page.pack(fill="both", expand=True)
        self.login_page.password_var.set("")

    def build_main_ui(self):
        self.master.rowconfigure(0, weight=1)
        self.master.columnconfigure(0, weight=1)
        self.master.columnconfigure(1, weight=5)

        style = ttk.Style()
        style.configure('.', font=('Montserrat', 10))
        style.configure('TLabel', font=('Montserrat', 10))
        style.configure('TButton', font=('Montserrat', 10))
        style.configure('Treeview.Heading', font=('Montserrat', 11, 'bold'))

        self.sidebar_frame = ttk.Frame(self.master, bootstyle="secondary")
        self.main_frame = ttk.Frame(self.master)

        self.main_frame.bind("<Configure>", self._update_row_heights)

        self.sidebar_frame.columnconfigure(0, weight=1)

        page_list = [ (MonitorPage, "Monitor"), (QuotationPage, "Quotation"), (LogsPage, "Logs"),
                      (PrintersPage, "Printers"), (FilamentsPage, "Filaments"), (UserManagementPage, "User Management"),
                      (ServerPage, "Server"), (SettingsPage, "Settings"), (ProfilePage, "Profile"), (VerificationPage, "Verification") ]

        for PageClass, name in page_list:
            frame = PageClass(self.main_frame, self)
            self.pages[name] = frame
            frame.place(x=0, y=0, relwidth=1, relheight=1)

        self.pages['Logs'].tree.tag_configure('oddrow', background=style.colors.light)
        self.pages['Logs'].tree.tag_configure('evenrow', background=style.colors.secondary)
        self.pages['Printers'].tree.tag_configure('oddrow', background=style.colors.light)
        self.pages['Printers'].tree.tag_configure('evenrow', background=style.colors.secondary)
        self.pages['Filaments'].tree.tag_configure('oddrow', background=style.colors.light)
        self.pages['Filaments'].tree.tag_configure('evenrow', background=style.colors.secondary)

        self.profile_frame = ttk.Frame(self.sidebar_frame, bootstyle="dark")

        self.profile_icon_label = ttk.Label(self.profile_frame, text="👤", font=('Montserrat', 16), bootstyle="inverse-dark")
        self.profile_icon_label.pack(side="left", padx=(10, 5), pady=5)

        self.profile_name_label = ttk.Label(self.profile_frame, text="Loading...", anchor="w", bootstyle="inverse-dark")
        self.profile_name_label.pack(side="left", fill="x", expand=True, pady=5)

        self.profile_frame.bind("<Button-1>", lambda e: self.show_page("Profile"))
        self.profile_icon_label.bind("<Button-1>", lambda e: self.show_page("Profile"))
        self.profile_name_label.bind("<Button-1>", lambda e: self.show_page("Profile"))

        self.main_ui_built = True

    def update_ui_for_role(self):
        for widget in self.sidebar_frame.winfo_children():
            if widget != self.profile_frame:
                widget.destroy()

        is_admin = self.api.user_info.get('role') == 'admin'
        button_order = ["Monitor", "Quotation", "Logs", "Printers", "Filaments", "User Management", "Server", "Settings"]

        self.sidebar_buttons = {}
        row_counter = 0
        for name in button_order:
            if name in ["Server", "User Management"] and not is_admin:
                continue

            button = ttk.Button(self.sidebar_frame, text=name, bootstyle="dark-outline", command=lambda n=name: self.show_page(n))
            button.grid(row=row_counter, column=0, sticky="ew", padx=10, pady=2, ipady=5)
            self.sidebar_buttons[name] = button
            row_counter += 1

        self.sidebar_frame.rowconfigure(row_counter, weight=1)
        self.profile_frame.grid(row=row_counter + 1, column=0, sticky="sew", padx=10, pady=10)

    def cache_data(self, key, data):
        self.cache[key] = data

    def get_cached_data(self, key):
        return self.cache.get(key)

    def update_profile_widget(self, force_refresh=False):
        if not force_refresh:
            cached_profile = self.get_cached_data('profile')
            if cached_profile:
                self.profile_name_label.config(text=cached_profile.get('username', 'Unknown User'))
                # Image handling can be more complex, so we'll still refresh it

        threading.Thread(target=self._update_profile_thread, daemon=True).start()

    def _update_profile_thread(self):
        profile_data = self.api.get_profile()
        if profile_data:
            self.cache_data('profile', profile_data)
            self.master.after(0, self.profile_name_label.config, {'text': profile_data.get('username', 'Unknown User')})
            if profile_data.get('profile_picture_url'):
                self._load_profile_image(profile_data['profile_picture_url'])
            else:
                self.master.after(0, self.profile_icon_label.config, {'text': "👤", 'image': ''})
        else:
            self.master.after(0, self.profile_name_label.config, {'text': "Error Loading"})

    def _load_profile_image(self, url):
        try:
            headers = self.api._get_auth_header()
            if not headers:
                self.master.after(0, self._update_profile_icon_ui, None)
                return
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            circular_image = create_circular_image(image, 32)
            self.master.after(0, self._update_profile_icon_ui, circular_image)
        except Exception as e:
            print(f"Failed to load profile image: {e}")
            self.master.after(0, self._update_profile_icon_ui, None)

    def _update_profile_icon_ui(self, pil_image):
        if pil_image:
            try:
                self.profile_photo = ImageTk.PhotoImage(pil_image)
                self.profile_icon_label.config(image=self.profile_photo, text="")
            except Exception as e:
                print(f"Failed to create Tkinter image: {e}")
                self.profile_icon_label.config(text="👤", image='')
        else:
            self.profile_icon_label.config(text="👤", image='')

    def show_page(self, page_name):
        for name, button in self.sidebar_buttons.items():
            button.config(bootstyle="dark-outline" if name != page_name else "primary")
        self.profile_frame.config(bootstyle="dark" if page_name != "Profile" else "primary")
        self.profile_icon_label.config(bootstyle="inverse-dark" if page_name != "Profile" else "inverse-primary")
        self.profile_name_label.config(bootstyle="inverse-dark" if page_name != "Profile" else "inverse-primary")
        page = self.pages[page_name]
        page.on_show()
        page.show()

    def update_sidebar_state(self, is_running):
        for name, button in self.sidebar_buttons.items():
            if name not in ("Monitor"):
                button.config(state="disabled" if is_running else "normal")

    def on_start(self):
        self.monitor_controller = MonitorController(self)
        self.monitor_controller.start()
        self.pages["Monitor"].set_bot_status(is_running=True)

    def on_stop(self):
        if self.monitor_controller:
            self.monitor_controller.stop()
        self.pages["Monitor"].set_bot_status(is_running=False)

    def get_status_box(self):
        return self.pages["Monitor"].get_status_box()

    def show_verification_page(self, image_path, ocr_data):
        self.hide_loader()
        self.show_page("Verification")
        self.pages["Verification"].load_data(image_path, ocr_data)

    def on_verification_complete(self, original_image_path, result):
        if self.monitor_controller:
            self.monitor_controller.put_dialog_result(original_image_path, result)
        if self.pages["Verification"].is_active:
            self.show_page("Monitor")


def initialize_client_config():
    config = load_client_config()
    defaults = { "IMAGE_INPUT_FOLDER": "", "PROCESSED_IMAGES_FOLDER": "processed_archive", "SKIPPED_IMAGES_FOLDER": "skipped_images",
                 "COMPANY_NAME": "Your Company Name", "COMPANY_ADDRESS": "123 Your Street, Your City", "COMPANY_CONTACT": "email@example.com | +91 0000000000",
                 "COMPANY_LOGO_PATH": "", "TAX_RATE_PERCENT": "18", "labour_rate": 100 }
    config_updated = False
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            config_updated = True

    if config_updated:
        save_client_config(config)

    if not config.get("IMAGE_INPUT_FOLDER") or not os.path.isdir(config.get("IMAGE_INPUT_FOLDER")):
        root = ttk.Window(); root.withdraw()
        messagebox.showinfo("First-Time Setup", "Please select the folder where your print images are stored.")
        input_folder = filedialog.askdirectory(title="Select Image Input Folder"); root.destroy()
        if not input_folder: messagebox.showerror("Setup Error", "An image input folder is required."); return False
        config["IMAGE_INPUT_FOLDER"] = input_folder; save_client_config(config)

    for folder_key in ["PROCESSED_IMAGES_FOLDER", "SKIPPED_IMAGES_FOLDER"]:
        if folder_path := config.get(folder_key): os.makedirs(folder_path, exist_ok=True)
    return True

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError):
        pass

    if initialize_client_config():
        root = ttk.Window()

        # --- CUSTOM THEME DEFINITION ---
        style = ttk.Style()
        theme_colors = {
            "primary": "#3a4be3",
            "secondary": "#29349b",
            "success": "#3498db",
            "info": "#ffafda",
            "warning": "#f39c12",
            "danger": "#e74c3c",
            "light": "#3b4a91",
            "dark": "#1c246d",
            "bg": "#1c246d",
            "fg": "#ffafda",
            "selectbg": "#3a4be3",
            "selectfg": "#ffffff",
            "border": "#3a4be3",
            "inputfg": "#ffafda",
            "inputbg": "#29349b"
        }
        style.theme_create("fabraforma_custom", parent="darkly", settings={
            ".": {
                "configure": {
                    "background": theme_colors["bg"],
                    "foreground": theme_colors["fg"],
                    "bordercolor": theme_colors["border"],
                    "selectbackground": theme_colors["selectbg"],
                    "selectforeground": theme_colors["selectfg"],
                    "fieldbackground": theme_colors["inputbg"],
                    "insertcolor": theme_colors["inputfg"],
                }
            },
            "TLabel": {
                "configure": { "foreground": theme_colors["fg"], "background": theme_colors["bg"] }
            },
            "TButton": {
                "configure": { "padding": 5 },
                "map": {
                    "background": [("active", theme_colors["selectbg"])],
                    "foreground": [("active", theme_colors["selectfg"])]
                }
            },
            "Treeview": {
                "map": {
                    "background": [('selected', theme_colors["selectbg"])],
                    "foreground": [('selected', theme_colors["selectfg"])]
                }
            }
        })
        style.theme_use("fabraforma_custom")
        # --- END CUSTOM THEME ---

        app = MainApp(root)

        app_width = 1280
        app_height = 720
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()

        x = (screen_width / 2) - (app_width / 2)
        y = (screen_height / 2) - (app_height / 2)

        root.geometry(f'{app_width}x{app_height}+{int(x)}+{int(y)}')

        def on_closing():
            if app.monitor_controller and not app.monitor_controller.stop_event.is_set():
                if messagebox.askokcancel("Quit", "The bot is still running. Are you sure you want to quit?"):
                    app.on_stop()
                    root.destroy()
            else:
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
