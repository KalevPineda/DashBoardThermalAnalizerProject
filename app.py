import os
import threading
import time
import h5py
import numpy as np
import json
from flask import Flask, render_template, jsonify, abort
from datetime import datetime

# --- CONFIGURACIÓN ---
DATA_PATH = os.path.join('..', 'proof', 'DataSet') # Ruta a tus archivos H5
REFRESH_INTERVAL_SECONDS = 30 # Intervalo para buscar nuevos archivos

# --- CACHÉ DE DATOS GLOBAL ---
# Usaremos un diccionario para almacenar los datos procesados y evitar relecturas.
# El Lock es crucial para la seguridad entre hilos.
data_cache = {
    "summary": [],      # Para la gráfica temporal (timestamp, max, min)
    "details": [],      # Datos completos de cada archivo
    "filenames": [],    # Nombres de archivo para evitar reprocesar
    "lock": threading.Lock()
}

# --- INICIALIZACIÓN DE FLASK ---
app = Flask(__name__)

# --- CLASE PARA SERIALIZAR NUMPY A JSON ---
# Flask no puede convertir arrays de NumPy a JSON por defecto.
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.int_, np.intc, np.intp, np.int8,
                            np.int16, np.int32, np.int64, np.uint8,
                            np.uint16, np.uint32, np.uint64)):
            return int(obj)
        if isinstance(obj, (np.float_, np.float16, np.float32, 
                            np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(NumpyEncoder, self).default(obj)

app.json_encoder = NumpyEncoder

# --- LÓGICA DE PROCESAMIENTO DE DATOS ---
def parse_timestamp_from_filename(filename):
    """Extrae el timestamp del nombre del archivo."""
    try:
        parts = filename.split('_')
        # Asume formato 'thermal_data_YYYYMMDD_HHMMSS.h5'
        timestamp_str = f"{parts[2]}_{parts[3].split('.')[0]}"
        return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except (IndexError, ValueError):
        # Si falla, retorna la hora actual como respaldo
        return datetime.now()

def process_h5_file(filepath):
    """Lee un archivo H5 y calcula todas las métricas requeridas."""
    with h5py.File(filepath, 'r') as hf:
        if 'temperature_matrix' not in hf:
            return None
        
        temp_matrix = np.array(hf['temperature_matrix'])
        
        # 1. Temperaturas Min, Max y Promedio
        min_temp = np.min(temp_matrix)
        max_temp = np.max(temp_matrix)
        avg_temp = np.mean(temp_matrix)
        
        # 2. Distribución de Temperaturas (se calculará en el frontend con la matriz)
        
        # 3. y 4. Puntos Calientes y Fríos (Coordenadas)
        hot_spot_coords = np.unravel_index(np.argmax(temp_matrix), temp_matrix.shape)
        cold_spot_coords = np.unravel_index(np.argmin(temp_matrix), temp_matrix.shape)

        # 5. Gradientes de Temperatura
        grad_y, grad_x = np.gradient(temp_matrix)
        gradient_magnitude = np.sqrt(grad_y**2 + grad_x**2)
        
        # 6. Áreas de Interés (ROIs) - Ejemplo: píxeles > 95% del máximo
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
    """Hilo que se ejecuta en segundo plano para cargar y actualizar datos."""
    print("Iniciando hilo de carga de datos...")
    while True:
        try:
            h5_files = sorted([f for f in os.listdir(DATA_PATH) if f.endswith('.h5')])
            
            with data_cache['lock']:
                # Comprobar si hay archivos nuevos
                new_files = [f for f in h5_files if f not in data_cache['filenames']]
                
                if new_files:
                    print(f"Nuevos archivos detectados: {new_files}")
                    for filename in new_files:
                        filepath = os.path.join(DATA_PATH, filename)
                        processed_data = process_h5_file(filepath)
                        
                        if processed_data:
                            timestamp = parse_timestamp_from_filename(filename)
                            
                            # Actualizar resumen para la gráfica temporal
                            data_cache['summary'].append({
                                "timestamp": timestamp,
                                "max_temp": processed_data['stats']['max'],
                                "min_temp": processed_data['stats']['min'],
                            })
                            
                            # Guardar detalles para vistas individuales
                            data_cache['details'].append({
                                "filename": filename,
                                **processed_data
                            })
                            data_cache['filenames'].append(filename)

                    # Ordenar por timestamp por si los archivos no se leyeron en orden
                    combined = sorted(zip(data_cache['summary'], data_cache['details']), key=lambda x: x[0]['timestamp'])
                    if combined:
                       data_cache['summary'], data_cache['details'] = zip(*combined)
                       data_cache['summary'] = list(data_cache['summary'])
                       data_cache['details'] = list(data_cache['details'])


        except Exception as e:
            print(f"Error en el hilo de carga de datos: {e}")
        
        time.sleep(REFRESH_INTERVAL_SECONDS)


# --- RUTAS DE LA API Y DE LA PÁGINA ---

@app.route('/')
def index():
    """Sirve la página principal."""
    return render_template('index.html')

@app.route('/api/data/summary')
def get_summary_data():
    """API endpoint para la gráfica temporal."""
    with data_cache['lock']:
        return jsonify(data_cache['summary'])

@app.route('/api/data/detail/<int:index>')
def get_detail_data(index):
    """API endpoint para los datos de un dataset específico."""
    with data_cache['lock']:
        if 0 <= index < len(data_cache['details']):
            return jsonify(data_cache['details'][index])
        else:
            abort(404, description="Dataset no encontrado")

# --- PUNTO DE ENTRADA DE LA APLICACIÓN ---
if __name__ == '__main__':
    # Iniciar el hilo de carga de datos en modo 'daemon' para que se cierre con la app
    loader = threading.Thread(target=data_loader_thread, daemon=True)
    loader.start()
    
    # Iniciar el servidor Flask
    # host='0.0.0.0' lo hace accesible en tu red local
    app.run(host='0.0.0.0', port=5000, debug=True)