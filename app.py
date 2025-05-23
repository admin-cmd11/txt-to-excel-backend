from flask import Flask, request, jsonify, render_template, send_file, redirect, session
from flask_cors import CORS
import smtplib
import random
import time
import os
import firebase_admin
from firebase_admin import credentials, auth
from converter import convert_text_to_excel
from werkzeug.utils import secure_filename
import shutil
import atexit
import json


app = Flask(__name__)
CORS(app)

# Global Firebase App instance and initialization flag
firebase_app = None
firebase_initialized = False

# Firebase Admin SDK Initialization (Ensure only one initialization)
try:
    if not firebase_initialized:
        cred_str = os.environ.get('FIREBASE_ADMIN_CREDENTIALS')
        if cred_str:
            try:
                cred_json = json.loads(cred_str)
                cred = credentials.Certificate(cred_json)
                firebase_app = firebase_admin.initialize_app(cred)
                firebase_initialized = True
                print("Firebase Admin SDK initialized successfully.")
            except json.JSONDecodeError as e:
                print(f"Error decoding FIREBASE_ADMIN_CREDENTIALS JSON: {e}")
            except Exception as e:
                print(f"Error initializing Firebase Admin SDK: {e}")
        else:
            print("Warning: FIREBASE_ADMIN_CREDENTIALS environment variable not set.")
    else:
        print("Firebase Admin SDK already initialized.")
except Exception as e:
    print(f"Outer error during Firebase Admin SDK initialization: {e}")

# ... rest of your app.py code ...


# Email configuration (use environment variables)
EMAIL = os.environ.get('EMAIL_ADDRESS')
PASSWORD = os.environ.get('EMAIL_PASSWORD')

# Temporary storage for OTPs during signup
signup_otp_store = {}
OTP_EXPIRATION_TIME = 300  # 5 minutes

UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

def generate_otp(length=4):
    return random.randrange(1000, 9999)

def send_otp_email(receiver_email, otp):
    subject = "OTP for Text to Excel Sign Up"
    body = f"Greetings,\nThank you for signing up! For security verification, please enter the following OTP: {otp}"
    message = f"Subject: {subject}\n\n{body}"
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, receiver_email, message)
        server.quit()
        print(f"Sign-up OTP sent successfully to {receiver_email}")
        return True
    except Exception as e:
        print(f"Error sending sign-up OTP email: {e}")
        return False

@app.route('/', methods=['GET'])
def backend_status():
    """Returns a simple JSON status indicating the backend is running."""
    return jsonify({"status": "CBSE Results to Excel Backend API is running"})
@app.route('/test-firebase-init', methods=['GET'])
def test_firebase_init():
    try:
        cred_str = os.environ.get('FIREBASE_ADMIN_CREDENTIALS')
        if cred_str:
            cred_info = json.loads(cred_str)
            cred = credentials.Certificate(cred_info)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
                return jsonify({"message": "Firebase Admin SDK initialized successfully for test."}), 200
            else:
                return jsonify({"message": "Firebase Admin SDK was already initialized."}), 200
        else:
            return jsonify({"error": "FIREBASE_ADMIN_CREDENTIALS not set for test."}), 400
    except Exception as e:
        return jsonify({"error": f"Error initializing Firebase Admin SDK for test: {e}"}), 500
@app.route('/signup/request-otp', methods=['POST'])
def signup_request_otp():
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Email address is required'}), 400
    email = data['email']

    # Check if user already exists in Firebase Auth
    try:
        auth.get_user_by_email(email)
        return jsonify({'error': 'An account with this email already exists'}), 409
    except firebase_admin.auth.UserNotFoundError:
        # If not found, continue with OTP process
        otp = generate_otp()
        signup_otp_store[email] = {'otp': str(otp), 'timestamp': time.time()}
        if send_otp_email(email, otp):
            return jsonify({'message': 'Sign-up OTP sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send sign-up OTP'}), 500
    except Exception as e:
        print(f"Error checking existing user: {e}")
        return jsonify({'error': 'Internal server error while checking user existence'}), 500


@app.route('/signup/verify-otp', methods=['POST'])
def signup_verify_otp():
    data = request.get_json()
    if not data or 'email' not in data or 'otp' not in data or 'password' not in data:
        return jsonify({'error': 'Email, OTP, and password are required'}), 400
    email = data['email']
    entered_otp = data['otp']
    password = data['password']  # Expect the password from the frontend

    if email in signup_otp_store:
        stored_data = signup_otp_store[email]
        if time.time() - stored_data['timestamp'] < OTP_EXPIRATION_TIME:
            if stored_data['otp'] == entered_otp:
                del signup_otp_store[email]
                try:
                    user = auth.create_user(email=email, password=password)
                    print(f"Successfully created new user in Firebase: {user.uid}")
                    return jsonify({'message': 'Account created successfully'}), 201
                except Exception as e:  # Catch a more general exception
                    print(f"Firebase error creating user: {e}")
                    return jsonify({'error': f'Firebase error creating user: {e}'}), 500
            else:
                return jsonify({'error': 'Invalid OTP'}), 401
        else:
            del signup_otp_store[email]
            return jsonify({'error': 'Sign-up OTP has expired'}), 401
    else:
        return jsonify({'error': 'Sign-up OTP not requested for this email'}), 400
        
@app.route('/sessionLogin', methods=['POST'])
def session_login():
    id_token = request.json.get('idToken')
    if not id_token:
        return jsonify({'error': 'Missing ID token'}), 400

    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        session['user_email'] = decoded_token['email']
        return jsonify({'message': 'Login successful'}), 200
    except Exception as e:
        print(f"Auth error: {e}")
        return jsonify({'error': 'Unauthorized'}), 401

@app.route('/process-file', methods=['POST'])
def process_file():
    """Handles the upload of the TXT file, processes it, and returns the Excel file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            temp_excel_filename = os.path.join(app.config['TEMP_FOLDER'], 'cbse_results_' + os.path.splitext(filename)[0] + '.xlsx')
            convert_text_to_excel(filepath, temp_excel_filename)
            return send_file(temp_excel_filename, as_attachment=True, download_name='cbse_results.xlsx')
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        finally:
            os.remove(filepath)
            if os.path.exists(temp_excel_filename):
                os.remove(temp_excel_filename)
    return jsonify({'error': 'Invalid file type'}), 400

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cleanup_temp_folder():
    if os.path.exists(app.config['TEMP_FOLDER']):
        shutil.rmtree(app.config['TEMP_FOLDER'])
        os.makedirs(app.config['TEMP_FOLDER'])

atexit.register(cleanup_temp_folder)

if __name__ == '__main__':
    app.run(debug=True)
