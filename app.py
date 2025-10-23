
# ======================================================
# app.py — versión final y estable (Neon + Local, hora Chile 🇨🇱)
# ======================================================

import os
import time
from flask import Flask
from flask_migrate import Migrate
from sqlalchemy.exc import OperationalError
from extensions import db  # ✅ instancia global de SQLAlchemy
from tiempo import hora_actual, to_hora_chile as hora_chile  # ✅ módulo de hora

# ======================================================
# 🚀 Inicialización de la app
# ======================================================
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "clave_secreta_local_cámbiala")

# ======================================================
# 🕒 Registrar funciones globales para Jinja (uso en HTML)
# ======================================================
app.jinja_env.globals.update(hora_actual=hora_actual)
app.jinja_env.filters["hora_chile"] = hora_chile
app.jinja_env.globals.update(hora_chile=hora_chile)

# ======================================================
# ⚙️ Configuración de la base de datos (Neon)
# ======================================================

# 🔗 Cadena directa de conexión Neon (una sola línea, tal como la entrega Neon)
DATABASE_URL = "postgresql+psycopg2://neondb_owner:npg_W6kO3HxNzudU@ep-round-shape-a462zq46-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# 🔁 Compatibilidad Render (por si en el futuro usas su variable de entorno)
env_url = os.getenv("DATABASE_URL")
if env_url and env_url != "":
    DATABASE_URL = env_url.replace("postgres://", "postgresql://", 1)

# Configuración de SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ======================================================
# 🔐 Usuario del sistema (login local)
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
# 🗃️ Crear tablas si no existen (con reintentos)
# ======================================================
with app.app_context():
    for i in range(5):
        try:
            db.create_all()
            print("✅ Base de datos NEON conectada correctamente")
            break
        except OperationalError as e:
            print(f"⚠️ Intento {i+1} fallido al conectar con Neon: {e}")
            time.sleep(5)

# ======================================================
# ▶️ Punto de entrada
# ======================================================
if __name__ == "__main__":
    app.run(debug=True)
