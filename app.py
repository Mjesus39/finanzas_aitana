# app.py - versión estable con caja funcional por día
import os, random
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timedelta, time
from sqlalchemy import func

# ---------------------------
# Configuración de la app
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "clave_secreta_local_cámbiala")

# ---------------------------
# Base de datos
# ---------------------------
DB_DEFAULT = "postgresql+psycopg2://almacen_aitana_332s_user:UH0aEwkoIZXef7j6k3aL8YC8wTHQGWYU@dpg-d38vaabuibrs73a4mmh0-a.oregon-postgres.render.com/almacen_aitana_332s"
DATABASE_URL = os.getenv("DATABASE_URL", DB_DEFAULT)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------------------------
# Usuario
# ---------------------------
VALID_USER = "mjesus40"
VALID_PASS = "198409"

# ---------------------------
# MODELOS
# ---------------------------
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

    # 🟢 Campos nuevos para registrar ventas diarias
    vendidas_dia = db.Column(db.Integer, default=0)
    valor_vendido_dia = db.Column(db.Float, default=0.0)

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    ingreso = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    producto = db.relationship("Producto", backref="ventas")

class MovimientoCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # entrada, salida, gasto
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Liquidacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, unique=True, nullable=False)
    entrada = db.Column(db.Float, default=0.0)
    salida = db.Column(db.Float, default=0.0)
    caja = db.Column(db.Float, default=0.0)
    inventario_valor = db.Column(db.Float, default=0.0)

# ---------------------------
# FUNCIONES AUXILIARES
# ---------------------------
def reiniciar_ventas_diarias():
    hoy = date.today()
    productos = Producto.query.all()
    for p in productos:
        if p.fecha != hoy:
            p.vendidas_dia = 0
            p.valor_vendido_dia = 0.0
            p.fecha = hoy
    db.session.commit()

# ---------------------------
# HELPERS
# ---------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def day_range(fecha: date):
    start = datetime.combine(fecha, time.min)
    end = start + timedelta(days=1)
    return start, end

def estado_class(producto):
    if producto.unidades_restantes <= 5:
        return "table-danger"
    return ""

# ---------------------------
# LOGIN
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "").strip()
        if usuario == VALID_USER and clave == VALID_PASS:
            session["usuario"] = usuario
            flash("Inicio de sesión correcto", "success")
            return redirect(url_for("index"))
        flash("Usuario o clave incorrectos", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    flash("Sesión cerrada", "info")
    return redirect(url_for("login"))

# ---------------------------
# PRINCIPAL (versión sincronizada con ventas diarias)
# ---------------------------
@app.route("/")
@login_required
def index():
    hoy = date.today()
    start = datetime.combine(hoy, time.min)
    end = datetime.combine(hoy + timedelta(days=1), time.min)

    # Traer productos ordenados
    productos = Producto.query.order_by(Producto.orden.asc(), Producto.id.asc()).all()

    # Recalcular ventas del día directamente desde la tabla Venta
    for p in productos:
        total_vendido = db.session.query(func.coalesce(func.sum(Venta.cantidad), 0)).filter(
            Venta.producto_id == p.id,
            Venta.fecha >= start,
            Venta.fecha < end
        ).scalar() or 0

        ingreso_vendido = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0)).filter(
            Venta.producto_id == p.id,
            Venta.fecha >= start,
            Venta.fecha < end
        ).scalar() or 0.0

        p.vendidas_dia = total_vendido
        p.valor_vendido_dia = ingreso_vendido
        p.fecha = hoy

    db.session.commit()

    # Calcular el precio con ganancia
    for p in productos:
        p.precio_ganancia = (p.valor_unitario or 0) * (1 + (p.interes or 0) / 100)

    total_vendido = sum(p.valor_vendido_dia or 0 for p in productos)
    ultimo_vendido = session.pop("resaltado", None)

    return render_template(
        "index.html",
        productos=productos,
        estado_class=estado_class,
        total_vendido=total_vendido,
        ultimo_vendido=ultimo_vendido
    )

# ---------------------------
# INGRESAR INVENTARIO POR CÓDIGO
# ---------------------------
@app.route("/ingresar_inventario_por_codigo", methods=["POST"])
@login_required
def ingresar_inventario_por_codigo():
    codigo = request.form.get("codigo", "").strip()
    try:
        cantidad = float(request.form.get("cantidad") or 0)
    except ValueError:
        flash("Cantidad inválida", "danger")
        return redirect(url_for("liquidacion"))

    if cantidad <= 0:
        flash("Cantidad inválida", "danger")
        return redirect(url_for("liquidacion"))

    producto = Producto.query.filter_by(codigo=codigo).first()
    if not producto:
        flash("Código no encontrado", "danger")
        return redirect(url_for("liquidacion"))

    # Sumar al inventario actual y al stock inicial
    producto.unidades_restantes += cantidad
    producto.stock_inicial += cantidad

    db.session.commit()
    flash(f"Se ingresaron {cantidad} unidades a {producto.nombre}", "success")
    return redirect(url_for("liquidacion"))

# ---------------------------
# ACTUALIZAR ORDEN DE PRODUCTO
# ---------------------------
@app.route("/actualizar_orden_producto/<int:producto_id>", methods=["POST"])
@login_required
def actualizar_orden_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)

    try:
        nuevo_orden = int(request.form.get("orden", producto.orden))
        if nuevo_orden < 1:
            raise ValueError("El orden debe ser mayor a 0.")
    except ValueError:
        flash("Orden inválida. Debe ser un número entero positivo.", "danger")
        return redirect(url_for("index"))

    # Traemos todos los productos ordenados
    productos = Producto.query.order_by(Producto.orden.asc(), Producto.id.asc()).all()

    # Quitamos el producto actual de la lista
    productos.remove(producto)

    # Aseguramos que no se exceda el total
    if nuevo_orden > len(productos) + 1:
        nuevo_orden = len(productos) + 1

    # Insertamos el producto en la nueva posición
    productos.insert(nuevo_orden - 1, producto)

    # Reasignamos los órdenes correctamente
    for idx, p in enumerate(productos, start=1):
        p.orden = idx

    db.session.commit()
    flash(f"Orden de '{producto.nombre}' actualizada a posición {nuevo_orden}.", "success")
    return redirect(url_for("index"))

# ---------------------------
# REGISTRAR VENTA (versión corregida)
# ---------------------------
@app.route("/vender/<int:producto_id>", methods=["POST"])
@login_required
def vender(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    try:
        cantidad = int(request.form.get("cantidad", 0))
    except ValueError:
        flash("Cantidad inválida", "warning")
        return redirect(url_for("index"))

    if cantidad <= 0:
        flash("Cantidad inválida", "warning")
        return redirect(url_for("index"))

    if producto.unidades_restantes < cantidad:
        flash("No hay suficientes unidades disponibles.", "danger")
        return redirect(url_for("index"))

    # 🧮 Calcular ingreso con ganancia
    precio_con_ganancia = producto.valor_unitario * (1 + producto.interes / 100)
    ingreso = cantidad * precio_con_ganancia

    # 🔄 Actualizar stock y ventas del día
    producto.unidades_restantes -= cantidad
    producto.vendidas_dia = (producto.vendidas_dia or 0) + cantidad
    producto.valor_vendido_dia = (producto.valor_vendido_dia or 0) + ingreso

    # 💾 Asegurar que el producto quede marcado para actualizar
    db.session.add(producto)

    # 💾 Registrar la venta
    venta = Venta(
        producto_id=producto.id,
        cantidad=cantidad,
        ingreso=ingreso,
        fecha=datetime.utcnow()
    )
    db.session.add(venta)

    # 💰 Registrar movimiento en caja
    mov = MovimientoCaja(
        tipo="entrada",
        monto=ingreso,
        descripcion=f"Venta de {producto.nombre}",
        fecha=datetime.utcnow()
    )
    db.session.add(mov)

    # ✅ Guardar cambios
    db.session.commit()

    # 🌟 Resaltar producto vendido
    session["resaltado"] = producto.id
    flash(f"Venta registrada: {producto.nombre} ({cantidad} unidades, ${ingreso:,.2f}).", "success")

    return redirect(url_for("index"))


# ---------------------------
# CAJA
# ---------------------------
@app.route("/caja/<tipo>", methods=["POST"])
@login_required
def caja_movimiento(tipo):
    if tipo not in ["entrada", "salida", "gasto"]:
        flash("Tipo de movimiento inválido", "danger")
        return redirect(url_for("liquidacion"))

    try:
        monto = float(request.form.get("monto", 0))
    except ValueError:
        flash("Monto inválido", "warning")
        return redirect(url_for("liquidacion"))

    if monto <= 0:
        flash("Monto debe ser mayor a 0", "warning")
        return redirect(url_for("liquidacion"))

    descripcion = request.form.get("descripcion", f"{tipo.capitalize()} manual")
    mov = MovimientoCaja(tipo=tipo, monto=monto, descripcion=descripcion, fecha=datetime.utcnow())
    db.session.add(mov)
    db.session.commit()

    flash(f"{tipo.capitalize()} registrada en caja", "success")
    return redirect(url_for("liquidacion"))

@app.route("/caja_entrada", methods=["POST"])
@login_required
def caja_entrada():
    return caja_movimiento("entrada")

@app.route("/caja_salida", methods=["POST"])
@login_required
def caja_salida():
    return caja_movimiento("salida")

# ---------------------------
# LIQUIDACIÓN (por día)
# ---------------------------
@app.route("/liquidacion", methods=["GET", "POST"])
@login_required
def liquidacion():
    if request.method == "POST":
        fecha_str = request.form.get("fecha")
        try:
            fecha_consulta = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
        except Exception:
            fecha_consulta = date.today()
    else:
        fecha_consulta = date.today()

    start, end = day_range(fecha_consulta)

    ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))\
        .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

    entradas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "entrada").scalar() or 0.0

    salidas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "salida").scalar() or 0.0

    gastos_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "gasto").scalar() or 0.0

    caja_dia = float(ventas_dia) + float(entradas_dia) - float(salidas_dia) - float(gastos_dia)

    inventario_valor = float(db.session.query(
        func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario * (1 + Producto.interes / 100)), 0)
    ).scalar() or 0.0)

    liq = Liquidacion.query.filter_by(fecha=fecha_consulta).first()
    if not liq:
        liq = Liquidacion(
            fecha=fecha_consulta,
            entrada=float(ventas_dia) + float(entradas_dia),
            salida=float(salidas_dia) + float(gastos_dia),
            caja=caja_dia,
            inventario_valor=inventario_valor
        )
        db.session.add(liq)
    else:
        liq.entrada = float(ventas_dia) + float(entradas_dia)
        liq.salida = float(salidas_dia) + float(gastos_dia)
        liq.caja = caja_dia
        liq.inventario_valor = inventario_valor
    db.session.commit()

    ventas_detalle = Venta.query.filter(Venta.fecha >= start, Venta.fecha < end).order_by(Venta.fecha).all()
    return render_template(
    "liquidacion.html",
    hoy=date.today(),
    fecha_consulta=fecha_consulta,
    liq=liq,
    ventas_dia=ventas_detalle,
    inventario_valor=inventario_valor,
    total_inventario=inventario_valor,
    total_caja=liq.caja  # 👈 agregado
)

# ---------------------------
# PRODUCTOS
# ---------------------------
@app.route("/nuevo_producto", methods=["GET","POST"])
@login_required
def nuevo_producto():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip() or ''.join(random.choices("0123456789", k=6))
        nombre = request.form.get("nombre", "").strip()
        stock_inicial = int(request.form.get("stock_inicial", 0))
        valor_unitario = float(request.form.get("valor_unitario", 0))
        interes = float(request.form.get("interes", 0))
        orden = Producto.query.count() + 1

        producto = Producto(codigo=codigo, nombre=nombre, orden=orden,
                            stock_inicial=stock_inicial, unidades_restantes=stock_inicial,
                            valor_unitario=valor_unitario, interes=interes, fecha=date.today())
        db.session.add(producto)
        db.session.commit()
        flash("Producto agregado correctamente", "success")
        return redirect(url_for("index"))
    return render_template("nuevo_producto.html")

@app.route("/eliminar_producto/<int:producto_id>", methods=["POST"])
@login_required
def eliminar_producto(producto_id):
    flash("Eliminar producto está deshabilitado.", "warning")
    return redirect(url_for("index"))

# ---------------------------
# ERRORES
# ---------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
