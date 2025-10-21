# ======================================================
# verificar_horas.py — Comprueba fechas/hora reales 🇨🇱
# ======================================================

from app import app, db
from modelos import Venta, MovimientoCaja, HistorialInventario
from tiempo import to_hora_chile

print("===============================================")
print("     🕒 VERIFICACIÓN DE HORAS REALES EN BD")
print("===============================================")

with app.app_context():
    print("\n📦 Últimas 5 Ventas registradas:")
    ventas = Venta.query.order_by(Venta.fecha.desc()).limit(5).all()
    if not ventas:
        print("  ⚠️ No hay ventas registradas.")
    else:
        for v in ventas:
            print(f"  ID {v.id} | {v.producto.nombre} | Fecha: {v.fecha} → {to_hora_chile(v.fecha)}")

    print("\n💰 Últimos 5 Movimientos de Caja:")
    movs = MovimientoCaja.query.order_by(MovimientoCaja.fecha.desc()).limit(5).all()
    if not movs:
        print("  ⚠️ No hay movimientos registrados.")
    else:
        for m in movs:
            print(f"  ID {m.id} | {m.tipo} | Monto: {m.monto} | Fecha: {m.fecha} → {to_hora_chile(m.fecha)}")

    print("\n📊 Últimos 5 Registros del Historial de Inventario:")
    hist = HistorialInventario.query.order_by(HistorialInventario.fecha.desc()).limit(5).all()
    if not hist:
        print("  ⚠️ No hay registros en el historial de inventario.")
    else:
        for h in hist:
            print(f"  ID {h.id} | {h.producto.nombre} | Cant: {h.cantidad} | Fecha: {h.fecha} → {to_hora_chile(h.fecha)}")

print("===============================================")
print("  ✅ Verificación completada correctamente.")
print("===============================================")
