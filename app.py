# ======================================================
# app.py — versión final y estable (hora local Chile 🇨🇱)
# ======================================================

import os
from flask import Flask
from flask_migrate import Migrate
from extensions import db  # ✅ instancia global de SQLAlchemy

# ---------------------------
# ⏰ Importar módulo de tiempo centralizado
# ---------------------------
from tiempo import hora_actual, to_hora_chile as hora_chile  # ✅ desde tiempo.py

# ======================================================
# 🚀 Inicialización de la app
# ======================================================
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "clave_secreta_local_cámbiala")

# ======================================================
# 🕒 Registrar funciones globales para Jinja (uso en HTML)
# ======================================================
# Permite usar hora_actual() y hora_chile() o el filtro |hora_chile en los templates
app.jinja_env.globals.update(hora_actual=hora_actual)
app.jinja_env.filters["hora_chile"] = hora_chile
app.jinja_env.globals.update(hora_chile=hora_chile)  # ✅ añadido: define la función directa

# ======================================================
# ⚙️ Configuración de la base de datos (Render PostgreSQL)
# ======================================================
DB_DEFAULT = (
    "postgresql+psycopg2://almacen_aitana_332s_user:"
    "UH0aEwkoIZXef7j6k3aL8YC8wTHQGWYU@"
    "dpg-d38vaabuibrs73a4mmh0-a.oregon-postgres.render.com/"
    "almacen_aitana_332s"
)

DATABASE_URL = os.getenv("DATABASE_URL", DB_DEFAULT)

# 🔁 Compatibilidad: corregir prefijo en caso de que Render use "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ======================================================
# 🔐 Usuario del sistema
# ======================================================
app.config["VALID_USER"] = "mjesus40"
app.config["VALID_PASS"] = "198409"

# ======================================================
# 🔧 Inicializar extensiones
# ======================================================
db.init_app(app)
migrate = Migrate(app, db)

# ======================================================
# 📦 Modelos y rutas
# ======================================================
from modelos import *          # (Producto, Venta, etc.)
from rutas import app_rutas    # Blueprint principal
app.register_blueprint(app_rutas)

# Asegurar que el blueprint herede la configuración
app_rutas.config = app.config

# ======================================================
# 🚫 Manejador de error 404
# ======================================================
@app.errorhandler(404)
def page_not_found(e):
    from flask import render_template
    return render_template("404.html"), 404

# ======================================================
# 🗃️ Crear tablas si no existen
# ======================================================
with app.app_context():
    db.create_all()

# ======================================================
# ▶️ Punto de entrada
# ======================================================
if __name__ == "__main__":
    app.run(debug=True)
