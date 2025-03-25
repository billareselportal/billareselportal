import sqlite3

def verificar_totales_facturas():
    db_path = r"D:\proyectos terminados\SISTEMA PORTAL - copia\portal.db"
    print(f"🟡 Conectando a la base de datos: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("✅ Conexión exitosa.")

        cursor.execute("SELECT factura_no, total FROM ventas WHERE factura_no IS NOT NULL")
        facturas = cursor.fetchall()
        print(f"📦 Se encontraron {len(facturas)} facturas para verificar.\n")

        facturas_con_error = []

        for factura_no, total_venta in facturas:
            cursor.execute("""
                SELECT SUM(costo) 
                FROM eventos_inventario 
                WHERE factura_no = ?
            """, (factura_no,))
            resultado = cursor.fetchone()
            total_eventos = resultado[0] if resultado[0] is not None else 0

            diferencia = round(total_venta - total_eventos, 2)

            if round(diferencia, 2) != 0:
                facturas_con_error.append((factura_no, total_venta, total_eventos, diferencia))

        if not facturas_con_error:
            print("✅ Todas las facturas coinciden correctamente.")
        else:
            print(f"⚠️ Se encontraron {len(facturas_con_error)} facturas con diferencias:\n")
            for factura_no, total_venta, total_eventos, diferencia in facturas_con_error:
                print(f"   - Factura: {factura_no}")
                print(f"     Total en ventas:           {total_venta}")
                print(f"     Total en eventos_inventario: {total_eventos}")
                print(f"     Diferencia:                {diferencia}\n")

        conn.close()

    except Exception as e:
        print(f"❗ Error al conectar o procesar la base de datos: {e}")

# Ejecutar
verificar_totales_facturas()
