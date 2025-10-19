
from app import app, db, Venta, Liquidacion
from datetime import datetime, date, timedelta, time
from sqlalchemy import func

print("🔧 Corrigiendo ventas del 19/10 → 18/10 ...")

with app.app_context():  # 🟢 Esto activa el contexto de Flask
    fecha_mal = date(2025, 10, 19)
    fecha_correcta = date(2025, 10, 18)

    start = datetime.combine(fecha_mal, time.min)
    end = datetime.combine(fecha_mal + timedelta(days=1), time.min)

    ventas_erradas = Venta.query.filter(Venta.fecha >= start, Venta.fecha < end).all()

    if not ventas_erradas:
        print("✅ No hay ventas del 19/10 para corregir.")
    else:
        print(f"📦 Se encontraron {len(ventas_erradas)} ventas para corregir:")
        total_corregido = 0

        for v in ventas_erradas:
            print(f" - Venta {v.id}: ${v.ingreso:,.2f}")
            total_corregido += v.ingreso
            v.fecha = v.fecha - timedelta(days=1)
            db.session.add(v)

        db.session.commit()
        print(f"✅ {len(ventas_erradas)} ventas actualizadas. Total movido: ${total_corregido:,.2f}")

        liq = Liquidacion.query.filter_by(fecha=fecha_correcta).first()
        if not liq:
            liq = Liquidacion(fecha=fecha_correcta, entrada=0.0, salida=0.0, caja=0.0)
            db.session.add(liq)

        liq.entrada = (liq.entrada or 0.0) + total_corregido
        liq.caja = (liq.caja or 0.0) + total_corregido
        db.session.commit()

        print(f"💰 Caja del {fecha_correcta} actualizada correctamente. Nuevo valor: ${liq.caja:,.2f}")

print("✅ Proceso finalizado.")
