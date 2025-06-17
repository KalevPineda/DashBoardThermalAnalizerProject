document.addEventListener('DOMContentLoaded', () => {

    // --- ESTADO GLOBAL ---
    let currentDatasetIndex = 0;
    let totalDatasets = 0;
    const PLOT_BG_COLOR = '#111529';
    const FONT_COLOR = '#f0f0f0';
    const GRID_COLOR = '#370617ff';

    // Paleta de colores para los mapas de calor
    const tempColorScale = [
        [0.0, '#03071e'],
        [0.1, '#370617'],
        [0.3, '#6a040f'],
        [0.5, '#9d0208'],
        [0.7, '#dc2f02'],
        [0.9, '#f48c06'],
        [1.0, '#ffba08']
    ];


    // --- REFERENCIAS A ELEMENTOS DEL DOM ---
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const counterEl = document.getElementById('dataset-counter');
    const filenameEl = document.getElementById('dataset-filename');

    const stats = {
        min: document.getElementById('stats-min'),
        max: document.getElementById('stats-max'),
        avg: document.getElementById('stats-avg'),
    };

    // --- CONFIGURACIÓN GENÉRICA DE PLOTLY ---
    const baseLayout = {
        paper_bgcolor: PLOT_BG_COLOR,
        plot_bgcolor: PLOT_BG_COLOR,
        font: { color: FONT_COLOR, family: 'Roboto Mono' },
        margin: { l: 60, r: 30, b: 50, t: 50, pad: 4 },
    };

    // --- FUNCIONES DE GRAFICACIÓN ---

    async function updateTemporalPlot() {
        try {
            const response = await fetch('/api/data/summary');
            if (!response.ok) throw new Error('Error al cargar datos de resumen');
            const summaryData = await response.json();

            totalDatasets = summaryData.length;
            if (totalDatasets === 0) return;

            const timestamps = summaryData.map(d => d.timestamp);
            const maxTemps = summaryData.map(d => d.max_temp);
            const minTemps = summaryData.map(d => d.min_temp);

            const traceMax = {
                x: timestamps,
                y: maxTemps,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Temp. Máxima',
                line: { color: '#e85d04ff', width: 2 },
                marker: { color: '#ffba08ff' }
            };

            const traceMin = {
                x: timestamps,
                y: minTemps,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Temp. Mínima',
                line: { color: '#9d0208ff', width: 2 },
                marker: { color: '#faa307ff' }
            };

            const layout = {
                ...baseLayout,
                xaxis: { title: 'Tiempo', gridcolor: GRID_COLOR },
                yaxis: { title: 'Temperatura (°C)', gridcolor: GRID_COLOR },
                legend: { x: 0.01, y: 0.99 },
            };

            Plotly.newPlot('temporal-plot', [traceMax, traceMin], layout, {responsive: true});
            updateControls();
            
        } catch (error) {
            console.error("Error en updateTemporalPlot:", error);
        }
    }

    async function updateDetailPlots(index) {
        try {
            const response = await fetch(`/api/data/detail/${index}`);
            if (!response.ok) throw new Error(`Dataset ${index} no encontrado`);
            const detailData = await response.json();
            
            // Actualizar textos y stats
            filenameEl.textContent = detailData.filename;
            stats.min.textContent = `${detailData.stats.min.toFixed(2)} °C`;
            stats.max.textContent = `${detailData.stats.max.toFixed(2)} °C`;
            stats.avg.textContent = `${detailData.stats.avg.toFixed(2)} °C`;

            const tempMatrix = detailData.matrices.temperature;
            
            // 1. Gráfica 3D
            const data3D = [{
                z: tempMatrix,
                type: 'surface',
                colorscale: tempColorScale,
                cmin: detailData.stats.min,
                cmax: detailData.stats.max,
                colorbar: { title: 'Temp °C' }
            }];
            const layout3D = { ...baseLayout, title: 'Superficie de Temperatura 3D' };
            Plotly.react('plot-3d', data3D, layout3D, {responsive: true});

            // 2. Gráfica 2D (Heatmap)
            const data2D = [{
                z: tempMatrix,
                type: 'heatmap',
                colorscale: tempColorScale,
                cmin: detailData.stats.min,
                cmax: detailData.stats.max,
                colorbar: { title: 'Temp °C' }
            }];
            const layout2D = { ...baseLayout, title: 'Mapa de Calor 2D', yaxis: { autorange: 'reversed' } };
            Plotly.react('plot-2d', data2D, layout2D, {responsive: true});

            // 3. Histograma
            const flatTemps = tempMatrix.flat();
            const dataHist = [{
                x: flatTemps,
                type: 'histogram',
                marker: { color: '#f48c06ff' }
            }];
            const layoutHist = { ...baseLayout, title: 'Distribución', xaxis: { title: 'Temperatura (°C)' }, yaxis: { title: 'Frecuencia' }};
            Plotly.react('histogram-plot', dataHist, layoutHist, {responsive: true});

            // 4. Gradiente
            const dataGrad = [{
                z: detailData.matrices.gradient_magnitude,
                type: 'heatmap',
                colorscale: 'Viridis',
                colorbar: { title: 'Magnitud Grad.' }
            }];
            const layoutGrad = { ...baseLayout, title: 'Magnitud del Gradiente', yaxis: { autorange: 'reversed' } };
            Plotly.react('gradient-plot', dataGrad, layoutGrad, {responsive: true});

            // 5. ROI
            const dataROI = [{
                z: detailData.matrices.hot_roi,
                type: 'heatmap',
                colorscale: [[0, PLOT_BG_COLOR], [1, '#ffba08ff']],
                showscale: false
            }];
            const layoutROI = { ...baseLayout, title: 'Zonas Calientes (>95%)', yaxis: { autorange: 'reversed' } };
            Plotly.react('roi-plot', dataROI, layoutROI, {responsive: true});


        } catch (error) {
            console.error("Error en updateDetailPlots:", error);
        }
    }

    // --- MANEJO DE CONTROLES ---
    function updateControls() {
        counterEl.textContent = totalDatasets > 0 ? `${currentDatasetIndex + 1} / ${totalDatasets}` : '0 / 0';
        btnPrev.disabled = currentDatasetIndex <= 0;
        btnNext.disabled = currentDatasetIndex >= totalDatasets - 1;
    }

    btnPrev.addEventListener('click', () => {
        if (currentDatasetIndex > 0) {
            currentDatasetIndex--;
            updateControls();
            updateDetailPlots(currentDatasetIndex);
        }
    });

    btnNext.addEventListener('click', () => {
        if (currentDatasetIndex < totalDatasets - 1) {
            currentDatasetIndex++;
            updateControls();
            updateDetailPlots(currentDatasetIndex);
        }
    });

    // --- INICIALIZACIÓN Y ACTUALIZACIÓN AUTOMÁTICA ---
    async function initialize() {
        await updateTemporalPlot(); // Carga la gráfica principal
        if (totalDatasets > 0) {
            updateDetailPlots(currentDatasetIndex); // Carga los detalles del primer dataset
        }
        updateControls();
    }
    
    initialize();
    
    // Actualiza la gráfica temporal cada 30 segundos
    setInterval(updateTemporalPlot, 30000);
});