from flask import Flask, render_template, request, send_file, jsonify
import os
import threading
import shutil
import uuid
import subprocess
from sc_engine import Engine

app = Flask(__name__)
engine = Engine()

tasks = {}

def check_and_install_deps():
    if shutil.which("astcenc") is None:
        print("System dependency 'astcenc' not found. Installing via apt...")
        try:
            subprocess.run(["sudo", "apt-get", "update"], check=True)
            subprocess.run(["sudo", "apt-get", "install", "-y", "astcenc"], check=True)
            print("'astcenc' installed successfully.")
        except Exception as e:
            print(f"Failed to auto-install 'astcenc': {e}")
            print("Please run: sudo apt-get install astcenc")

def progress_updater(task_id, msg, pct):
    if task_id in tasks:
        tasks[task_id]["message"] = msg
        tasks[task_id]["percent"] = pct

def run_decode(task_id, file_path, filename):
    try:
        tasks[task_id]["status"] = "processing"
        
        def callback(m, p):
            progress_updater(task_id, m, p)
            
        zip_path = engine.decode_file(file_path, filename, progress_callback=callback)
        tasks[task_id]["download_url"] = f"/download/{task_id}/{os.path.basename(zip_path)}"
        tasks[task_id]["status"] = "done"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = str(e)

def run_encode(task_id, file_path):
    try:
        tasks[task_id]["status"] = "processing"
        
        def callback(m, p):
            progress_updater(task_id, m, p)
            
        out_path = engine.encode_file(file_path, progress_callback=callback)
        tasks[task_id]["download_url"] = f"/download/{task_id}/{os.path.basename(out_path)}"
        tasks[task_id]["status"] = "done"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status/<task_id>')
def status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    return jsonify(task)

@app.route('/upload_decode', methods=['POST'])
def upload_decode():
    if 'file' not in request.files: return "No file", 400
    file = request.files['file']
    
    task_id = str(uuid.uuid4())
    task_dir = os.path.join("temp", task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    save_path = os.path.join(task_dir, file.filename)
    file.save(save_path)

    tasks[task_id] = {
        "status": "idle",
        "message": "Queued...",
        "percent": 0,
        "download_url": ""
    }

    t = threading.Thread(target=run_decode, args=(task_id, save_path, file.filename))
    t.start()
    return jsonify({"status": "started", "task_id": task_id})

@app.route('/upload_encode', methods=['POST'])
def upload_encode():
    if 'file' not in request.files: return "No file", 400
    file = request.files['file']
    
    task_id = str(uuid.uuid4())
    task_dir = os.path.join("temp", task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    save_path = os.path.join(task_dir, file.filename)
    file.save(save_path)

    tasks[task_id] = {
        "status": "idle",
        "message": "Queued...",
        "percent": 0,
        "download_url": ""
    }

    t = threading.Thread(target=run_encode, args=(task_id, save_path))
    t.start()
    return jsonify({"status": "started", "task_id": task_id})

@app.route('/download/<task_id>/<filename>')
def download(task_id, filename):
    file_path = os.path.join("temp", task_id, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    if not os.path.exists("temp"):
        os.makedirs("temp")
    check_and_install_deps()
    app.run(host='0.0.0.0', port=5000)