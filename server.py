from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS  # Import CORS
import os
import tempfile
import threading
import time
import hashlib
import comtypes.client
from comtypes import CoInitialize, CoUninitialize
import shutil
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

ORIGIN_DIR = 'origin'
CONVERTED_DIR = 'converted'

if not os.path.exists(ORIGIN_DIR):
    os.makedirs(ORIGIN_DIR)

ORIGIN_DIR = os.path.abspath('origin')
CONVERTED_DIR = os.path.abspath('converted')

def delete_old_files(directory, max_age_hours=6):
    """지정된 디렉토리에서 max_age_hours 시간보다 오래된 파일들을 삭제합니다."""
    now = datetime.now()
    cutoff = now - timedelta(hours=max_age_hours)

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_modified_time < cutoff:
                try:
                    os.remove(file_path)
                    print(f"Deleted old file: {file_path}")
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

def clean_directories():
    """origin 및 converted 디렉토리를 주기적으로 청소합니다."""
    while True:
        delete_old_files(ORIGIN_DIR)
        delete_old_files(CONVERTED_DIR)
        time.sleep(6 * 3600)  # 6시간 대기 (6시간 = 6 * 3600초)


def initialize_com():
    try:
        CoInitialize()
    except Exception as e:
        print(f"COM initialization failed: {e}")
        raise

def finalize_com():
    try:
        CoUninitialize()
    except Exception as e:
        print(f"COM uninitialization failed: {e}")

def calculate_file_hash(file_path):
    """Calculate the MD5 hash of a file."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    return md5_hash.hexdigest()

def convert_word_to_pdf(input_file, output_file):
    word = comtypes.client.CreateObject('Word.Application')
    word.Visible = False
    doc = word.Documents.Open(input_file)
    doc.SaveAs(output_file, FileFormat=17)  # 17 corresponds to the PDF format
    doc.Close(False)
    time.sleep(1)  # Adjust the sleep duration as necessary
    word.Quit()

def convert_excel_to_pdf(input_file, output_file):
    excel = comtypes.client.CreateObject('Excel.Application')
    excel.Visible = False
    workbook = excel.Workbooks.Open(input_file)
    workbook.ExportAsFixedFormat(0, output_file)  # 0 corresponds to the PDF format
    workbook.Close(False)
    time.sleep(1)  # Adjust the sleep duration as necessary
    excel.Quit()

def convert_ppt_to_pdf(input_file, output_file):
    powerpoint = comtypes.client.CreateObject('PowerPoint.Application')
    powerpoint.Visible = True
    presentation = powerpoint.Presentations.Open(input_file)
    presentation.SaveAs(output_file, 32)  # 32 corresponds to the PDF format
    presentation.Close()
    time.sleep(1)  # Adjust the sleep duration as necessary
    powerpoint.Quit()

def convert_hwp_to_pdf(input_file, output_file):
    hwp = comtypes.client.CreateObject('HWPFrame.HwpObject')
    hwp.RegisterModule('FilePathCheckDLL','FilePathCheckerModuleExample')
    hwp.XHwpWindows.Item(0).Visible = False
    try:
        hwp.Open(input_file, "HWP", "HWP")
        hwp.HAction.GetDefault('FileSaveAsPdf', hwp.HParameterSet.HFileOpenSave.HSet)
        hwp.HParameterSet.HFileOpenSave.filename = output_file
        hwp.HParameterSet.HFileOpenSave.Format = 'PDF'
        hwp.HParameterSet.HFileOpenSave.Quality = 100
        hwp.HAction.Execute("FileSaveAsPdf", hwp.HParameterSet.HFileOpenSave.HSet)
    finally:
        hwp.Clear(1)  # Close the document and clear memory
        hwp.Quit()

def delete_file_after_delay(file_path, delay=1):
    """Delete the file after a specified delay"""
    def delete():
        for _ in range(5):  # Try up to 5 times
            try:
                time.sleep(delay)
                os.remove(file_path)
                break
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")
                time.sleep(1)  # Wait before retrying
    threading.Thread(target=delete).start()

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # # Save the uploaded file to a temporary location
    # with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_input:
    #     temp_input.write(file.read())
    #     temp_input_path = temp_input.name

    # Save the uploaded file to the 'origin' directory
    origin_file_path = os.path.abspath(os.path.join(ORIGIN_DIR, file.filename))
    file.save(origin_file_path)

    temp_input_path = os.path.abspath(origin_file_path)

    # Calculate the hash of the uploaded file to check for existing conversion
    file_hash = calculate_file_hash(origin_file_path)
    converted_file_name = f"{file_hash}.pdf"
    converted_file_path = os.path.abspath(os.path.join(CONVERTED_DIR, converted_file_name))

    # Check if the file has already been converted
    if os.path.exists(converted_file_path):
        return send_file(converted_file_path, as_attachment=True, download_name='converted.pdf', mimetype='application/pdf')

    try:
        initialize_com()
        ext = os.path.splitext(temp_input_path)[1].lower()


        if ext in ['.doc', '.docx']:
            convert_word_to_pdf(temp_input_path, converted_file_path)
        elif ext in ['.xls', '.xlsx']:
            convert_excel_to_pdf(temp_input_path, converted_file_path)
        elif ext in ['.ppt', '.pptx']:
            convert_ppt_to_pdf(temp_input_path, converted_file_path)
        elif ext in ['.hwp', '.hml']:
            convert_hwp_to_pdf(temp_input_path, converted_file_path)
        else:
            return jsonify({"error": "Unsupported file extension"}), 400
        # Return the PDF file to the client
        response = send_file(converted_file_path, as_attachment=True, download_name='converted.pdf', mimetype='application/pdf')
        return response
    except Exception as e:
        print(f"Error during file conversion: {e}")
        return jsonify({"error": "An error occurred during file conversion"}), 500
    finally:
        finalize_com()

@app.route("/")
def hello_world():
    return render_template('index.html')

if __name__ == '__main__':
    cleaner_thread = threading.Thread(target=clean_directories, daemon=True)
    cleaner_thread.start()
    app.run(host='0.0.0.0', port=65530)
