from datetime import date
from extensions import db
from tiempo import hora_actual  # ✅ Devuelve hora chilena sin tzinfo

# ======================================================
# 🏷️ PRODUCTO
# ======================================================
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    orden = db.Column(db.Integer, nullable=True)
    stock_inicial = db.Column(db.Integer, default=0)
    unidades_restantes = db.Column(db.Integer, default=0)
    valor_unitario = db.Column(db.Float, nullable=False)
    interes = db.Column(db.Float, default=0)
    fecha = db.Column(db.Date, default=date.today)

    vendidas_dia = db.Column(db.Integer, default=0)
    valor_vendido_dia = db.Column(db.Float, default=0.0)

    historial_inventario = db.relationship(
        "HistorialInventario",
        back_populates="producto",
        cascade="all, delete"
    )


# ======================================================
# 💵 VENTA
# ======================================================
class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    ingreso = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime(timezone=False), default=hora_actual)  # ✅ Hora real de Chile (naive)
    producto = db.relationship("Producto", backref="ventas")


# ======================================================
# 💰 MOVIMIENTO DE CAJA
# ======================================================
class MovimientoCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    fecha = db.Column(db.DateTime(timezone=False), default=hora_actual)  # ✅ Hora chilena exacta


# ======================================================
# 📊 LIQUIDACIÓN
# ======================================================
class Liquidacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, unique=True, nullable=False)
    entrada = db.Column(db.Float, default=0.0)
    salida = db.Column(db.Float, default=0.0)
    caja = db.Column(db.Float, default=0.0)
    inventario_valor = db.Column(db.Float, default=0.0)


# ======================================================
# 🧮 LIQUIDACIÓN DE PRODUCTOS
# ======================================================
class LiquidacionProducto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, unique=True, nullable=False)
    caja_anterior = db.Column(db.Float, default=0.0)
    entrada_inventario = db.Column(db.Float, default=0.0)
    salida_efectivo = db.Column(db.Float, default=0.0)
    caja_actual = db.Column(db.Float, default=0.0)
    inventario_total = db.Column(db.Float, default=0.0)


# ======================================================
# 🧾 HISTORIAL DE INVENTARIO
# ======================================================
class HistorialInventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("producto.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    valor_total = db.Column(db.Float, nullable=True)
    fecha = db.Column(db.DateTime(timezone=False), default=hora_actual)  # ✅ Hora chilena real
    producto = db.relationship("Producto", back_populates="historial_inventario")
