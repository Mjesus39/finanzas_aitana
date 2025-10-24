# ======================================================
# helpers.py — versión final y sincronizada con tiempo.py 🇨🇱
# ======================================================

from datetime import date, datetime, timedelta  # ✅ agregado timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from extensions import db
from modelos import Producto, Venta, MovimientoCaja, Liquidacion, HistorialInventario

# ⏰ Importar funciones de hora desde tiempo.py
from tiempo import hora_actual, day_range

# ======================================================
# 💼 CAJA ANTERIOR
# ======================================================
def obtener_caja_anterior(fecha: date) -> float:
    """Obtiene la caja del día anterior desde la tabla Liquidacion."""
    dia_anterior = fecha - timedelta(days=1)
    liq_anterior = Liquidacion.query.filter_by(fecha=dia_anterior).first()
    return float(liq_anterior.caja) if liq_anterior else 0.0


# ======================================================
# 📦 INVENTARIO TOTAL (CON INTERÉS)
# ======================================================
def calcular_inventario_total() -> float:
    """Calcula el valor total del inventario actual con ganancia."""
    total_preciso = Decimal("0.00")
    productos = Producto.query.all()

    for p in productos:
        unidades = Decimal(str(p.unidades_restantes or 0))
        valor = Decimal(str(p.valor_unitario or 0))
        interes = Decimal(str(p.interes or 0))
        subtotal = unidades * valor * (Decimal("1") + interes / Decimal("100"))
        total_preciso += subtotal

    return float(total_preciso.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ======================================================
# 📈 ENTRADA DE INVENTARIO
# ======================================================
def calcular_entrada_inventario(fecha: date) -> float:
    """Calcula el valor total de entradas de inventario registradas en el día (hora Chile)."""
    start, end = day_range(fecha)
    total = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.tipo == "entrada") \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end) \
        .scalar() or 0.0
    return float(total)


# ======================================================
# 💰 CAJA BASE DEL DÍA
# ======================================================
def caja_base_del_dia(fecha: date):
    """Devuelve la base de caja (ventas + entradas - salidas - gastos + caja anterior)."""
    start, end = day_range(fecha)
    caja_anterior = obtener_caja_anterior(fecha)

    # 🟢 Ventas del día
    ventas = (
        db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))
        .filter(Venta.fecha >= start, Venta.fecha < end)
        .scalar() or 0.0
    )

    # 💰 Entradas
    entradas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo == "entrada")
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar() or 0.0
    )

    # 💸 Salidas + Gastos
    salidas = (
        db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]))
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)
        .scalar() or 0.0
    )

    # 🧮 Caja total
    return float(caja_anterior + ventas + entradas - salidas)


# ======================================================
# 🔁 RESETEAR VENTAS DIARIAS
# ======================================================
def resetear_ventas_dia():
    """Reinicia las ventas diarias si cambió el día."""
    hoy = hora_actual().date()  # 👈 ajustado a hora Chile
    for producto in Producto.query.all():
        if getattr(producto, "fecha", None) != hoy:
            producto.vendidas_dia = 0
            producto.valor_vendido_dia = 0
            producto.fecha = hoy
    db.session.commit()


# ======================================================
# 🧮 FUNCIONES DE APOYO
# ======================================================
def _to_float(value):
    """Convierte un valor a float de forma segura (acepta coma o punto)."""
    if value is None or str(value).strip() == "":
        return 0.0
    return float(str(value).strip().replace(",", "."))


def _to_int(value):
    """Convierte un valor a entero de forma segura."""
    if value is None or str(value).strip() == "":
        return 0
    return int(float(str(value).strip().replace(",", ".")))

# ======================================================
# 🎨 FUNCIÓN VISUAL PARA CLASES CSS DE PRODUCTOS
# ======================================================
def estado_class(producto):
    """Devuelve una clase CSS según el stock restante."""
    if producto.unidades_restantes <= 0:
        return "table-danger"  # 🔴 Sin stock
    elif producto.unidades_restantes <= 5:
        return "table-warning"  # 🟡 Pocas unidades
    else:
        return "table-success"  # 🟢 Disponible

# ======================================================
# 🔁 RESETEAR VENTAS DIARIAS (versión robusta, hora Chile)
# ======================================================
from tiempo import local_date  # 👈 asegúrate de tener esto arriba

def resetear_ventas_dia():
    """Reinicia las ventas diarias si cambió el día (según hora local Chile)."""
    hoy = local_date()  # ✅ Fecha local de Chile
    cambios = 0

    for producto in Producto.query.all():
        if getattr(producto, "fecha", None) != hoy:
            producto.vendidas_dia = 0
            producto.valor_vendido_dia = 0
            producto.fecha = hoy
            cambios += 1

    if cambios > 0:
        db.session.commit()
        print(f"🔄 Ventas diarias reiniciadas para {cambios} productos ({hoy})")

