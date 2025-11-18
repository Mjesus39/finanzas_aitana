# ======================================================
# rutas.py — versión FINAL (Aitana System, hora Chile 🇨🇱)
# ======================================================
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import date, timedelta, datetime, time
from sqlalchemy import func
from extensions import db
from modelos import Producto, Venta, MovimientoCaja, Liquidacion, LiquidacionProducto, HistorialInventario
from helpers import (
    obtener_caja_anterior,
    calcular_inventario_total,
    calcular_entradas,        # ✅ reemplaza calcular_entrada_inventario
    calcular_salidas,         # ✅ agrega esta para salidas de efectivo
    caja_base_del_dia,
    estado_class              # ✅ para los colores de stock
)
import random

# ⏰ Importaciones horarias (incluye to_hora_chile para formatear fechas)
from tiempo import hora_actual, day_range, local_date, to_hora_chile


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
# 🌎 HORA LOCAL (Chile)
# ======================================================
def hora_chile():
    """Alias para compatibilidad con plantillas antiguas."""
    return hora_actual()

# ======================================================
# FUNCIONES AUXILIARES INTERNAS
# ======================================================
def _to_float(value):
    if value is None or str(value).strip() == "":
        return 0.0
    return float(str(value).strip().replace(",", "."))

def _to_int(value):
    if value is None or str(value).strip() == "":
        return 0
    return int(float(str(value).strip().replace(",", ".")))

def generar_codigo_unico(modelo):
    code = "".join(random.choices("0123456789", k=6))
    while modelo.query.filter_by(codigo=code).first():
        code = "".join(random.choices("0123456789", k=6))
    return code

# ======================================================
# 🏠 INDEX — Reinicio diario real (sin depender de session)
# ======================================================
@app_rutas.route("/")
@login_required
def index():
    hoy = local_date()  # ✅ Fecha local Chile

    # 🔄 Reiniciar valores diarios si el producto tiene una fecha anterior
    productos = Producto.query.all()
    cambios = 0
    for p in productos:
        if p.fecha != hoy:
            p.vendidas_dia = 0
            p.valor_vendido_dia = 0.0
            p.fecha = hoy
            cambios += 1

    if cambios > 0:
        db.session.commit()
        print(f"🔁 Ventas diarias reiniciadas para {cambios} productos ({hoy})")

    # 🔁 Sincronizar ventas reales del día actual
    start, end = day_range(hoy)
    for p in productos:
        ventas_dia = Venta.query.filter(
            Venta.producto_id == p.id,
            Venta.fecha >= start,
            Venta.fecha < end
        ).all()
        p.vendidas_dia = sum(v.cantidad for v in ventas_dia)
        p.valor_vendido_dia = sum(v.ingreso for v in ventas_dia)
    db.session.commit()

    # 🔢 Reordenar productos
    productos = Producto.query.order_by(Producto.orden.asc(), Producto.id.asc()).all()
    for idx, p in enumerate(productos, start=1):
        if not p.orden or p.orden != idx:
            p.orden = idx
    db.session.commit()

    # 💰 Calcular precios con ganancia
    for p in productos:
        p.precio_ganancia = (p.valor_unitario or 0) * (1 + (p.interes or 0) / 100)

    total_vendido = sum(p.valor_vendido_dia or 0 for p in productos)

    # 🧾 Renderizar plantilla
    return render_template(
        "index.html",
        productos=productos,
        total_vendido=total_vendido,
        estado_class=estado_class
    )

# ======================================================
# ✏️ ACTUALIZAR NOMBRE Y/O PRECIO DE PRODUCTO — versión robusta final
# ======================================================
@app_rutas.route("/actualizar_producto/<int:producto_id>", methods=["POST"])
@login_required
def actualizar_producto(producto_id):
    try:
        data = request.get_json() or {}
        nuevo_precio = data.get("precio")
        nuevo_nombre = data.get("nombre", "").strip() if data.get("nombre") else None

        # 🔍 Buscar producto
        producto = Producto.query.get(producto_id)
        if not producto:
            return jsonify({
                "success": False,
                "error": "❌ Producto no encontrado."
            }), 404

        # 💰 Actualizar precio (solo si se envió)
        if nuevo_precio is not None:
            try:
                nuevo_precio = float(nuevo_precio)
                if nuevo_precio <= 0:
                    return jsonify({
                        "success": False,
                        "error": "⚠️ El precio debe ser mayor que cero."
                    }), 400
                producto.valor_unitario = round(
                    nuevo_precio / (1 + (producto.interes or 0) / 100), 2
                )
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": "⚠️ Precio inválido."
                }), 400

        # 🏷️ Actualizar nombre (solo si se envió)
        if nuevo_nombre:
            producto.nombre = nuevo_nombre

        # ⚠️ Si no se envió ni nombre ni precio
        if nuevo_precio is None and not nuevo_nombre:
            return jsonify({
                "success": False,
                "error": "⚠️ No se proporcionaron datos para actualizar."
            }), 400

        db.session.commit()

        # ✅ Éxito
        return jsonify({
            "success": True,
            "id": producto.id,
            "nombre": producto.nombre,
            "nuevo_precio": round(nuevo_precio, 2) if nuevo_precio else None,
            "mensaje": f"✅ Producto '{producto.nombre}' actualizado correctamente."
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"❌ Error interno: {str(e)}"
        }), 500


# ======================================================
# 📋 Detalle de ventas de HOY por producto (JSON para el modal)
# ======================================================
@app_rutas.route("/detalle_ventas_producto/<int:producto_id>", methods=["GET"])
@login_required
def detalle_ventas_producto(producto_id):
    from tiempo import to_hora_chile  # ✅ Importar aquí para evitar errores circulares

    producto = Producto.query.get_or_404(producto_id)

    # 🕒 Rango del día actual según hora Chile
    hoy = local_date()
    start, end = day_range(hoy)

    ventas = (
        Venta.query
        .filter(
            Venta.producto_id == producto.id,
            Venta.fecha >= start,
            Venta.fecha < end
        )
        .order_by(Venta.fecha.desc())
        .all()
    )

    data = []
    for v in ventas:
        data.append({
            "id": v.id,
            "cantidad": int(v.cantidad),
            "ingreso": float(v.ingreso),
            "fecha_iso": v.fecha.isoformat(),
            "fecha_chile": to_hora_chile(v.fecha)  # ✅ ahora sí definida correctamente
        })

    return jsonify({
        "success": True,
        "producto": {
            "id": producto.id,
            "codigo": producto.codigo,
            "nombre": producto.nombre,
        },
        "ventas": data
    })


# ======================================================
# 🗑️ ELIMINAR ENTRADA DE HISTORIAL DE INVENTARIO
# ======================================================
@app_rutas.route("/eliminar_entrada_inventario/<int:entrada_id>", methods=["DELETE"])
@login_required
def eliminar_entrada_inventario(entrada_id):
    try:
        entrada = HistorialInventario.query.get_or_404(entrada_id)

        # 🔁 Restaurar el stock restando la cantidad ingresada en esa entrada
        producto = entrada.producto
        if producto:
            producto.unidades_restantes = max(producto.unidades_restantes - entrada.cantidad, 0)

        db.session.delete(entrada)
        db.session.commit()

        return jsonify({"success": True, "message": "Entrada eliminada correctamente."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


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
    total_abonos = total_prestamos = 0.0

    # ✅ Calculamos el inventario total desde helpers
    inventario_total = calcular_inventario_total() or 0

    return render_template(
        "dashboard.html",
        total_productos=total_productos,
        total_unidades_vendidas=total_unidades_vendidas,
        valor_total_vendido=valor_total_vendido,
        total_movimientos=total_movimientos,
        total_abonos=total_abonos,
        total_prestamos=total_prestamos,
        inventario_total=inventario_total  # ✅ se pasa como valor
    )

# ======================================================
# 🆕 NUEVO PRODUCTO — versión optimizada (rápida + AJAX)
# ======================================================
@app_rutas.route("/nuevo_producto", methods=["GET", "POST"])
@login_required
def nuevo_producto():
    if request.method == "POST":
        try:
            nombre = request.form.get("nombre", "").strip().upper()
            orden = int(request.form.get("orden") or 0)
            valor_unitario = float(request.form.get("valor_unitario") or 0)
            interes = float(request.form.get("interes") or 0)
            stock_inicial = int(request.form.get("stock_inicial") or 0)
            codigo = generar_codigo_unico(Producto)

            nuevo = Producto(
                codigo=codigo,
                orden=orden,
                nombre=nombre,
                valor_unitario=valor_unitario,
                interes=interes,
                stock_inicial=stock_inicial,
                unidades_restantes=stock_inicial,
                fecha=local_date(),
            )
            db.session.add(nuevo)
            db.session.commit()

            if stock_inicial > 0:
                valor_total = stock_inicial * valor_unitario
                historial = HistorialInventario(
                    producto_id=nuevo.id,
                    cantidad=stock_inicial,
                    valor_total=valor_total,
                    fecha=hora_actual(),
                )
                db.session.add(historial)
                db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "success": True,
                    "id": nuevo.id,
                    "codigo": nuevo.codigo,
                    "nombre": nuevo.nombre,
                    "precio": round(nuevo.valor_unitario * (1 + nuevo.interes / 100), 2),
                    "stock": nuevo.unidades_restantes
                })

            flash(f"✅ Producto '{nombre}' agregado correctamente (Código: {codigo}).", "success")
            return redirect(url_for("app_rutas.entrada_inventario", _anchor=f"producto-{nuevo.id}"))

        except Exception as e:
            db.session.rollback()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": False, "error": str(e)}), 500

            flash(f"❌ Error al agregar producto: {e}", "danger")
            return redirect(url_for("app_rutas.entrada_inventario"))

    return render_template("nuevo_producto.html")


# ======================================================
# 🛒 REGISTRAR VENTA (versión robusta)
# ======================================================
@app_rutas.route("/vender/<int:producto_id>", methods=["POST"])
@login_required
def vender(producto_id):
    try:
        producto = Producto.query.get_or_404(producto_id)
        if request.is_json:
            data = request.get_json(silent=True) or {}
            cantidad = int(float(str(data.get("cantidad", "0")).replace(",", ".")))
        else:
            cantidad = int(float(str(request.form.get("cantidad", "0")).replace(",", ".")))
        if cantidad <= 0:
            return jsonify({"success": False, "error": "Cantidad inválida."}), 400

        valor_unitario = float(producto.valor_unitario or 0)
        interes = float(producto.interes or 0)
        stock = int(producto.unidades_restantes or 0)
        if stock < cantidad:
            return jsonify({"success": False, "error": "No hay suficiente stock."}), 400

        ingreso = round(cantidad * (valor_unitario * (1 + interes / 100)), 2)
        producto.unidades_restantes = stock - cantidad
        producto.vendidas_dia = int(producto.vendidas_dia or 0) + cantidad
        producto.valor_vendido_dia = round(float(producto.valor_vendido_dia or 0) + ingreso, 2)
        db.session.add(producto)

        venta = Venta(producto_id=producto.id, cantidad=cantidad, ingreso=ingreso, fecha=hora_actual())
        db.session.add(venta)

        hoy_cl = local_date()
        liq = Liquidacion.query.filter_by(fecha=hoy_cl).first()
        if not liq:
            liq = Liquidacion(fecha=hoy_cl, entrada=0.0, salida=0.0, caja=0.0, inventario_valor=0.0)
            db.session.add(liq)
        liq.entrada = round(float(liq.entrada or 0) + ingreso, 2)
        liq.caja = round(float(liq.caja or 0) + ingreso, 2)
        db.session.commit()

        return jsonify({
            "success": True,
            "nombre": producto.nombre,
            "cantidad": cantidad,
            "monto": ingreso,
            "stock": producto.unidades_restantes,
            "vendidas_dia": producto.vendidas_dia,
            "valor_vendido_dia": producto.valor_vendido_dia
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Ocurrió un error al vender: {str(e)}"}), 500

# ======================================================
# 🗑 ELIMINAR VENTA (desde el modal) — versión corregida con caja ajustada
# ======================================================
@app_rutas.route("/eliminar_venta/<int:venta_id>", methods=["POST"])
@login_required
def eliminar_venta(venta_id):
    try:
        venta = Venta.query.get_or_404(venta_id)
        producto = venta.producto

        # 🔙 Revertir inventario y totales del día
        producto.unidades_restantes += venta.cantidad
        producto.vendidas_dia = max(0, (producto.vendidas_dia or 0) - venta.cantidad)
        producto.valor_vendido_dia = max(0.0, (producto.valor_vendido_dia or 0) - venta.ingreso)

        # 💰 Eliminar movimiento de caja (si existía)
        movimiento = MovimientoCaja.query.filter_by(
            tipo="entrada", descripcion=f"Venta: {producto.nombre}", monto=venta.ingreso
        ).first()
        if movimiento:
            db.session.delete(movimiento)

        # 💼 Ajustar liquidación del día actual
        hoy = local_date()
        liq = Liquidacion.query.filter_by(fecha=hoy).first()
        if liq:
            liq.entrada = max((liq.entrada or 0) - venta.ingreso, 0)
            liq.caja = max((liq.caja or 0) - venta.ingreso, 0)
        else:
            # Si no hay liquidación, la creamos solo por coherencia
            liq = Liquidacion(fecha=hoy, entrada=0.0, salida=0.0, caja=0.0)
            db.session.add(liq)

        # 🗑 Eliminar la venta
        db.session.delete(venta)
        db.session.commit()

        return jsonify({
            "success": True,
            "stock": producto.unidades_restantes,
            "vendidas_dia": producto.vendidas_dia,
            "valor_vendido_dia": producto.valor_vendido_dia
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# ======================================================
# 💸 SALIDA DE CAJA (corregido)
# ======================================================
@app_rutas.route("/caja_salida", methods=["POST"])
@login_required
def caja_salida():
    descripcion = request.form.get("descripcion", "").strip()
    monto = float(request.form.get("monto") or 0)

    if monto <= 0:
        flash("⚠️ El monto debe ser mayor que cero.", "warning")
        return redirect(url_for("app_rutas.liquidacion"))

    # Registrar el movimiento
    salida = MovimientoCaja(
        tipo="salida",
        monto=monto,
        descripcion=descripcion or "Salida manual de caja",
        fecha=hora_actual()
    )
    db.session.add(salida)

    # Actualizar o crear la liquidación del día
    hoy = local_date()
    liq = Liquidacion.query.filter_by(fecha=hoy).first()
    if not liq:
        liq = Liquidacion(fecha=hoy, entrada=0.0, salida=0.0, caja=0.0)
        db.session.add(liq)

    # ✅ Solo actualizamos la salida, NO tocamos la caja aquí
    liq.salida = (liq.salida or 0) + monto

    db.session.commit()

    flash(f"💸 Salida de caja registrada: ${monto:,.2f}", "info")
    return redirect(url_for("app_rutas.liquidacion"))

# ======================================================
# 🗑️ ELIMINAR SALIDA DE CAJA
# ======================================================
@app_rutas.route("/eliminar_salida/<int:salida_id>", methods=["POST"])
@login_required
def eliminar_salida(salida_id):
    salida = MovimientoCaja.query.get_or_404(salida_id)

    # Solo eliminamos si el tipo es "salida"
    if salida.tipo != "salida":
        flash("⚠️ Solo se pueden eliminar movimientos de tipo salida.", "warning")
        return redirect(url_for("app_rutas.liquidacion"))

    # Actualizamos la liquidación correspondiente
    hoy = salida.fecha.date()
    liq = Liquidacion.query.filter_by(fecha=hoy).first()
    if liq:
        liq.salida = max((liq.salida or 0) - salida.monto, 0)
        # ⚠️ No modificamos liq.caja manualmente
    db.session.delete(salida)
    db.session.commit()

    flash(f"🗑️ Salida de caja eliminada correctamente (${salida.monto:,.2f})", "success")
    return redirect(url_for("app_rutas.liquidacion"))


# ======================================================
# 📅 DETALLE DE VENTAS POR DÍA
# ======================================================
@app_rutas.route("/detalle_ventas/<fecha>")
@login_required
def detalle_ventas(fecha):
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        start, end = day_range(fecha_obj)

        ventas = Venta.query.filter(Venta.fecha >= start, Venta.fecha < end).all()
        total_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0)) \
            .filter(Venta.fecha >= start, Venta.fecha < end).scalar()

        return render_template(
            "detalle_ventas.html",
            ventas=ventas,
            fecha=fecha_obj,
            total_dia=total_dia
        )
    except Exception as e:
        flash(f"❌ Error cargando detalle: {e}", "danger")
        return redirect(url_for("app_rutas.liquidacion"))

# ======================================================
# 📤 DETALLE DE SALIDAS POR DÍA (CORREGIDO)
# ======================================================
@app_rutas.route("/detalle_salida/<fecha>")
@login_required
def detalle_salida(fecha):
    try:
        # Convertir la fecha del formato "YYYY-MM-DD"
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

        # Rango completo del día (00:00:00 → 23:59:59)
        inicio = datetime.combine(fecha_obj, time.min)
        fin = datetime.combine(fecha_obj, time.max)

        # Buscar salidas del día
        salidas = MovimientoCaja.query.filter(
            MovimientoCaja.tipo.in_(["salida", "gasto"]),
            MovimientoCaja.fecha >= inicio,
            MovimientoCaja.fecha <= fin
        ).order_by(MovimientoCaja.fecha.asc()).all()

        # Calcular total del día
        total_salidas = sum(s.monto for s in salidas)

        return render_template(
            "detalle_salida.html",
            salidas=salidas,
            fecha=fecha_obj,
            total_salidas=total_salidas
        )

    except Exception as e:
        flash(f"❌ Error al cargar detalle de salidas: {e}", "danger")
        return redirect(url_for("app_rutas.liquidacion"))

# ======================================================
# 📦 ENTRADA DE INVENTARIO — versión optimizada (rápida + AJAX)
# ======================================================
@app_rutas.route("/entrada_inventario", methods=["GET", "POST"])
@login_required
def entrada_inventario():
    if request.method == "POST":
        try:
            codigo = request.form.get("codigo", "").strip()
            cantidad = int(request.form.get("cantidad", 0))

            # 🧩 Validaciones
            if not codigo:
                flash("⚠️ Debes ingresar un código de producto.", "warning")
                return redirect(url_for("app_rutas.entrada_inventario"))

            producto = Producto.query.filter_by(codigo=codigo).first()
            if not producto:
                flash("❌ No se encontró un producto con ese código.", "danger")
                return redirect(url_for("app_rutas.entrada_inventario"))

            if cantidad <= 0:
                flash("⚠️ La cantidad debe ser mayor a cero.", "warning")
                return redirect(url_for("app_rutas.entrada_inventario"))

            # 📦 Actualizar stock
            producto.unidades_restantes += cantidad
            producto.stock_inicial += cantidad
            valor_total = (producto.valor_unitario or 0) * cantidad

            # 🕒 Registrar historial
            historial = HistorialInventario(
                producto_id=producto.id,
                cantidad=cantidad,
                valor_total=valor_total,
                fecha=hora_actual()
            )
            db.session.add(historial)

            # 🧹 Eliminar registros antiguos (más de 90 días)
            limite = hora_actual() - timedelta(days=90)
            HistorialInventario.query.filter(
                HistorialInventario.fecha < limite
            ).delete()

            db.session.commit()

            # ⚡ Si es una solicitud AJAX, devolver JSON
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "success": True,
                    "producto": producto.nombre,
                    "cantidad": cantidad,
                    "nuevo_stock": producto.unidades_restantes,
                    "valor_total": round(valor_total, 2),
                    "fecha": hora_actual().strftime("%Y-%m-%d %H:%M:%S")
                })

            # ✅ Respuesta normal (modo HTML)
            flash(f"✅ {cantidad} unidades agregadas a {producto.nombre}.", "success")
            return redirect(url_for("app_rutas.entrada_inventario"))

        except Exception as e:
            db.session.rollback()

            # ❌ Error vía AJAX
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": False, "error": str(e)}), 500

            flash(f"❌ Error al registrar entrada: {e}", "danger")
            return redirect(url_for("app_rutas.entrada_inventario"))

    # 📋 Vista GET — mostrar inventario y últimos 90 días
    productos = Producto.query.order_by(Producto.nombre.asc()).all()
    limite = hora_actual() - timedelta(days=90)
    historial = (
        HistorialInventario.query
        .filter(HistorialInventario.fecha >= limite)
        .order_by(HistorialInventario.fecha.desc())
        .all()
    )

    return render_template("entrada_inventario.html", productos=productos, historial=historial)


# ======================================================
# 📊 LIQUIDACIÓN DE PRODUCTOS (Aitana System)
# ======================================================
@app_rutas.route("/liquidacion", methods=["GET", "POST"])
@login_required
def liquidacion():
    hoy = local_date()
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")

    # Última liquidación registrada
    ultima_liq = LiquidacionProducto.query.order_by(LiquidacionProducto.fecha.desc()).first()
    ultima_fecha = ultima_liq.fecha if ultima_liq else None

    # =====================================================
    # 📆 CONSULTA POR RANGO
    # =====================================================
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
        total_ventas = total_entradas = total_salidas = total_caja = 0.0

        fecha_actual = fi

        while fecha_actual <= ff:
            start, end = day_range(fecha_actual)
            inventario_total = calcular_inventario_total()

            # ✔ SI YA EXISTE LIQUIDACIÓN GUARDADA → SE USA
            liq_guardada = LiquidacionProducto.query.filter_by(fecha=fecha_actual).first()

            if liq_guardada:
                resultados.append({
                    "fecha": liq_guardada.fecha,
                    "caja_anterior": liq_guardada.caja_anterior,
                    "ventas_dia": liq_guardada.ventas_dia,
                    "entradas": liq_guardada.entradas,
                    "salidas": liq_guardada.salidas,
                    "caja_dia": liq_guardada.caja_dia,
                    "caja_total": liq_guardada.caja_total,
                    "inventario": liq_guardada.inventario_total,
                })

                total_ventas += liq_guardada.ventas_dia
                total_entradas += liq_guardada.entradas
                total_salidas += liq_guardada.salidas
                total_caja = liq_guardada.caja_dia

                fecha_actual += timedelta(days=1)
                continue

            # ✔ SI NO EXISTE → CALCULAR
            caja_anterior = obtener_caja_anterior(fecha_actual)

            ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))\
                .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

            entradas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
                .filter(MovimientoCaja.tipo == "entrada",
                        MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
                .scalar() or 0.0

            salidas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
                .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]),
                        MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
                .scalar() or 0.0

            caja_dia = caja_anterior + ventas_dia + entradas - salidas

            resultados.append({
                "fecha": fecha_actual,
                "caja_anterior": caja_anterior,
                "ventas_dia": ventas_dia,
                "entradas": entradas,
                "salidas": salidas,
                "caja_dia": caja_dia,
                "caja_total": caja_dia,
                "inventario": inventario_total,
            })

            total_ventas += ventas_dia
            total_entradas += entradas
            total_salidas += salidas
            total_caja = caja_dia

            fecha_actual += timedelta(days=1)

        return render_template(
            "liquidacion.html",
            modo="rango",
            liquidaciones=resultados,
            fecha_inicio=fi,
            fecha_fin=ff,
            ultima_fecha=ultima_fecha,
            total_ventas=total_ventas,
            total_ingresos=total_entradas,
            total_salida=total_salidas,
            caja_final=total_caja,
            total_paquete=inventario_total
        )

    # =====================================================
    # 🟢 GET — LIQUIDACIÓN DEL DÍA (RECALCULADA SIN DUPLICAR)
    # =====================================================
    start, end = day_range(hoy)
    inventario_total = calcular_inventario_total()

    liq = LiquidacionProducto.query.filter_by(fecha=hoy).first()

    # ✔ SI YA EXISTE → ACTUALIZAR SIN DUPLICAR NADA
    if liq:
        ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))\
            .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

        entradas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.tipo == "entrada",
                    MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
            .scalar() or 0.0

        salidas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]),
                    MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
            .scalar() or 0.0

        caja_dia = liq.caja_anterior + ventas_dia + entradas - salidas

        liq.ventas_dia = ventas_dia
        liq.entradas = entradas
        liq.salidas = salidas
        liq.caja_dia = caja_dia
        liq.caja_total = caja_dia
        liq.inventario_total = inventario_total

        db.session.commit()

        resultados = [{
            "fecha": hoy,
            "caja_anterior": liq.caja_anterior,
            "ventas_dia": ventas_dia,
            "entradas": entradas,
            "salidas": salidas,
            "caja_dia": caja_dia,
            "caja_total": caja_dia,
            "inventario": inventario_total,
        }]

    else:
        # ✔ NO EXISTE → CREAR NORMAL
        caja_anterior = obtener_caja_anterior(hoy)

        ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))\
            .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

        entradas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.tipo == "entrada",
                    MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
            .scalar() or 0.0

        salidas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.tipo.in_(["salida", "gasto"]),
                    MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end)\
            .scalar() or 0.0

        caja_dia = caja_anterior + ventas_dia + entradas - salidas

        nueva_liq = LiquidacionProducto(
            fecha=hoy,
            caja_anterior=caja_anterior,
            ventas_dia=ventas_dia,
            entradas=entradas,
            salidas=salidas,
            caja_dia=caja_dia,
            caja_total=caja_dia,
            inventario_total=inventario_total,
        )
        db.session.add(nueva_liq)
        db.session.commit()

        resultados = [{
            "fecha": hoy,
            "caja_anterior": caja_anterior,
            "ventas_dia": ventas_dia,
            "entradas": entradas,
            "salidas": salidas,
            "caja_dia": caja_dia,
            "caja_total": caja_dia,
            "inventario": inventario_total,
        }]

    return render_template(
        "liquidacion.html",
        modo="dia",
        liquidaciones=resultados,
        fecha_inicio=hoy,
        fecha_fin=hoy,
        ultima_fecha=ultima_fecha,
        total_ventas=resultados[0]["ventas_dia"],
        total_ingresos=resultados[0]["entradas"],
        total_salida=resultados[0]["salidas"],
        caja_final=resultados[0]["caja_dia"],
        total_paquete=inventario_total
    )


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
