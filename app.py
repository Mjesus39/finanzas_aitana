# app.py — versión corregida y estable
import os
from flask import Flask
from flask_migrate import Migrate
from extensions import db   # ✅ usamos la instancia global de extensions.py

# ---------------------------
# Inicialización de la app
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "clave_secreta_local_cámbiala")

# ---------------------------
# Configuración de la base de datos
# ---------------------------
DB_DEFAULT = "postgresql+psycopg2://almacen_aitana_332s_user:UH0aEwkoIZXef7j6k3aL8YC8wTHQGWYU@dpg-d38vaabuibrs73a4mmh0-a.oregon-postgres.render.com/almacen_aitana_332s"
DATABASE_URL = os.getenv("DATABASE_URL", DB_DEFAULT)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------------------
# Usuario del sistema
# ---------------------------
app.config["VALID_USER"] = "mjesus40"
app.config["VALID_PASS"] = "198409"

# ---------------------------
# Inicializar extensiones
# ---------------------------
db.init_app(app)              # ✅ aquí se asocia la base de datos con la app
migrate = Migrate(app, db)

# ---------------------------
# Importar modelos y rutas
# ---------------------------
from modelos import *          # tus modelos (Producto, Venta, etc.)
from rutas import app_rutas    # blueprint de todas las rutas

# Registrar rutas
app.register_blueprint(app_rutas)

# ✅ Asegurar que el blueprint herede la configuración
app_rutas.config = app.config

# ---------------------------
# Errores e inicialización
# ---------------------------
@app.errorhandler(404)
def page_not_found(e):
    from flask import render_template
    return render_template("404.html"), 404

# Crear tablas si no existen
with app.app_context():
    db.create_all()

# ---------------------------
# Punto de entrada
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)
