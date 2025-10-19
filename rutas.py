# ======================================================
# rutas.py — versión final y estable (Aitana System)
# ======================================================
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, date, timedelta, time
from sqlalchemy import func
from extensions import db
from modelos import Producto, Venta, MovimientoCaja, Liquidacion, LiquidacionProducto, HistorialInventario
from helpers import (
    obtener_caja_anterior,
    calcular_inventario_total,
    calcular_entrada_inventario,
    caja_base_del_dia
)
import random

# ======================================================
# CONFIGURACIÓN DEL BLUEPRINT
# ======================================================
app_rutas = Blueprint("app_rutas", __name__)

# ======================================================
# 🔒 DECORADOR DE LOGIN
# ======================================================
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("app_rutas.login"))
        return f(*args, **kwargs)
    return wrapper


# ======================================================
# FUNCIONES AUXILIARES INTERNAS
# ======================================================
def _to_float(value):
    """Convierte valores a float, seguros ante cadenas vacías."""
    if value is None or str(value).strip() == "":
        return 0.0
    return float(str(value).strip().replace(",", "."))


def _to_int(value):
    """Convierte valores a int, seguros ante cadenas vacías."""
    if value is None or str(value).strip() == "":
        return 0
    return int(float(str(value).strip().replace(",", ".")))


def generar_codigo_unico(modelo):
    """Genera un código numérico único de 6 dígitos."""
    code = "".join(random.choices("0123456789", k=6))
    while modelo.query.filter_by(codigo=code).first():
        code = "".join(random.choices("0123456789", k=6))
    return code


def day_range(fecha: date):
    """Devuelve rango datetime de inicio y fin de un día."""
    start = datetime.combine(fecha, time.min)
    end = start + timedelta(days=1)
    return start, end


# ======================================================
# 🏠 RUTA PRINCIPAL / INDEX
# ======================================================
@app_rutas.route("/")
@login_required
def index():
    hoy = date.today().isoformat()
    ultima_actualizacion = session.get("ultima_actualizacion")

    # Reiniciar conteo diario si cambió el día
    if ultima_actualizacion != hoy:
        for p in Producto.query.all():
            p.vendidas_dia = 0
            p.valor_vendido_dia = 0.0
            p.fecha = date.today()
        db.session.commit()
        session["ultima_actualizacion"] = hoy

    productos = Producto.query.order_by(Producto.orden.asc(), Producto.id.asc()).all()

    # Reordenar automáticamente
    for idx, p in enumerate(productos, start=1):
        if not p.orden or p.orden != idx:
            p.orden = idx
    db.session.commit()

    # Calcular precios y totales
    for p in productos:
        p.precio_ganancia = (p.valor_unitario or 0) * (1 + (p.interes or 0) / 100)

    total_vendido = sum(p.valor_vendido_dia or 0 for p in productos)

    return render_template("index.html", productos=productos, total_vendido=total_vendido)


# ======================================================
# 📊 DASHBOARD
# ======================================================
@app_rutas.route("/dashboard")
@login_required
def dashboard():
    total_productos = Producto.query.count()
    total_unidades_vendidas = db.session.query(func.sum(Venta.cantidad)).scalar() or 0
    valor_total_vendido = db.session.query(func.sum(Venta.ingreso)).scalar() or 0
    total_movimientos = MovimientoCaja.query.count()
    total_abonos = 0.0
    total_prestamos = 0.0  # 👈 agregado

    return render_template(
        "dashboard.html",
        total_productos=total_productos,
        total_unidades_vendidas=total_unidades_vendidas,
        valor_total_vendido=valor_total_vendido,
        total_movimientos=total_movimientos,
        total_abonos=total_abonos,
        total_prestamos=total_prestamos,  # 👈 agregado
    )

# ======================================================
# 🆕 NUEVO PRODUCTO UNIFICADO (Usado por ambos botones)
# ======================================================
@app_rutas.route("/nuevo_producto", methods=["GET", "POST"])
@login_required
def nuevo_producto():
    from random import randint
    from datetime import datetime

    if request.method == "POST":
        nombre = request.form.get("nombre")
        orden = int(request.form.get("orden") or 0)
        valor_unitario = float(request.form.get("valor_unitario") or 0)
        interes = float(request.form.get("interes") or 0)
        stock_inicial = int(request.form.get("stock_inicial") or 0)

        # Generar código aleatorio
        codigo = str(randint(100000, 999999))

        nuevo = Producto(
            codigo=codigo,
            orden=orden,
            nombre=nombre,
            valor_unitario=valor_unitario,
            interes=interes,
            stock_inicial=stock_inicial,
            unidades_restantes=stock_inicial,
            fecha=date.today()
        )

        db.session.add(nuevo)
        db.session.commit()

        # Registrar entrada inicial en el historial
        if stock_inicial > 0:
            valor_total = stock_inicial * valor_unitario
            historial = HistorialInventario(
                producto_id=nuevo.id,
                cantidad=stock_inicial,
                valor_total=valor_total,
                fecha=datetime.now()
            )
            db.session.add(historial)
            db.session.commit()

        flash(f"✅ Producto '{nombre}' agregado correctamente (Código: {codigo}).", "success")
        return redirect(url_for("app_rutas.entrada_inventario"))

    return render_template("nuevo_producto.html")

# ======================================================
# 💰 REGISTRO DE VENTAS (Versión AJAX)
# ======================================================
# ======================================================
# 🛒 REGISTRAR VENTA (Versión clásica totalmente funcional)
# ======================================================
@app_rutas.route("/vender/<int:producto_id>", methods=["POST"])
@login_required
def vender(producto_id):
    from datetime import datetime, date
    from flask import jsonify, request

    producto = Producto.query.get_or_404(producto_id)

    # ✅ Detectar si viene JSON (desde fetch o llamada AJAX)
    if request.is_json:
        data = request.get_json()
        cantidad = int(data.get("cantidad", 0))
    else:
        try:
            cantidad = int(request.form.get("cantidad", 0))
        except ValueError:
            cantidad = 0

    # 🚫 Validaciones
    if cantidad <= 0:
        mensaje = "Cantidad inválida."
        if request.is_json:
            return jsonify({"success": False, "error": mensaje}), 400
        flash(mensaje, "warning")
        return redirect(url_for("app_rutas.index"))

    if producto.unidades_restantes < cantidad:
        mensaje = "No hay suficientes unidades disponibles."
        if request.is_json:
            return jsonify({"success": False, "error": mensaje}), 400
        flash(mensaje, "danger")
        return redirect(url_for("app_rutas.index"))

    # 🧮 Calcular ingreso con ganancia
    precio_con_ganancia = producto.valor_unitario * (1 + producto.interes / 100)
    ingreso = cantidad * precio_con_ganancia

    # 🔄 Actualizar inventario y ventas del día
    producto.unidades_restantes -= cantidad
    producto.vendidas_dia = (producto.vendidas_dia or 0) + cantidad
    producto.valor_vendido_dia = (producto.valor_vendido_dia or 0) + ingreso
    db.session.add(producto)

    # 💾 Registrar la venta (hora local)
    venta = Venta(
        producto_id=producto.id,
        cantidad=cantidad,
        ingreso=ingreso,
        fecha=datetime.now()
    )
    db.session.add(venta)

    # 💼 Actualizar o crear la liquidación del día
    hoy = date.today()
    liq = Liquidacion.query.filter_by(fecha=hoy).first()
    if not liq:
        liq = Liquidacion(fecha=hoy, entrada=0.0, salida=0.0, caja=0.0, inventario_valor=0.0)
        db.session.add(liq)

    # 🧾 Sumar venta a la caja y entradas
    liq.entrada = (liq.entrada or 0.0) + ingreso
    liq.caja = (liq.caja or 0.0) + ingreso

    # 💾 Guardar los cambios
    db.session.commit()

    # 🌟 Si viene desde AJAX/Fetch (index.html)
    if request.is_json:
        return jsonify({
            "success": True,
            "nombre": producto.nombre,
            "cantidad": cantidad,
            "monto": ingreso,
            "stock": producto.unidades_restantes,
            "vendidas_dia": producto.vendidas_dia,
            "valor_vendido_dia": round(producto.valor_vendido_dia, 2)
        })

    # 🟢 Si es desde formulario normal
    session["resaltado"] = producto.id
    flash(f"Venta registrada: {producto.nombre} ({cantidad} uds, ${ingreso:,.2f}).", "success")
    return redirect(url_for("app_rutas.index"))

# ======================================================
# 📦 ENTRADA DE INVENTARIO
# ======================================================
@app_rutas.route("/entrada_inventario", methods=["GET", "POST"])
@login_required
def entrada_inventario():
    from datetime import datetime, timedelta

    # 🧾 Registrar entrada
    if request.method == "POST":
        codigo = request.form.get("codigo")
        cantidad = int(request.form.get("cantidad", 0))
        producto = Producto.query.filter_by(codigo=codigo).first()

        if not producto:
            flash("❌ No se encontró un producto con ese código.", "danger")
            return redirect(url_for("app_rutas.entrada_inventario"))

        if cantidad <= 0:
            flash("⚠️ La cantidad debe ser mayor a cero.", "warning")
            return redirect(url_for("app_rutas.entrada_inventario"))

        # 📦 Actualizar stock
        producto.unidades_restantes += cantidad

        # 💰 Registrar historial
        valor_total = (producto.valor_unitario or 0) * cantidad
        historial = HistorialInventario(
            producto_id=producto.id,
            cantidad=cantidad,
            valor_total=valor_total,
            fecha=datetime.now()
        )
        db.session.add(historial)

        # 🧹 Eliminar registros antiguos (+90 días)
        limite = datetime.now() - timedelta(days=90)
        HistorialInventario.query.filter(HistorialInventario.fecha < limite).delete()

        db.session.commit()
        flash(f"✅ {cantidad} unidades agregadas a {producto.nombre}.", "success")
        return redirect(url_for("app_rutas.entrada_inventario"))

    # 📋 Mostrar productos e historial
    productos = Producto.query.order_by(Producto.orden.asc()).all()
    limite = datetime.now() - timedelta(days=90)
    historial = HistorialInventario.query.filter(HistorialInventario.fecha >= limite).order_by(HistorialInventario.fecha.desc()).all()

    return render_template("entrada_inventario.html", productos=productos, historial=historial)


# ======================================================
# 📊 LIQUIDACIÓN — Muestra último día o rango de fechas
# ======================================================
@app_rutas.route("/liquidacion", methods=["GET", "POST"])
@login_required
def liquidacion():
    from sqlalchemy import func

    hoy = date.today()
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")

    # ------------------------------------------------------
    # 📆 Si el usuario busca un rango (POST con fechas)
    # ------------------------------------------------------
    if request.method == "POST" and fecha_inicio and fecha_fin:
        try:
            fi = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
            ff = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
        except ValueError:
            flash("❌ Fechas no válidas.", "danger")
            return redirect(url_for("app_rutas.liquidacion"))

        if fi > ff:
            flash("⚠️ La fecha inicial no puede ser mayor que la final.", "warning")
            return redirect(url_for("app_rutas.liquidacion"))

        resultados = []
        total_ingresos = total_ventas = total_salida = 0.0
        caja_final = 0.0

        inventario_total = sum(
            (p.valor_unitario or 0) * (1 + (p.interes or 0) / 100) * (p.unidades_restantes or 0)
            for p in Producto.query.all()
        )

        fecha_actual = fi
        caja_anterior = 0.0

        while fecha_actual <= ff:
            start = datetime.combine(fecha_actual, time.min)
            end = start + timedelta(days=1)

            liq = Liquidacion.query.filter_by(fecha=fecha_actual).first()

            if liq and liq.caja is not None:
                caja_anterior = liq.caja
            elif resultados:
                caja_anterior = resultados[-1]["caja"]

            ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0)) \
                .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

            entradas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
                .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                        MovimientoCaja.tipo == "entrada").scalar() or 0.0

            salidas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
                .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                        MovimientoCaja.tipo.in_(["salida", "gasto"])).scalar() or 0.0

            caja_actual = caja_anterior + ventas_dia + entradas_dia - salidas_dia

            resultados.append({
                "fecha": fecha_actual,
                "ingresos": entradas_dia,
                "caja_anterior": caja_anterior,
                "entrada_efectivo": entradas_dia,
                "ventas_dia": ventas_dia,
                "gastos": 0.0,
                "salida_efectivo": salidas_dia,
                "caja": caja_actual,
                "dia_tasado": 0.0,
                "suma_paquete": inventario_total,
            })

            total_ingresos += entradas_dia
            total_ventas += ventas_dia
            total_salida += salidas_dia
            caja_final = caja_actual

            fecha_actual += timedelta(days=1)

        return render_template(
            "liquidacion.html",
            modo="rango",
            liquidaciones=resultados,
            fecha_inicio=fi,
            fecha_fin=ff,
            total_ingresos=total_ingresos,
            total_ventas=total_ventas,
            total_salida=total_salida,
            caja_inicial=resultados[0]["caja_anterior"] if resultados else 0,
            caja_final=caja_final,
            total_dia_tasado=0.0,
            total_paquete=inventario_total,
            ultima_fecha=ff
        )

    # ------------------------------------------------------
    # 📅 Si no hay rango: mostrar el último día con liquidación
    # ------------------------------------------------------
    ultima_liq = Liquidacion.query.order_by(Liquidacion.fecha.desc()).first()
    ultima_fecha = ultima_liq.fecha if ultima_liq else hoy

    start, end = day_range(ultima_fecha)
    ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0)) \
        .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0
    entradas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                MovimientoCaja.tipo == "entrada").scalar() or 0.0
    salidas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0)) \
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                MovimientoCaja.tipo.in_(["salida", "gasto"])).scalar() or 0.0

    inventario_total = sum(
        (p.valor_unitario or 0) * (1 + (p.interes or 0) / 100) * (p.unidades_restantes or 0)
        for p in Producto.query.all()
    )

    data = [{
        "fecha": ultima_fecha,
        "ingresos": entradas_dia,
        "caja_anterior": ultima_liq.caja if ultima_liq else 0.0,
        "entrada_efectivo": entradas_dia,
        "ventas_dia": ventas_dia,
        "gastos": 0.0,
        "salida_efectivo": salidas_dia,
        "caja": (ultima_liq.caja if ultima_liq else 0) + ventas_dia + entradas_dia - salidas_dia,
        "dia_tasado": 0.0,
        "suma_paquete": inventario_total,
    }]

    return render_template(
        "liquidacion.html",
        modo="ultimo_dia",
        liquidaciones=data,
        fecha_inicio=ultima_fecha,
        fecha_fin=ultima_fecha,
        ultima_fecha=ultima_fecha,
        total_ingresos=entradas_dia,
        total_ventas=ventas_dia,
        total_salida=salidas_dia,
        caja_inicial=ultima_liq.caja if ultima_liq else 0,
        caja_final=data[0]["caja"],
        total_dia_tasado=0.0,
        total_paquete=inventario_total
    )

# ======================================================
# 📆 DETALLE DE VENTAS POR DÍA
# ======================================================
@app_rutas.route("/detalle_ventas/<fecha>")
@login_required
def detalle_ventas(fecha):
    try:
        fecha_dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        flash("❌ Fecha no válida.", "danger")
        return redirect(url_for("app_rutas.liquidacion"))

    start = datetime.combine(fecha_dia, datetime.min.time())
    end = datetime.combine(fecha_dia, datetime.max.time())

    ventas = (
        db.session.query(Venta, Producto)
        .join(Producto, Venta.producto_id == Producto.id)
        .filter(Venta.fecha >= start, Venta.fecha <= end)
        .order_by(Venta.fecha.asc())
        .all()
    )

    total_dia = sum(v.Venta.ingreso for v in ventas) if ventas else 0
    return render_template("detalle_ventas.html", ventas=ventas, fecha=fecha_dia, total_dia=total_dia)

# ======================================================
# 💸 DETALLE DE SALIDAS DE EFECTIVO POR FECHA
# ======================================================
@app_rutas.route("/detalle_salida/<fecha>")
@login_required
def detalle_salida(fecha):
    try:
        fecha_dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        flash("❌ Fecha no válida.", "danger")
        return redirect(url_for("app_rutas.liquidacion"))

    start = datetime.combine(fecha_dia, datetime.min.time())
    end = datetime.combine(fecha_dia, datetime.max.time())

    salidas = (
        MovimientoCaja.query
        .filter(MovimientoCaja.tipo == "salida")
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha <= end)
        .order_by(MovimientoCaja.fecha.asc())
        .all()
    )

    total_salidas = sum(s.monto for s in salidas) if salidas else 0

    return render_template("detalle_salida.html", salidas=salidas, fecha=fecha_dia, total_salidas=total_salidas)

# ======================================================
# 📜 HISTORIAL DE INVENTARIO (últimos 90 días)
# ======================================================
@app_rutas.route("/historial_inventario")
@login_required
def historial_inventario():
    hoy = datetime.now()
    limite = hoy - timedelta(days=90)

    # 🧹 Limpieza automática de registros más antiguos de 90 días
    HistorialInventario.query.filter(HistorialInventario.fecha < limite).delete()
    db.session.commit()

    # 📊 Consultar los últimos 90 días
    historial = (
        db.session.query(HistorialInventario, Producto)
        .join(Producto, HistorialInventario.producto_id == Producto.id)
        .filter(HistorialInventario.fecha >= limite)
        .order_by(HistorialInventario.fecha.desc())
        .all()
    )

    return render_template("historial_inventario.html", historial=historial, hoy=hoy.date())


# ======================================================
# 🎨 CLASES DE COLOR SEGÚN STOCK
# ======================================================
@app_rutas.app_template_global()
def estado_class(producto):
    """
    Devuelve una clase CSS según el estado del stock.
    - Rojo (peligro): sin stock
    - Amarillo (advertencia): 1 a 5 unidades
    - Verde (normal): más de 5 unidades
    """
    if producto.unidades_restantes == 0:
        return "table-danger"
    elif producto.unidades_restantes <= 5:
        return "table-warning"
    return "table-success"


# ======================================================
# 🔐 LOGIN Y LOGOUT
# ======================================================
VALID_USER = "mjesus40"
VALID_PASS = "198409"

@app_rutas.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        contrasena = (request.form.get("contrasena") or "").strip()

        if usuario == VALID_USER.lower() and contrasena == VALID_PASS:
            session["usuario"] = VALID_USER
            flash(f"✅ Bienvenido, {VALID_USER}.", "success")
            return redirect(url_for("app_rutas.index"))

        flash("❌ Usuario o contraseña incorrectos.", "danger")

    return render_template("login.html")


@app_rutas.route("/logout")
def logout():
    session.pop("usuario", None)
    flash("👋 Sesión cerrada correctamente.", "info")
    return redirect(url_for("app_rutas.login"))
