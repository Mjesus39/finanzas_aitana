# app.py - Versión con productos y rutas de caja directas
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
# Configuración de la base de datos
# ---------------------------
DB_DEFAULT = "postgresql+psycopg2://almacen_aitana_332s_user:UH0aEwkoIZXef7j6k3aL8YC8wTHQGWYU@dpg-d38vaabuibrs73a4mmh0-a.oregon-postgres.render.com/almacen_aitana_332s"
DATABASE_URL = os.getenv("DATABASE_URL", DB_DEFAULT)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------------------
# Inicialización de extensiones
# ---------------------------
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ---------------------------
# Usuarios válidos
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
    stock_inicial = db.Column(db.Integer, default=0)  # 👈 aquí
    unidades_restantes = db.Column(db.Integer, default=0)
    valor_unitario = db.Column(db.Float, nullable=False)
    interes = db.Column(db.Float, default=0)
    fecha = db.Column(db.Date, default=date.today)

class MovimientoCaja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # entrada, salida, gasto
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

from datetime import date
from sqlalchemy import desc

def crear_liquidacion():
    # Calcula valores actuales de caja e inventario
    entrada_total = sum(m.monto for m in MovimientoCaja.query.filter_by(tipo='entrada').all())
    salida_total = sum(m.monto for m in MovimientoCaja.query.filter_by(tipo='salida').all())
    caja_actual = entrada_total - salida_total
    inventario_valor = calcular_valor_inventario()  # tu función actual para calcular inventario

    # Verifica si ya existe liquidación del día
    hoy = date.today()
    liquidacion = Liquidacion.query.filter_by(fecha=hoy).first()
    if not liquidacion:
        liquidacion = Liquidacion(
            fecha=hoy,
            entrada=entrada_total,
            salida=salida_total,
            caja=caja_actual,
            inventario_valor=inventario_valor
        )
        db.session.add(liquidacion)
        db.session.commit()

        # Mantener solo las últimas 10 liquidaciones
        todas = Liquidacion.query.order_by(desc(Liquidacion.fecha)).all()
        if len(todas) > 10:
            for liq in todas[10:]:
                db.session.delete(liq)
            db.session.commit()

def obtener_resumen_total():
    # Movimientos manuales
    total_entradas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto),0))\
        .filter(MovimientoCaja.tipo=='entrada').scalar() or 0
    total_salidas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto),0))\
        .filter(MovimientoCaja.tipo=='salida').scalar() or 0
    total_gastos = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto),0))\
        .filter(MovimientoCaja.tipo=='gasto').scalar() or 0

    # Ventas (todas las liquidaciones)
    total_ventas = db.session.query(func.coalesce(func.sum(Liquidacion.entrada),0)).scalar() or 0

    # Caja total = ventas + entradas - salidas - gastos
    caja_total = total_ventas + total_entradas - (total_salidas + total_gastos)
    
    # Inventario
    inventario_total = float(db.session.query(
        func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario * (1 + Producto.interes/100)),0)
    ).scalar() or 0)

    return {"caja_total": caja_total, "inventario_total": inventario_total}

class Liquidacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, unique=True, nullable=False)
    entrada = db.Column(db.Float, default=0.0)
    salida = db.Column(db.Float, default=0.0)
    caja = db.Column(db.Float, default=0.0)
    inventario_valor = db.Column(db.Float, default=0.0)

    @property
    def total(self):
        """Calcula el total automáticamente al acceder."""
        return (self.entrada or 0) - (self.salida or 0) + (self.caja or 0) + (self.inventario_valor or 0)

# Función auxiliar para dar estilo a las filas según stock
def estado_class(producto):
    if producto.stock_inicial == 0:
        return "table-danger"   # rojo = sin stock
    elif producto.stock_inicial < 5:
        return "table-warning"  # amarillo = poco stock
    return ""                   # sin clase extra

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

def crear_liquidacion_para_fecha(fecha):
    liq = Liquidacion.query.filter_by(fecha=fecha).first()
    if not liq:
        inventario_valor = float(db.session.query(
            func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario), 0)
        ).scalar() or 0.0)
        liq = Liquidacion(fecha=fecha, caja=0.0, inventario_valor=inventario_valor)
        db.session.add(liq)
        db.session.commit()
    return liq

def actualizar_liquidacion_por_movimiento(fecha: date):
    fecha = fecha if isinstance(fecha, date) else fecha.date()
    liq = Liquidacion.query.filter_by(fecha=fecha).first() or crear_liquidacion_para_fecha(fecha)
    start, end = day_range(fecha)

    entradas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "entrada")\
        .scalar() or 0.0
    salidas = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "salida")\
        .scalar() or 0.0
    gastos = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
        .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end, MovimientoCaja.tipo == "gasto")\
        .scalar() or 0.0

    caja = entradas - (salidas + gastos)
    inventario_valor = float(db.session.query(
        func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario), 0)
    ).scalar() or 0.0)

    liq.caja = caja
    liq.inventario_valor = inventario_valor
    db.session.commit()
    return liq

# ---------------------------
# RUTAS AUTH
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
# RUTAS PRINCIPALES
# ---------------------------
@app.route("/")
@login_required
def index():
    productos = Producto.query.all()

    liq_hoy = Liquidacion.query.filter_by(fecha=date.today()).first()

    ultimas_liqs = (
        Liquidacion.query.order_by(Liquidacion.fecha.desc())
        .limit(10)
        .all()
    )

    total_inventario = sum(
        (p.stock_inicial or 0) * (
            p.valor_unitario + (p.valor_unitario * (p.interes or 0) / 100)
        )
        for p in productos
    )

    # 👉 CALCULO DEL TOTAL VENDIDO
    total_vendido = 0
    for p in productos:
        vendidas = (p.stock_inicial or 0) - (p.unidades_restantes or 0)
        valor_vendido = vendidas * (p.valor_unitario or 0) * (1 + (p.interes or 0)/100)
        total_vendido += valor_vendido

    return render_template(
        "index.html",
        productos=productos,
        hoy=date.today(),
        liq_hoy=liq_hoy,
        ultimas_liqs=ultimas_liqs,
        total_inventario=total_inventario,
        total_vendido=total_vendido,   # 👈 ahora lo pasamos
        estado_class=estado_class
    )

@app.route("/detalle_caja/<fecha>")
@login_required
def detalle_caja(fecha):
    from datetime import datetime, date
    
    if fecha == "total":
        # Mostrar resumen por día
        liquidaciones = Liquidacion.query.order_by(Liquidacion.fecha.desc()).all()
        resumen_diario = []
        for liq in liquidaciones:
            resumen_diario.append({
                "fecha": liq.fecha,
                "caja": liq.caja,
                "inventario": liq.inventario_valor
            })
        return render_template("detalle_caja_total.html", resumen_diario=resumen_diario)

    else:
        # Mostrar detalle de productos de un día específico
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
        productos = Producto.query.all()
        detalle = []
        total_vendido = 0

        for p in productos:
            vendidas = (p.stock_inicial or 0) - (p.unidades_restantes or 0)
            if vendidas > 0:
                valor_vendido = vendidas * p.valor_unitario * (1 + (p.interes or 0)/100)
                detalle.append({
                    "producto": p.nombre,
                    "vendidas": vendidas,
                    "valor": valor_vendido
                })
                total_vendido += valor_vendido

        # Actualizamos la liquidación de la caja con el total vendido del día
        liq = Liquidacion.query.filter_by(fecha=fecha_dt).first()
        if liq:
            liq.caja = total_vendido
            db.session.commit()

        return render_template(
            "detalle_caja.html",
            fecha=fecha_dt,
            detalle=detalle,
            total_vendido=total_vendido
        )

@app.route("/detalle_caja_total")
@login_required
def detalle_caja_total():
    # Traer todas las liquidaciones
    liquidaciones = Liquidacion.query.order_by(Liquidacion.fecha.asc()).all()
    
    # Actualizar caja de cada liquidación según ventas actuales
    productos = Producto.query.all()
    for liq in liquidaciones:
        total_vendido = 0
        for p in productos:
            vendidas = (p.stock_inicial or 0) - (p.unidades_restantes or 0)
            if vendidas > 0:
                total_vendido += vendidas * p.valor_unitario * (1 + (p.interes or 0)/100)
        liq.caja = total_vendido

    # Calcular totales acumulados
    total_caja = sum(liq.caja or 0 for liq in liquidaciones)
    total_inventario = sum(liq.inventario_valor or 0 for liq in liquidaciones)

    return render_template(
        "detalle_caja_total.html",
        liquidaciones=liquidaciones,
        total_caja=total_caja,
        total_inventario=total_inventario
    )

@app.route("/dashboard")
@login_required
def dashboard():
    total_productos = Producto.query.count()
    inventario_total = float(db.session.query(
        func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario), 0)
    ).scalar() or 0.0)
    return render_template("dashboard.html", total_productos=total_productos, inventario_total=inventario_total)

@app.route("/liquidacion")
@login_required
def liquidacion():
    hoy = date.today()
    productos = Producto.query.all()

    # -------------------
    # Liquidación de hoy
    # -------------------
    liq_hoy = Liquidacion.query.filter_by(fecha=hoy).first()
    total_vendido_hoy = 0
    for p in productos:
        vendidas = (p.stock_inicial or 0) - (p.unidades_restantes or 0)
        if vendidas > 0:
            total_vendido_hoy += vendidas * p.valor_unitario * (1 + (p.interes or 0)/100)

    if liq_hoy:
        liq_hoy.entrada = total_vendido_hoy      # Guardamos el total vendido
        liq_hoy.caja = total_vendido_hoy         # Lo mismo para mostrar en la tabla
        liq_hoy.inventario_valor = float(db.session.query(
            func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario * (1 + Producto.interes/100)),0)
        ).scalar() or 0.0)
    else:
        liq_hoy = Liquidacion(
            fecha=hoy,
            entrada=total_vendido_hoy,
            salida=0,
            caja=total_vendido_hoy,  # Guardamos directamente aquí
            inventario_valor=float(db.session.query(
                func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario * (1 + Producto.interes/100)),0)
            ).scalar() or 0.0)
        )
        db.session.add(liq_hoy)
    db.session.commit()

    # -------------------
    # Últimas 10 liquidaciones con valores correctos
    # -------------------
    ultimas = Liquidacion.query.order_by(Liquidacion.fecha.desc()).limit(10).all()
    # No recalculamos dinámicamente; usamos lo que ya está guardado
    # liq.caja ya tiene el total vendido del día

    # -------------------
    # Resumen total (caja + inventario)
    # -------------------
    resumen = obtener_resumen_total()
    total_caja = resumen["caja_total"]
    total_inventario = resumen["inventario_total"]

    return render_template(
        "liquidacion.html",
        liquidaciones=ultimas,
        hoy=hoy,
        liq_hoy=liq_hoy,
        total_vendido=total_vendido_hoy,
        total_caja=total_caja,
        total_inventario=total_inventario
    )

@app.route("/vender/<int:producto_id>", methods=["POST"])
@login_required
def vender(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    try:
        cantidad = int(request.form.get("cantidad", 0))
    except ValueError:
        flash("Cantidad inválida", "danger")
        return redirect(url_for("index"))

    if cantidad <= 0:
        flash("La cantidad debe ser mayor que cero", "danger")
        return redirect(url_for("index"))

    if cantidad > producto.unidades_restantes:
        flash("No hay suficientes unidades disponibles", "danger")
        return redirect(url_for("index"))

    # Restar unidades
    producto.unidades_restantes -= cantidad

    # Calcular ingreso con ganancia
    ingreso = cantidad * producto.valor_unitario * (1 + (producto.interes or 0)/100)

    # Actualizar liquidación de hoy
    liq = Liquidacion.query.filter_by(fecha=date.today()).first()
    if not liq:
        liq = Liquidacion(fecha=date.today(), entrada=0, salida=0, caja=0, inventario_valor=0)
        db.session.add(liq)

    liq.entrada += ingreso

    # Actualizar valor de inventario con ganancia
    liq.inventario_valor = float(db.session.query(
        func.coalesce(func.sum(Producto.unidades_restantes * Producto.valor_unitario * (1 + Producto.interes/100)), 0)
    ).scalar() or 0.0)

    db.session.commit()
    flash(f"Se registró la venta de {cantidad} unidad(es) de {producto.nombre}", "success")
    return redirect(url_for("index"))

@app.route("/ingresar_inventario_por_codigo", methods=["POST"])
@login_required
def ingresar_inventario_por_codigo():
    codigo = request.form.get("codigo").strip()
    cantidad = float(request.form.get("cantidad") or 0)

    if cantidad <= 0:
        flash("Cantidad inválida", "danger")
        return redirect(url_for("liquidacion"))

    producto = Producto.query.filter_by(codigo=codigo).first()
    if not producto:
        flash("Código no encontrado", "danger")
        return redirect(url_for("liquidacion"))

    # ✅ Sumar al inventario actual, no al stock inicial
    producto.unidades_restantes += cantidad
    db.session.commit()

    flash(f"Se ingresaron {cantidad} unidades a {producto.nombre}", "success")
    return redirect(url_for("liquidacion"))

@app.route("/actualizar_orden_producto/<int:producto_id>", methods=["POST"])
@login_required
def actualizar_orden_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    try:
        nuevo_orden = int(request.form.get("orden", producto.orden))
    except ValueError:
        flash("Orden inválida", "danger")
        return redirect(url_for("index"))

    producto.orden = nuevo_orden
    db.session.commit()
    flash(f"Orden de {producto.nombre} actualizada a {nuevo_orden}", "success")
    return redirect(url_for("index"))

@app.route("/eliminar_producto/<int:producto_id>", methods=["POST"])
@login_required
def eliminar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    db.session.delete(producto)
    db.session.commit()
    flash(f"Producto {producto.nombre} eliminado", "success")
    return redirect(url_for("index"))

@app.route("/detalle_caja_acumulada")
@login_required
def detalle_caja_acumulada():
    liquidaciones = Liquidacion.query.order_by(Liquidacion.fecha.asc()).all()
    total_caja = 0
    detalle = []

    for liq in liquidaciones:
        total_caja += liq.caja or 0
        detalle.append({
            "fecha": liq.fecha,
            "caja": liq.caja
        })

    return render_template("detalle_caja_acumulada.html", detalle=detalle, total_caja=total_caja)

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

    # ✅ No llamamos a actualizar_liquidacion_por_movimiento aquí
    # La caja histórica queda intacta; solo se modifica la caja resumen total al calcularla

    flash(f"{tipo.capitalize()} registrada en caja", "success")
    return redirect(url_for("liquidacion"))

# ---------------------------
# RUTAS DIRECTAS PARA CAJA
# ---------------------------
@app.route("/caja_entrada", methods=["POST"])
@login_required
def caja_entrada():
    return caja_movimiento("entrada")

@app.route("/caja_salida", methods=["POST"])
@login_required
def caja_salida():
    return caja_movimiento("salida")

# ---------------------------
# PRODUCTOS CRUD
# ---------------------------
def generar_codigo_producto():
    code = ''.join(random.choices("0123456789", k=6))
    while Producto.query.filter_by(codigo=code).first():
        code = ''.join(random.choices("0123456789", k=6))
    return code

@app.route("/nuevo_producto", methods=["GET","POST"])
@login_required
def nuevo_producto():
    if request.method == "POST":
        codigo = request.form.get("codigo", generar_codigo_producto()).strip()
        nombre = request.form.get("nombre", "").strip()
        try:
            orden = int(request.form.get("orden", 0))
            stock_inicial = int(request.form.get("stock_inicial", 0))  # 👈 cantidad inicial
            valor_unitario = float(request.form.get("valor_unitario", 0))
            interes = float(request.form.get("interes", 0))  # 👈 porcentaje de ganancia
        except ValueError:
            flash("Valores inválidos", "warning")
            return redirect(url_for("nuevo_producto"))

        # Si no se definió orden, tomar el siguiente disponible
        if orden <= 0:
            last = Producto.query.order_by(Producto.orden.desc()).first()
            orden = (last.orden + 1) if last else 1

        producto = Producto(
            codigo=codigo,
            nombre=nombre,
            orden=orden,
            stock_inicial=stock_inicial,       # 👈 guardar cantidad inicial
            unidades_restantes=stock_inicial,  # 👈 inicializar unidades restantes
            valor_unitario=valor_unitario,
            interes=interes,                   # 👈 guardar ganancia
            fecha=date.today()
        )
        db.session.add(producto)
        db.session.commit()
        flash("Producto agregado correctamente", "success")
        return redirect(url_for("index"))

    return render_template("nuevo_producto.html")

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
