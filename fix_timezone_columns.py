# ======================================================
# fix_timezone_columns.py — Corrige columnas datetime sin zona horaria
# ======================================================
from app import app  # 👈 Importamos la app principal
from extensions import db

with app.app_context():
    print("⏳ Corrigiendo columnas de fecha en la base de datos...")

    with db.engine.connect() as conn:
        conn.execute(db.text("""
            ALTER TABLE venta
            ALTER COLUMN fecha TYPE timestamptz
            USING fecha AT TIME ZONE 'America/Santiago';
        """))
        conn.execute(db.text("""
            ALTER TABLE movimiento_caja
            ALTER COLUMN fecha TYPE timestamptz
            USING fecha AT TIME ZONE 'America/Santiago';
        """))
        conn.execute(db.text("""
            ALTER TABLE historial_inventario
            ALTER COLUMN fecha TYPE timestamptz
            USING fecha AT TIME ZONE 'America/Santiago';
        """))
        conn.commit()

    print("✅ Conversiones completadas correctamente.")
    print("Las columnas ahora usan TIMESTAMP WITH TIME ZONE (Chile).")
