from flask import Flask, render_template, request, send_file
import os
from werkzeug.utils import secure_filename
from converter import convert_text_to_excel
import atexit
import shutil

app = Flask(__name__)

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
