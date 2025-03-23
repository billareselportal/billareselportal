from datetime import datetime, timedelta
import psycopg2
from flask import Flask, request, jsonify, render_template, send_file
from funciones import buscar_por_codigo
from funciones import obtener_lista_precios
import pytz
import pandas as pd

app = Flask(__name__, template_folder='templates')  # Asegurar que use la carpeta de plantillas

# ✅ URL de conexión a PostgreSQL en Render
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

def connect_db():
    """Establece la conexión con la base de datos PostgreSQL en Render."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/inventario')
def inventario():
    return render_template('inventario.html')

@app.route('/consulta', methods=['GET'])
def consulta():
    codigo = request.args.get('codigo')
    if not codigo:
        return jsonify({'success': False, 'message': 'Código no proporcionado'})

    resultado = buscar_por_codigo(codigo)

    if resultado:
        return jsonify({'success': True, 'factura': resultado['factura'], 'cliente': resultado['cliente']})
    else:
        return jsonify({'success': False, 'message': f'No se encontró una factura para el código {codigo}.'})

@app.route('/resultado', methods=['POST'])
def resultado():
    codigo = request.form.get('codigo')  # Código ingresado en el formulario
    if not codigo:
        return render_template('resultado.html', mensaje="Debe ingresar un código.")

    conn = connect_db()  # Asegurar que se llama correctamente la función
    if not conn:
        return render_template('resultado.html', mensaje="Error de conexión a la base de datos.")

    cursor = conn.cursor()

    # 🔎 Buscar el `factura_no` en la tabla `mesas`
    print(f"🟡 Buscando factura asociada al código {codigo}...")
    cursor.execute("SELECT factura_no FROM mesas WHERE codigo = %s;", (codigo,))
    factura_result = cursor.fetchone()

    if not factura_result:
        print(f"❌ No se encontró la factura para el código {codigo}")
        conn.close()
        return render_template('resultado.html', mensaje=f"No se encontró la factura para el código {codigo}.")

    factura_no = factura_result[0]
    print(f"✅ Factura encontrada para código {codigo}: {factura_no}")

    try:
        # 🔎 Buscar en `ventas` usando `factura_no`
        cursor.execute("""
            SELECT factura_no, nombre, estado, 
                   CAST(total AS FLOAT), CAST(saldo AS FLOAT), 
                   CAST(caja AS FLOAT), CAST(nequi AS FLOAT), CAST(bancolombia AS FLOAT), 
                   CAST(datafono AS FLOAT), CAST(julian AS FLOAT), CAST(fiado AS FLOAT), 
                   fecha, concepto
            FROM ventas
            WHERE factura_no = %s""", (factura_no,))
        venta_result = cursor.fetchone()

        # ✅ Imprimir los valores obtenidos
        print(f"✅ Datos de ventas encontrados: {venta_result}")

        if not venta_result:
            print(f"❌ No hay información de ventas para la factura {factura_no}")
            conn.close()
            return render_template('resultado.html', mensaje=f"No hay información de ventas para la factura {factura_no}.")

        # Desempaquetar valores asegurando que son del tipo correcto
        factura, nombre, estado, total, saldo, caja, nequi, bancolombia, datafono, julian, fiado, fecha, concepto = venta_result

        # 🔎 Buscar en `eventos_inventario` los productos asociados a la factura
        cursor.execute("""
            SELECT producto, 
                   CAST(salidas AS FLOAT), 
                   CAST(costo AS FLOAT), 
                   metodo
            FROM eventos_inventario
            WHERE factura_no = %s""", (factura_no,))
        eventos = cursor.fetchall()

        # ✅ Imprimir los productos sin modificar
        print(f"📦 Productos en la factura (antes de conversión): {eventos}")

        # 🔥 Convertir `None` en valores seguros y evitar errores en la plantilla HTML
        eventos_convertidos = [
            (producto, float(salidas) if salidas is not None else 0.0,
             float(costo) if costo is not None else 0.0, 
             metodo if metodo is not None else "pendiente") 
            for producto, salidas, costo, metodo in eventos
        ]

        # ✅ Imprimir los productos después de la conversión
        print(f"📦 Productos en la factura (después de conversión): {eventos_convertidos}")

        conn.close()

        return render_template(
            'resultado.html',
            datos_venta=[factura, nombre, estado, total, saldo, caja, nequi, bancolombia, datafono, julian, fiado, fecha, concepto],
            detalle_eventos=eventos_convertidos
        )

    except Exception as e:
        print(f"❌ Error en la consulta SQL: {e}")
        conn.close()
        return render_template('resultado.html', mensaje=f"Error al consultar la factura {factura_no}.")

@app.route('/lista_precios')
def lista_precios():
    productos = obtener_lista_precios()  # Obtiene los productos y precios
    
    if not productos:
        return render_template('lista_precios.html', mensaje="No se encontraron productos.")

    return render_template('lista_precios.html', productos=productos)

@app.route('/api/inventario')
def obtener_inventario():
    periodo = request.args.get('periodo', 'dia')  # 'dia', 'semana' o 'mes'
    print(f"[DEBUG] Ingresando a /api/inventario con periodo={periodo}")

    conn = connect_db()
    if not conn:
        return jsonify([])

    cursor = conn.cursor()

    # ✅ Verificar tipo de columna 'fecha' en eventos_inventario
    try:
        cursor.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'eventos_inventario' AND column_name = 'fecha';
        """)
        tipo_fecha = cursor.fetchone()

        if tipo_fecha and tipo_fecha[0] == 'text':
            print("⚠️ La columna 'fecha' está en formato TEXT. Convirtiendo a TIMESTAMP...")
            cursor.execute("""
                ALTER TABLE eventos_inventario 
                ALTER COLUMN fecha TYPE TIMESTAMP 
                USING fecha::timestamp;
            """)
            conn.commit()
            print("✅ Columna 'fecha' convertida a TIMESTAMP correctamente.")
        else:
            print("✅ La columna 'fecha' ya es de tipo TIMESTAMP.")
    except Exception as e:
        print(f"❌ Error al validar o convertir el tipo de la columna 'fecha': {e}")
        conn.rollback()

    # 🔹 1️⃣ Obtener horario dinámico
    cursor.execute("SELECT hora_inicial, hora_final FROM horarios ORDER BY id DESC LIMIT 1")
    horario_result = cursor.fetchone()
    hora_inicial, hora_final = horario_result if horario_result else ("12:00", "12:00")
    print(f"[DEBUG] Horario dinámico configurado: {hora_inicial} - {hora_final}")

    # 🔹 2️⃣ Obtener hora actual en zona horaria de Colombia
    zona_colombia = pytz.timezone("America/Bogota")
    ahora_local = datetime.now(zona_colombia)
    print(f"[DEBUG] Hora local (Colombia): {ahora_local.strftime('%Y-%m-%d %H:%M:%S')}")

    hora_actual = ahora_local.time()
    hora_inicial_time = datetime.strptime(hora_inicial, "%H:%M").time()
    hora_final_time = datetime.strptime(hora_final, "%H:%M").time()

    # 🔹 3️⃣ Calcular rango de fechas basado en hora local
    if periodo == "dia":
        fecha_inicio = (ahora_local - timedelta(days=1)).date() if hora_actual < hora_inicial_time else ahora_local.date()
        fecha_fin = fecha_inicio + timedelta(days=1) if hora_final_time <= hora_inicial_time else fecha_inicio
    elif periodo == "semana":
        fecha_inicio = (ahora_local - timedelta(days=ahora_local.weekday())).date()
        fecha_fin = fecha_inicio + timedelta(days=7)
    elif periodo == "mes":
        fecha_inicio = ahora_local.replace(day=1).date()
        fecha_fin = (fecha_inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        return jsonify({"error": "Periodo no válido"}), 400

    # 🔹 4️⃣ Convertimos los límites a UTC para que funcionen con los datos en la base de datos
    limite_inferior = zona_colombia.localize(datetime.combine(fecha_inicio, hora_inicial_time)).astimezone(pytz.utc)
    limite_superior = zona_colombia.localize(datetime.combine(fecha_fin, hora_final_time)).astimezone(pytz.utc)

    print(f"[DEBUG] Periodo seleccionado: {periodo}")
    print(f"[DEBUG] Fecha inicio (sin hora): {fecha_inicio}")
    print(f"[DEBUG] Fecha fin (sin hora): {fecha_fin}")
    print(f"[DEBUG] Hora inicial del periodo: {hora_inicial_time}")
    print(f"[DEBUG] Hora final del periodo: {hora_final_time}")
    print(f"[DEBUG] Rango de consulta en UTC: {limite_inferior} → {limite_superior}")

    # 🔹 5️⃣ Obtener productos y valores iniciales
    cursor.execute("SELECT producto, COALESCE(inicial, 0) FROM productos ORDER BY id ASC")
    productos_rows = cursor.fetchall()
    inventario = {
        row[0]: {"producto": row[0], "inicial": float(row[1]), "entradas": 0, "salidas": 0, "final": float(row[1])}
        for row in productos_rows
    }
    print(f"[DEBUG] Productos obtenidos: {len(inventario)}")

    # 🔹 6️⃣ Inventario anterior al periodo
    cursor.execute("""
        SELECT producto, COALESCE(SUM(entradas - salidas), 0)
        FROM eventos_inventario
        WHERE fecha < %s
        GROUP BY producto;
    """, (limite_inferior,))
    iniciales_rows = cursor.fetchall()

    for producto, cantidad in iniciales_rows:
        if producto in inventario:
            inventario[producto]["inicial"] += cantidad
            inventario[producto]["final"] += cantidad
        else:
            inventario[producto] = {
                "producto": producto, "inicial": cantidad, "entradas": 0, "salidas": 0, "final": cantidad
            }

    print(f"[DEBUG] Inventario inicial actualizado con eventos anteriores")

    # 🔹 7️⃣ Movimientos dentro del período
    cursor.execute("""
        SELECT producto, 
               COALESCE(SUM(entradas), 0) AS entradas, 
               COALESCE(SUM(salidas), 0) AS salidas
        FROM eventos_inventario
        WHERE fecha >= %s AND fecha <= %s
        GROUP BY producto;
    """, (limite_inferior, limite_superior))
    periodo_rows = cursor.fetchall()

    for producto, entradas, salidas in periodo_rows:
        if producto in inventario:
            inventario[producto]["entradas"] += entradas
            inventario[producto]["salidas"] += salidas
            inventario[producto]["final"] += entradas - salidas
        else:
            inventario[producto] = {
                "producto": producto, "inicial": 0, "entradas": entradas,
                "salidas": salidas, "final": entradas - salidas
            }

    print(f"[DEBUG] Inventario final calculado correctamente")

    cursor.close()
    conn.close()
    return jsonify(list(inventario.values()))



@app.route("/api/generar_informe")
def generar_informe():
    id_inicio = request.args.get("id_inicio", "30")

    conn = connect_db()
    cursor = conn.cursor()

    # Verificar tipo de fecha en 'eventos_inventario'
    cursor.execute("""
        SELECT data_type FROM information_schema.columns 
        WHERE table_name = 'eventos_inventario' AND column_name = 'fecha'
    """)
    tipo_fecha = cursor.fetchone()
    if tipo_fecha and tipo_fecha[0] == 'text':
        cursor.execute("""
            ALTER TABLE eventos_inventario
            ALTER COLUMN fecha TYPE TIMESTAMP USING fecha::timestamp
        """)
        conn.commit()

    # Verificar tipo de fecha en 'tiempos'
    cursor.execute("""
        SELECT data_type FROM information_schema.columns 
        WHERE table_name = 'tiempos' AND column_name = 'fecha'
    """)
    tipo_fecha_tiempo = cursor.fetchone()
    if tipo_fecha_tiempo and tipo_fecha_tiempo[0] == 'text':
        cursor.execute("""
            ALTER TABLE tiempos
            ALTER COLUMN fecha TYPE TIMESTAMP USING fecha::timestamp
        """)
        conn.commit()

    # Buscar ID válido
    def buscar_id_valido(base_id):
        while int(base_id) < 9999:
            for sufijo in ["", "-1", "-1P1"]:
                cursor.execute("SELECT fecha FROM eventos_inventario WHERE id = %s LIMIT 1", (f"S{base_id}{sufijo}",))
                row = cursor.fetchone()
                if row:
                    return f"S{base_id}{sufijo}", row[0]
            base_id = str(int(base_id) + 1)
        return None, None

    id_valido, fecha_inicio = buscar_id_valido(id_inicio)
    if not fecha_inicio:
        return jsonify({"error": "No se encontró un ID válido"}), 400

    # Helper para cargar data
    def fetch_df(query, params=()):
        cursor.execute(query, params)
        cols = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    # Cargar datos
    inventario_df = fetch_df("SELECT * FROM eventos_inventario WHERE fecha >= %s", (fecha_inicio,))
    productos_df = fetch_df("SELECT * FROM productos")
    ventas_df = fetch_df("SELECT * FROM ventas WHERE fecha::timestamp >= %s", (fecha_inicio,))
    gastos_df = fetch_df("SELECT * FROM gastos WHERE fecha::timestamp >= %s", (fecha_inicio,))
    costos_df = fetch_df("SELECT * FROM costos WHERE fecha::timestamp >= %s", (fecha_inicio,))
    abonos_df = fetch_df("SELECT * FROM abonos WHERE fecha::timestamp >= %s", (fecha_inicio,))
    flujo_df = fetch_df("SELECT * FROM flujo_dinero")
    tiempos_df = fetch_df("SELECT * FROM tiempos WHERE fecha >= %s", (fecha_inicio,))

    # Inventario
    inventario = {
        row["producto"]: {
            "Precio": row["precio"],
            "Inicial": row["inicial"],
            "Entradas": 0,
            "Salidas": 0,
            "Final": row["inicial"]
        } for _, row in productos_df.iterrows()
    }

    for _, row in inventario_df.iterrows():
        prod = row["producto"]
        if prod in inventario:
            inventario[prod]["Entradas"] += row["entradas"]
            inventario[prod]["Salidas"] += row["salidas"]
            inventario[prod]["Final"] += row["entradas"] - row["salidas"]

    df_inv = pd.DataFrame.from_dict(inventario, orient="index").reset_index().rename(columns={"index": "Producto"})
    df_inv["Valor Venta"] = df_inv["Precio"] * df_inv["Salidas"]

    # Finanzas
    ventas_total = ventas_df["total"].sum()
    ventas_edgar = ventas_df[ventas_df["nombre"].str.lower() == "edgar"]["total"].sum()
    ventas_julian = ventas_total - ventas_edgar

    costos_df["julian"] = costos_df["total"] - costos_df["edgar"]
    gastos_df["julian"] = gastos_df["total"] - gastos_df["edgar"]

    costos_julian = costos_df["julian"].sum()
    costos_edgar = costos_df["edgar"].sum()
    gastos_julian = gastos_df["julian"].sum()
    gastos_edgar = gastos_df["edgar"].sum()

    abonos_edgar = abonos_df["edgar"].sum()
    abono_edgar_positivo = abonos_edgar if abonos_edgar > 0 else 0
    abono_edgar_negativo = abonos_edgar if abonos_edgar < 0 else 0

    inicial_julian = flujo_df[flujo_df["nombre"].str.lower() == "julian"]["inicial"].sum()
    inicial_edgar = flujo_df[flujo_df["nombre"].str.lower() == "edgar"]["inicial"].sum()

    saldo_julian = inicial_julian + ventas_julian - gastos_julian - costos_julian - abono_edgar_positivo + abs(abono_edgar_negativo)
    saldo_edgar = inicial_edgar + ventas_edgar - gastos_edgar - costos_edgar + abono_edgar_positivo - abs(abono_edgar_negativo)

    # Detalles
    df_costos = costos_df.groupby("nombre")[["julian", "edgar"]].sum().reset_index()
    df_gastos = gastos_df.groupby("motivo")[["julian", "edgar"]].sum().reset_index()
    df_abonos = abonos_df[abonos_df["edgar"] != 0][["fecha", "concepto", "edgar"]]

    # Guardar en Excel
    file_path = "/tmp/informe_final.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df_inv.to_excel(writer, sheet_name="Inventario", index=False)
        sheet = writer.sheets["Inventario"]
        workbook = writer.book

        money_format = workbook.add_format({'num_format': '$ #,##0', 'align': 'right'})
        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'align': 'center'})

        # Ajuste columna Producto
        sheet.set_column("A:A", 25)
        sheet.set_column("F:F", 15, money_format)

        # Totales personalizados
        total_venta_productos = df_inv[
            ~df_inv["Producto"].str.upper().str.startswith("TIEMPO")
            & (df_inv["Producto"].str.upper() != "GUANTES ALQUILER")
        ]["Valor Venta"].sum()

        total_tiempos = tiempos_df["total"].sum()

        guantes = inventario.get("GUANTES ALQUILER", {"Salidas": 0, "Precio": 0})
        total_guantes = guantes["Salidas"] * guantes["Precio"]

        total_servicios = total_venta_productos + total_tiempos + total_guantes

        resumen_inv = [
            ["TOTAL VENTA PRODUCTOS", total_venta_productos],
            ["TOTAL TIEMPOS", total_tiempos],
            ["GUANTES ALQUILER", total_guantes],
            ["TOTAL SERVICIOS", total_servicios]
        ]

        for i, (concepto, valor) in enumerate(resumen_inv):
            fila = 3 + i  # J4 -> fila 3
            sheet.write(f"J{fila+1}", concepto, bold)
            sheet.write(f"K{fila+1}", valor, money_format)

        # Hoja Resumen
        resumen = [
            ["VENTA", ventas_julian],
            ["COSTOS", costos_julian],
            ["GASTOS", gastos_julian],
            ["UTILIDAD", ventas_julian - costos_julian - gastos_julian],
            [],
            ["SALDO FINAL JULIAN", saldo_julian],
            ["SALDO FINAL EDGAR", saldo_edgar]
        ]
        df_resumen = pd.DataFrame(resumen, columns=["CONCEPTO", "VALOR"])
        df_resumen.to_excel(writer, sheet_name="Resumen", startrow=1, index=False)

        df_costos.to_excel(writer, sheet_name="Resumen", startrow=12, startcol=0, index=False)
        df_gastos.to_excel(writer, sheet_name="Resumen", startrow=12, startcol=4, index=False)
        df_abonos.to_excel(writer, sheet_name="Resumen", startrow=12, startcol=8, index=False)

        resumen_sheet = writer.sheets["Resumen"]
        resumen_sheet.set_column("A:A", 25, center)
        resumen_sheet.set_column("B:B", 18, money_format)
        resumen_sheet.set_column("E:F", 18, money_format)
        resumen_sheet.set_column("I:J", 18, money_format)
        resumen_sheet.set_column("C:D", 18)
        resumen_sheet.set_column("G:H", 18)
        resumen_sheet.write("A1", f"Resumen desde ID: {id_valido}", bold)

    cursor.close()
    conn.close()

    return send_file(file_path, as_attachment=True, download_name="informe_final.xlsx")


if __name__ == '__main__':
    app.run(debug=True)
