import os
import threading
import time
import h5py
import numpy as np
import json
from flask import Flask, render_template, jsonify, abort, Response
from datetime import datetime

# --- CONFIGURACIÓN ---
DATA_PATH = os.path.join('..', 'proof', 'DataSet')
REFRESH_INTERVAL_SECONDS = 30

# --- CACHÉ DE DATOS GLOBAL ---
data_cache = {
    "summary": [],      
    "details": [],      
    "filenames": [],    
    "lock": threading.Lock()
}

# --- INICIALIZACIÓN DE FLASK ---
app = Flask(__name__)

# --- CLASE PARA SERIALIZAR NUMPY Y DATETIME A JSON (VERSIÓN NUMPY 2.0+ COMPATIBLE) ---
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # FIX: Usar la clase base np.integer para cualquier tipo de entero de NumPy
        if isinstance(obj, np.integer):
            return int(obj)
        # FIX: Usar la clase base np.floating para cualquier tipo de flotante de NumPy
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(NumpyEncoder, self).default(obj)

# --- LÓGICA DE PROCESAMIENTO DE DATOS ---
def parse_timestamp_from_filename(filename):
    try:
        parts = filename.split('_')
        timestamp_str = f"{parts[2]}_{parts[3].split('.')[0]}"
        return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except (IndexError, ValueError):
        return datetime.now()

def process_h5_file(filepath):
    with h5py.File(filepath, 'r') as hf:
        if 'temperature_matrix' not in hf:
            return None
        
        temp_matrix = np.array(hf['temperature_matrix'])
        
        min_temp = np.min(temp_matrix)
        max_temp = np.max(temp_matrix)
        avg_temp = np.mean(temp_matrix)
        
        hot_spot_idx = np.unravel_index(np.argmax(temp_matrix), temp_matrix.shape)
        cold_spot_idx = np.unravel_index(np.argmin(temp_matrix), temp_matrix.shape)
        hot_spot_coords = [int(i) for i in hot_spot_idx]
        cold_spot_coords = [int(i) for i in cold_spot_idx]

        grad_y, grad_x = np.gradient(temp_matrix)
        gradient_magnitude = np.sqrt(grad_y**2 + grad_x**2)
        
        roi_threshold = min_temp + 0.95 * (max_temp - min_temp)
        hot_roi = np.where(temp_matrix > roi_threshold, 1, 0)
        
        return {
            "stats": {
                "min": min_temp,
                "max": max_temp,
                "avg": avg_temp,
                "hot_spot_coords": hot_spot_coords,
                "cold_spot_coords": cold_spot_coords,
            },
            "matrices": {
                "temperature": temp_matrix,
                "gradient_magnitude": gradient_magnitude,
                "hot_roi": hot_roi,
            }
        }

def data_loader_thread():
    print("Iniciando hilo de carga de datos...")
    while True:
        try:
            if not os.path.isdir(DATA_PATH):
                print(f"Directorio no encontrado: {DATA_PATH}. Esperando...")
                time.sleep(REFRESH_INTERVAL_SECONDS)
                continue

            h5_files = sorted([f for f in os.listdir(DATA_PATH) if f.endswith('.h5')])
            
            with data_cache['lock']:
                new_files = [f for f in h5_files if f not in data_cache['filenames']]
                
                if new_files:
                    print(f"Nuevos archivos detectados: {new_files}")
                    for filename in new_files:
                        filepath = os.path.join(DATA_PATH, filename)
                        processed_data = process_h5_file(filepath)
                        
                        if processed_data:
                            timestamp = parse_timestamp_from_filename(filename)
                            
                            data_cache['summary'].append({
                                "timestamp": timestamp,
                                "max_temp": processed_data['stats']['max'],
                                "min_temp": processed_data['stats']['min'],
                            })
                            
                            data_cache['details'].append({
                                "filename": filename,
                                **processed_data
                            })
                            data_cache['filenames'].append(filename)

                    combined = sorted(zip(data_cache['summary'], data_cache['details']), key=lambda x: x[0]['timestamp'])
                    if combined:
                       summary_list, details_list = zip(*combined)
                       data_cache['summary'] = list(summary_list)
                       data_cache['details'] = list(details_list)
        except Exception as e:
            print(f"Error en el hilo de carga de datos: {e}")
        
        time.sleep(REFRESH_INTERVAL_SECONDS)

# --- RUTAS DE LA API Y DE LA PÁGINA ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data/summary')
def get_summary_data():
    with data_cache['lock']:
        json_data = json.dumps(data_cache['summary'], cls=NumpyEncoder)
        return Response(json_data, mimetype='application/json')

@app.route('/api/data/detail/<int:index>')
def get_detail_data(index):
    with data_cache['lock']:
        if 0 <= index < len(data_cache['details']):
            json_data = json.dumps(data_cache['details'][index], cls=NumpyEncoder)
            return Response(json_data, mimetype='application/json')
        else:
            abort(404, description="Dataset no encontrado")

# --- PUNTO DE ENTRADA DE LA APLICACIÓN ---
if __name__ == '__main__':
    loader = threading.Thread(target=data_loader_thread, daemon=True)
    loader.start()
    
    app.run(host='0.0.0.0', port=5000, debug=True)