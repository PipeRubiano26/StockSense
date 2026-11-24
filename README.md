# StockSense

**Predictor inteligente de agotamiento de inventario.** Proyecto universitario: ExpoUNINPAHU, 25 al 28 de noviembre de 2026.

StockSense es una aplicación web para gestionar un inventario (productos, proveedores, ventas, movimientos y órdenes de compra). Con un modelo de **regresión lineal** entrenado con Scikit-learn, **predice la demanda diaria**, estima **cuándo se agotará cada producto**, calcula el **riesgo** según el tiempo de entrega del proveedor, recomienda **cuánto reponer**, genera **alertas** y **compara escenarios** comerciales.

> ⚠️ **Datos sintéticos.** El dataset de entrenamiento y los datos iniciales de la aplicación se generan con Python a partir de reglas comerciales simuladas y semillas reproducibles. Los resultados son un **experimento académico**, no un modelo validado con ventas reales.

## Objetivo

Ayudar a decidir **cuándo y cuánto reponer** mediante predicciones reales de un modelo entrenado. No hay respuestas precargadas: cada predicción se calcula en vivo con `models/demand_model.joblib`.

## Funcionalidades

| Módulo | Qué hace |
|---|---|
| Dashboard | Productos, unidades disponibles, stock bajo, alertas activas, demanda estimada a 7 días (modelo), mayor rotación, gráficos de ventas, inventario y riesgo |
| Inventario | CRUD de productos, búsqueda por nombre o categoría, filtro por nivel de stock, movimientos (entradas y ajustes) y órdenes de compra |
| Ventas | Registro con control de existencias (no permite vender más de lo disponible), historial filtrable por producto y fecha |
| Proveedores | CRUD, tiempos de entrega, pedidos pendientes y retrasados, asociación de productos |
| Predicciones | Historial y pronóstico, unidades estimadas, fecha de agotamiento, riesgo, reposición recomendada y **factores** que explican la predicción |
| Simulador | Escenarios normal, promoción, alta demanda, baja demanda y retraso del proveedor, con gráficos comparativos y supuestos visibles |
| Alertas | Stock bajo, próximos a agotarse, agotamiento antes de reponer, reposición requerida y retrasos de proveedores |

## Tecnologías

Python 3.12 · Flask 3.1 · Flask-SQLAlchemy 3.1 · SQLite · Docker · Kubernetes (minikube) · Gunicorn · Scikit-learn 1.9 · Pandas · NumPy · Joblib · Jupyter · Matplotlib · Seaborn · HTML5 · CSS3 · JavaScript · Bootstrap 5.3 · Chart.js 4.4 · pytest

Bootstrap, sus íconos y Chart.js están incluidos en `static/vendor/`: **la aplicación funciona sin internet**.

## Arquitectura

Aplicación monolítica en capas (sin microservicios):

```
Navegador (Jinja2 + JS + Chart.js)
        │ HTTP / JSON
Flask: routes/ (blueprints) ──▶ services/ (inventario, predicción, escenarios, alertas, validación)
        │                                   │
Flask-SQLAlchemy ──▶ SQLite (stocksense.db)  └──▶ Pipeline Scikit-learn (models/demand_model.joblib)

Jupyter (offline): dataset sintético ──▶ entrenamiento ──▶ demand_model.joblib + model_metadata.json
```

El modelo se **entrena solo en el notebook**. Flask lo **carga una vez** al iniciar y nunca lo reentrena. Los diagramas C4 y UML y su explicación están en [`docs/documento_tecnico.md`](docs/documento_tecnico.md).

## Estructura de carpetas

```
StockSense/
├── app.py                  # create_app(): carga del modelo, blueprints, comando init-db
├── config.py               # rutas de la BD y del modelo, parámetros de negocio
├── requirements.txt
├── pytest.ini
├── database/               # models.py (6 tablas) y seed.py (datos iniciales)
├── ml/                     # simulación, generador del dataset, variables y pronóstico recursivo
├── models/                 # demand_model.joblib y model_metadata.json (generados por el notebook)
├── services/               # lógica de negocio
├── routes/                 # blueprints Flask
├── templates/  static/     # interfaz web (static/vendor: Bootstrap y Chart.js locales)
├── notebooks/              # StockSense_Model_Training.ipynb
├── data/                   # synthetic_sales.csv (35 000 registros)
├── tests/                  # pruebas pytest (79)
├── Dockerfile              # imagen para Kubernetes
├── k8s/                    # manifiestos de Kubernetes y scripts .bat
└── docs/                   # documento técnico, diagramas PlantUML, imágenes, resultados de pruebas
```

## Requisitos previos

* Windows 10/11
* **Python 3.12** (probado con 3.12.1). Verifique con `py -3.12 --version`.
* Un navegador moderno (Chrome, Edge o Firefox)

## Instalación (Windows)

Descargue el proyecto (requiere [Git](https://git-scm.com/download/win)) o use *Code › Download ZIP* en GitHub:

```powershell
git clone https://github.com/PipeRubiano26/StockSense.git
cd StockSense
```

Luego, en **PowerShell** dentro de la carpeta del proyecto:

```powershell
# 1. Crear el entorno virtual
py -3.12 -m venv .venv

# 2. Activarlo
.\.venv\Scripts\Activate.ps1
#    Si PowerShell bloquea el script, ejecute una vez:
#    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#    En cmd.exe use:  .venv\Scripts\activate.bat

# 3. Instalar dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Generación del dataset

```powershell
python -m ml.generate_dataset
# Dataset generado: 35,000 registros -> data\synthetic_sales.csv
```

Es reproducible (semilla 42). Con `--seed N` se genera otra muestra. El notebook también puede generarlo si el archivo no existe.

## Ejecución del notebook y exportación del modelo

El repositorio ya incluye el modelo entrenado. Para volver a entrenarlo:

```powershell
# Opción A: interactiva
jupyter notebook notebooks/StockSense_Model_Training.ipynb
#   Menú: Run > Run All Cells

# Opción B: ejecución completa sin interfaz (guarda las salidas en el notebook)
jupyter nbconvert --to notebook --execute --inplace notebooks/StockSense_Model_Training.ipynb
```

Al terminar, el notebook escribe **`models/demand_model.joblib`** (Pipeline: interacciones + escalado + OneHot + regresión lineal) y **`models/model_metadata.json`** (fecha, versión, variables, métricas y dataset).

## Inicialización de la base de datos

La primera vez que se inicia la aplicación se crea `stocksense.db` y se cargan los datos iniciales: 20 productos, 5 proveedores y 12 meses de ventas que terminan el día anterior. **No se duplican** en los siguientes arranques.

```powershell
# Crear/cargar manualmente (no duplica si ya hay datos)
flask --app app init-db

# Borrar todo y volver a cargar los datos iniciales
flask --app app init-db --reset
```

> **Antes de la demostración:** ejecute `flask --app app init-db --reset` el mismo día de la Expo. Así el historial termina "ayer" y las predicciones parten de ventas recientes.

## Ejecución de Flask

La forma más fácil es hacer doble clic en **`iniciar_stocksense.bat`**, que usa el Python de `.venv` sin activarlo. Para reiniciar los datos, use `reiniciar_datos.bat`.

Desde la consola, con el entorno activo:

```powershell
python app.py
```

> En **cmd** el entorno se activa con `.venv\Scripts\activate.bat`. `Activate.ps1` solo funciona en PowerShell.

Abra **http://127.0.0.1:5000**. La consola debe mostrar `Modelo cargado: versión 1.0.0`. Si falta el archivo del modelo, la aplicación funciona igual (CRUD) y muestra un aviso para ejecutar el notebook.

## Despliegue en Kubernetes (caídas y autorrecuperación)

StockSense también corre en un clúster **Kubernetes local (minikube)** con **2 réplicas**. Kubernetes las vigila con sondas de salud, reinicia las que se caen o se cuelgan y solo envía tráfico a las que están sanas. La base SQLite vive en un volumen persistente.

**Requisitos:** Docker Desktop **abierto**, minikube y kubectl. Todos los scripts están en `k8s\`:

| Script | Qué hace |
|---|---|
| `k8s\desplegar.bat` | Inicia minikube si hace falta, construye la imagen, la carga y aplica los manifiestos (`kubectl apply -k k8s`) |
| `k8s\abrir_app.bat` | Abre la app en el navegador (deje la ventana abierta: es el túnel) |
| `k8s\ver_pods.bat` | Muestra los pods en tiempo real |
| `k8s\demo_fallas.bat` | Menú para provocar fallas: eliminar un pod, tumbar el proceso o colgar la app |
| `k8s\reiniciar_datos.bat` | Reinicia los datos dentro del clúster (el día de la Expo) |
| `k8s\eliminar.bat` | Elimina el despliegue |

Resultado medido con fallas reales: **427 de 431 peticiones correctas (99.1 %)** mientras se eliminaba un pod, se tumbaba un proceso y se colgaba una réplica. Ver [`docs/resultados_kubernetes.txt`](docs/resultados_kubernetes.txt) y la sección 12 del documento técnico.

## Ejecución de pruebas

```powershell
python -m pytest           # resumen
python -m pytest -v        # detalle por prueba
```

Resultado actual: **79 pruebas aprobadas**. Ver [`docs/resultados_pruebas.txt`](docs/resultados_pruebas.txt). Las pruebas usan SQLite en memoria y no modifican `stocksense.db`.

## Guion de la demostración en vivo

| # | Paso | Dónde | Qué mostrar |
|---|---|---|---|
| 1 | Iniciar la aplicación | `python app.py` | Mensaje *Modelo cargado* (no entrena) |
| 2 | Dashboard | `/` | Indicadores, demanda estimada por el modelo, gráficos |
| 3 | Registrar un producto | Inventario › Nuevo producto | Validaciones (probar un precio negativo) y registro |
| 4 | Registrar una venta | Ventas › Registrar venta | Intentar vender más del stock (se rechaza) y luego una venta válida |
| 5 | Inventario actualizado | Inventario › detalle del producto | Stock descontado y movimiento de salida |
| 6 | Seleccionar un producto | Predicciones | p. ej. *Leche entera 1 L* |
| 7 | Ejecutar una predicción | Botón *Generar predicción* | Cálculo en vivo con el `.joblib` |
| 8 | Estimación de demanda | Tarjetas y gráfico | Demanda de hoy, 7 y 30 días; tabla de factores |
| 9 | Fecha de agotamiento | Tarjetas y proyección de stock | Fecha, días, riesgo y reposición recomendada |
| 10 | Modificar el simulador | Simulador | Mover descuento, demanda y retraso |
| 11 | Comparar escenarios | Tarjetas y gráficos | *Modelo* vs. *modelo + supuesto* |
| 12 | Alertas de reposición | Alertas | Crear una orden con la cantidad recomendada |

## Diagramas

Las fuentes PlantUML están en `docs/diagrams/`: `c4_context`, `c4_containers`, `c4_components`, `deployment_k8s`, `sequence_inference` y `activity_system`. Para obtener las imágenes:

* **VS Code:** instale la extensión *PlantUML* (jebbs.plantuml), abra el `.puml` y pulse `Alt+D`; o exporte con *PlantUML: Export Current Diagram*.
* **Línea de comandos:** descargue `plantuml.jar` desde https://plantuml.com/download y ejecute
  `java -jar plantuml.jar -tpng -charset UTF-8 docs/diagrams/*.puml -o ../images`

Los diagramas C4 usan la biblioteca C4-PlantUML incluida en PlantUML (`!include <C4/...>`) y el motor de diseño `smetana`, por lo que no necesitan Graphviz.

## Documentación

* [`docs/documento_tecnico.md`](docs/documento_tecnico.md): stack y justificación, C4, UML, modelo de datos, modelo de IA con métricas reales, agotamiento, escenarios, alertas, pruebas y limitaciones.
* [`notebooks/StockSense_Model_Training.ipynb`](notebooks/StockSense_Model_Training.ipynb): entrenamiento completo con salidas.
* [`models/model_metadata.json`](models/model_metadata.json): métricas y detalles del entrenamiento.

**Métricas del modelo (conjunto de prueba temporal, sep–dic 2025):** MAE 6.63 · RMSE 11.84 · R² 0.819 (datos sintéticos).
