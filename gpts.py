from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
import os
import threading
import time
import hashlib
import comtypes.client
from comtypes import CoInitialize, CoUninitialize
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# 디렉토리 설정 및 초기화
ORIGIN_DIR = os.path.abspath('origin')
CONVERTED_DIR = os.path.abspath('converted')
os.makedirs(ORIGIN_DIR, exist_ok=True)
os.makedirs(CONVERTED_DIR, exist_ok=True)

def delete_old_files(directory, max_age_hours=6):
    """지정된 디렉토리에서 max_age_hours 시간보다 오래된 파일들을 삭제합니다."""
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) and datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_time:
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
        time.sleep(6 * 3600)  # 6시간 대기

def initialize_com():
    """COM 초기화."""
    try:
        CoInitialize()
    except Exception as e:
        print(f"COM initialization failed: {e}")
        raise

def finalize_com():
    """COM 해제."""
    try:
        CoUninitialize()
    except Exception as e:
        print(f"COM uninitialization failed: {e}")

def calculate_file_hash(file_path):
    """파일의 MD5 해시를 계산합니다."""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    return md5_hash.hexdigest()

def convert_to_pdf(input_file, output_file, application, conversion_func, close_func):
    """지정된 어플리케이션으로 파일을 PDF로 변환합니다."""
    app = comtypes.client.CreateObject(application)
    app.Visible = False
    conversion_func(app, input_file, output_file)
    close_func(app)

def convert_word_to_pdf(app, input_file, output_file):
    doc = app.Documents.Open(input_file)
    doc.SaveAs(output_file, FileFormat=17)
    doc.Close(False)

def convert_excel_to_pdf(app, input_file, output_file):
    workbook = app.Workbooks.Open(input_file)
    workbook.ExportAsFixedFormat(0, output_file)
    workbook.Close(False)

def convert_ppt_to_pdf(app, input_file, output_file):
    presentation = app.Presentations.Open(input_file)
    presentation.SaveAs(output_file, 32)
    presentation.Close()

def convert_hwp_to_pdf(app, input_file, output_file):
    app.RegisterModule('FilePathCheckDLL', 'FilePathCheckerModuleExample')
    app.XHwpWindows.Item(0).Visible = False
    try:
        app.Open(input_file, "HWP", "HWP")
        app.HAction.GetDefault('FileSaveAsPdf', app.HParameterSet.HFileOpenSave.HSet)
        app.HParameterSet.HFileOpenSave.filename = output_file
        app.HParameterSet.HFileOpenSave.Format = 'PDF'
        app.HParameterSet.HFileOpenSave.Quality = 100
        app.HAction.Execute("FileSaveAsPdf", app.HParameterSet.HFileOpenSave.HSet)
    finally:
        app.Clear(1)
        app.Quit()

def delete_file_after_delay(file_path, delay=1):
    """지정된 파일을 일정 시간 후에 삭제합니다."""
    def delete():
        for _ in range(5):
            try:
                time.sleep(delay)
                os.remove(file_path)
                break
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")
                time.sleep(1)
    threading.Thread(target=delete).start()

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    origin_file_path = os.path.join(ORIGIN_DIR, file.filename)
    file.save(origin_file_path)

    file_hash = calculate_file_hash(origin_file_path)
    converted_file_name = f"{file_hash}.pdf"
    converted_file_path = os.path.join(CONVERTED_DIR, converted_file_name)

    if os.path.exists(converted_file_path):
        return send_file(converted_file_path, as_attachment=True, download_name='converted.pdf', mimetype='application/pdf')

    ext = os.path.splitext(origin_file_path)[1].lower()
    conversion_mapping = {
        '.doc': ('Word.Application', convert_word_to_pdf, lambda app: app.Quit()),
        '.docx': ('Word.Application', convert_word_to_pdf, lambda app: app.Quit()),
        '.xls': ('Excel.Application', convert_excel_to_pdf, lambda app: app.Quit()),
        '.xlsx': ('Excel.Application', convert_excel_to_pdf, lambda app: app.Quit()),
        '.ppt': ('PowerPoint.Application', convert_ppt_to_pdf, lambda app: app.Quit()),
        '.pptx': ('PowerPoint.Application', convert_ppt_to_pdf, lambda app: app.Quit()),
        '.hwp': ('HWPFrame.HwpObject', convert_hwp_to_pdf, lambda app: app.Quit()),
        '.hml': ('HWPFrame.HwpObject', convert_hwp_to_pdf, lambda app: app.Quit())
    }

    if ext not in conversion_mapping:
        return jsonify({"error": "Unsupported file extension"}), 400

    try:
        initialize_com()
        app_name, conversion_func, close_func = conversion_mapping[ext]
        convert_to_pdf(origin_file_path, converted_file_path, app_name, conversion_func, close_func)
        return send_file(converted_file_path, as_attachment=True, download_name='converted.pdf', mimetype='application/pdf')
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
