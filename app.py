from flask import Flask, render_template, request, send_file
import os
from werkzeug.utils import secure_filename
from converter import convert_text_to_excel
import atexit
import shutil
from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
import random
import time
import os
import firebase_admin
from firebase_admin import credentials, auth
import json
app = Flask(__name__)
CORS(app)

# Firebase Admin SDK Initialization
try:
    # Try to load credentials from the file path specified in the environment variable
    cred_path = os.environ.get('FIREBASE_ADMIN_CREDENTIALS_PATH')
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully via file.")
    elif 'FIREBASE_ADMIN_CREDENTIALS' in os.environ:
        # Fallback to loading from JSON string (less reliable on Render)
        cred_str = os.environ.get('FIREBASE_ADMIN_CREDENTIALS')
        cred = credentials.Certificate(json.loads(cred_str))
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully via JSON string (less reliable on Render).")
    else:
        print("Warning: Neither FIREBASE_ADMIN_CREDENTIALS_PATH nor FIREBASE_ADMIN_CREDENTIALS environment variable is set.")
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")

# Email configuration (use environment variables)
EMAIL = os.environ.get('report.vvs@gmail.com')
PASSWORD = os.environ.get('fhwwtlvxatblopjc')

# Temporary storage for OTPs during signup
signup_otp_store = {}
OTP_EXPIRATION_TIME = 300  # 5 minutes

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

@app.route('/signup/request-otp', methods=['POST'])
def signup_request_otp():
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Email address is required'}), 400
    email = data['email']
    otp = generate_otp()
    signup_otp_store[email] = {'otp': str(otp), 'timestamp': time.time()}
    if send_otp_email(email, otp):
        return jsonify({'message': 'Sign-up OTP sent successfully'}), 200
    else:
        return jsonify({'error': 'Failed to send sign-up OTP'}), 500

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
                except auth.FirebaseError as e:
                    return jsonify({'error': f'Firebase error creating user: {e}'}), 500
            else:
                return jsonify({'error': 'Invalid OTP'}), 401
        else:
            del signup_otp_store[email]
            return jsonify({'error': 'Sign-up OTP has expired'}), 401
    else:
        return jsonify({'error': 'Sign-up OTP not requested for this email'}), 400


UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'  # Create a temporary folder for generated files
ALLOWED_EXTENSIONS = {'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET'])
def upload_form():
    return render_template('upload.html')

@app.route('/', methods=['POST'])
def process_file():
    if 'file' not in request.files:
        return "No file part"
    file = request.files['file']
    if file.filename == '':
        return "No selected file"
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            # Generate the temporary Excel file in the TEMP_FOLDER
            temp_excel_filename = os.path.join(app.config['TEMP_FOLDER'], 'cbse_results_' + os.path.splitext(filename)[0] + '.xlsx')
            convert_text_to_excel(filepath, temp_excel_filename)
            return send_file(temp_excel_filename, as_attachment=True, download_name='cbse_results.xlsx')
        except ValueError as e:
            return f"Error: {str(e)}"
        finally:
            os.remove(filepath) # Clean up the uploaded text file
            # We will clean up the temporary Excel files later

    return "Invalid file type"

# Function to clean up temporary files
def cleanup_temp_folder():
    if os.path.exists(app.config['TEMP_FOLDER']):
        shutil.rmtree(app.config['TEMP_FOLDER'])
        os.makedirs(app.config['TEMP_FOLDER']) # Recreate the folder for future use

# Register the cleanup function to run when the app exits
atexit.register(cleanup_temp_folder)

if __name__ == '__main__':
    app.run(debug=True)
