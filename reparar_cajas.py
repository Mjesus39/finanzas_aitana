from app import app, db, Liquidacion, Venta, MovimientoCaja
from sqlalchemy import func
from datetime import datetime, timedelta, time

def day_range(fecha):
    start = datetime.combine(fecha, time.min)
    end = start + timedelta(days=1)
    return start, end

print("🔧 Recalculando cajas día por día...\n")

# 🟢 Usa el contexto de la app
with app.app_context():
    registros = Liquidacion.query.order_by(Liquidacion.fecha.asc()).all()
    for liq in registros:
        start, end = day_range(liq.fecha)

        ventas_dia = db.session.query(func.coalesce(func.sum(Venta.ingreso), 0))\
            .filter(Venta.fecha >= start, Venta.fecha < end).scalar() or 0.0

        entradas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                    MovimientoCaja.tipo == "entrada").scalar() or 0.0

        salidas_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                    MovimientoCaja.tipo == "salida").scalar() or 0.0

        gastos_dia = db.session.query(func.coalesce(func.sum(MovimientoCaja.monto), 0))\
            .filter(MovimientoCaja.fecha >= start, MovimientoCaja.fecha < end,
                    MovimientoCaja.tipo == "gasto").scalar() or 0.0

        caja_dia = ventas_dia + entradas_dia - salidas_dia - gastos_dia
        liq.caja = caja_dia

        print(f"📅 {liq.fecha}: Ventas={ventas_dia:.2f}, Entradas={entradas_dia:.2f}, "
              f"Salidas={salidas_dia:.2f}, Gastos={gastos_dia:.2f} → Caja={caja_dia:.2f}")

    db.session.commit()
    print("\n✅ Cajas recalculadas correctamente día por día.")

