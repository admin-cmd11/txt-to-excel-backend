from flask import Flask, request, send_file, jsonify
import os
from werkzeug.utils import secure_filename
from converter import convert_text_to_excel
from flask_cors import CORS
import atexit
import shutil

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET'])
def backend_status():
    """Returns a simple JSON status indicating the backend is running."""
    return jsonify({"status": "CBSE Results to Excel Backend API is running"})

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

def cleanup_temp_folder():
    if os.path.exists(app.config['TEMP_FOLDER']):
        shutil.rmtree(app.config['TEMP_FOLDER'])
        os.makedirs(app.config['TEMP_FOLDER'])

atexit.register(cleanup_temp_folder)

if __name__ == '__main__':
    app.run(debug=True)
