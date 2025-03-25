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
    limite_inferior = datetime.combine(fecha_inicio, hora_inicial_time)
    limite_superior = datetime.combine(fecha_fin, hora_final_time)

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
    # 🔹 8️⃣ Filtrar productos que comienzan con "TIEMPO"
    inventario_filtrado = [
        item for item in inventario.values()
        if not item["producto"].strip().upper().startswith("TIEMPO")
    ]

    return jsonify(inventario_filtrado)



@app.route("/api/generar_informe")
def generar_informe():
    id_inicio_str = request.args.get("id_inicio", "1")
    id_fin_str = request.args.get("id_fin", "")

    conn = connect_db()
    cursor = conn.cursor()

    def verificar_columna_fecha(tabla):
        cursor.execute(f"""
            SELECT data_type FROM information_schema.columns 
            WHERE table_name = '{tabla}' AND column_name = 'fecha'
        """)
        tipo = cursor.fetchone()
        if tipo and tipo[0] == 'text':
            cursor.execute(f"""
                ALTER TABLE {tabla}
                ALTER COLUMN fecha TYPE TIMESTAMP USING fecha::timestamp
            """)
            conn.commit()

    for tabla in ["eventos_inventario", "tiempos", "ventas", "gastos", "costos", "abonos"]:
        verificar_columna_fecha(tabla)

    # Esta parte se mantiene igual: se busca la fecha_inicio, fecha_fin en la tabla eventos_inventario
    # a partir de 'id_inicio' y 'id_fin'...
    def buscar_fecha_por_id(base_id):
        for sufijo in ["", "-1", "-1P1"]:
            id_buscar = f"S{base_id}{sufijo}"
            cursor.execute("SELECT fecha FROM eventos_inventario WHERE id = %s LIMIT 1", (id_buscar,))
            row = cursor.fetchone()
            if row:
                return id_buscar, row[0]
        return None, None

    id_valido, fecha_inicio = buscar_fecha_por_id(id_inicio_str)
    fecha_fin = None
    if id_fin_str:
        _, fecha_val = buscar_fecha_por_id(id_fin_str)
        fecha_fin = fecha_val  # podría ser None si no existe

    if not fecha_inicio:
        return jsonify({"error": "No se encontró un ID válido"}), 400

    # Helper con rango de fechas
    def fetch_df(query_base, params=()):
        if fecha_fin:
            query = query_base + " AND fecha <= %s"
            params = params + (fecha_fin,)
        else:
            query = query_base
        cursor.execute(query, params)
        cols = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    # 🔹 1. Convertir id_inicio_str e id_fin_str a enteros
    try:
        base_inicio = int(id_inicio_str)
    except ValueError:
        base_inicio = 1
    try:
        base_fin = int(id_fin_str) if id_fin_str else base_inicio
    except ValueError:
        base_fin = base_inicio
    # Asegurarnos de que base_inicio <= base_fin
    if base_inicio > base_fin:
        base_inicio, base_fin = base_fin, base_inicio

    # 🔹 2. Con ese rango, ver qué IDs en la tabla `ventas` no están activos
    ids_cerrados = []
    for num in range(base_inicio, base_fin + 1):
        s_id = f"S{num}"
        cursor.execute("""
            SELECT estado FROM ventas
            WHERE id = %s LIMIT 1
        """, (s_id,))
        row = cursor.fetchone()
        if row:
            estado = (row[0] or "").lower()
            if estado != "activo":
                # Se agrega a la lista
                ids_cerrados.append(num)

    # Si no hay IDs válidos en ventas, no hay nada que incluir
    if not ids_cerrados:
        return jsonify({"error": "Ningún ID en ventas está cerrado (no activo) en el rango dado"}), 400

    # 🔹 3. Cargar todos los IDs existentes de eventos_inventario
    cursor.execute("SELECT id FROM eventos_inventario")
    todos_los_ids_eventos = [row[0] for row in cursor.fetchall()]

    # 🔹 4. Filtrar los que comienzan con alguno de los IDs cerrados
    eventos_ids = []
    for eid in todos_los_ids_eventos:
        base = eid.split("-")[0]  # De "S200-1P1" => "S200"
        try:
            num = int(base[1:])   # De "S200" => 200
        except:
            continue
        if num in ids_cerrados:
            eventos_ids.append(eid)

    print("🧩 Sub-IDs válidos encontrados en eventos_inventario:", eventos_ids)

    # 🔹 5. Cargar datos filtrando esos IDs + fecha
    if not eventos_ids:
        return jsonify({"error": "No hay IDs válidos para eventos_inventario"}), 400

    placeholders = ",".join(["%s"] * len(eventos_ids))
    query_inv = f"SELECT * FROM eventos_inventario WHERE id IN ({placeholders}) AND fecha >= %s"
    params_inv = tuple(eventos_ids) + (fecha_inicio,)
    if fecha_fin:
        query_inv += " AND fecha <= %s"
        params_inv += (fecha_fin,)

    cursor.execute(query_inv, params_inv)
    inv_cols = [desc[0] for desc in cursor.description]
    inv_rows = cursor.fetchall()
    inventario_df = pd.DataFrame(inv_rows, columns=inv_cols)

    # 🔹 5. El resto lo dejas IGUAL que en tu función original:

    # Cargar productos sin filtros
    cursor.execute("SELECT * FROM productos")
    cols = [desc[0] for desc in cursor.description]
    productos_df = pd.DataFrame(cursor.fetchall(), columns=cols)

    # Ventas, gastos, costos, abonos, tiempos => siguen por fecha
    ventas_df = fetch_df("SELECT * FROM ventas WHERE fecha >= %s", (fecha_inicio,))
    gastos_df = fetch_df("SELECT * FROM gastos WHERE fecha >= %s", (fecha_inicio,))
    costos_df = fetch_df("SELECT * FROM costos WHERE fecha >= %s", (fecha_inicio,))
    abonos_df = fetch_df("SELECT * FROM abonos WHERE fecha >= %s", (fecha_inicio,))
    tiempos_df = fetch_df("SELECT * FROM tiempos WHERE fecha >= %s", (fecha_inicio,))

    # flujo_dinero sin fecha
    cursor.execute("SELECT * FROM flujo_dinero")
    cols = [desc[0] for desc in cursor.description]
    flujo_df = pd.DataFrame(cursor.fetchall(), columns=cols)

    # ---------- Acumulado antes del periodo (igual que antes) ----------
    ventas_antes = fetch_df("SELECT * FROM ventas WHERE fecha < %s", (fecha_inicio,))
    costos_antes = fetch_df("SELECT * FROM costos WHERE fecha < %s", (fecha_inicio,))
    gastos_antes = fetch_df("SELECT * FROM gastos WHERE fecha < %s", (fecha_inicio,))
    abonos_antes = fetch_df("SELECT * FROM abonos WHERE fecha < %s", (fecha_inicio,))

    total_ventas_antes = ventas_antes["total"].sum()
    ventas_edgar_antes = ventas_antes[ventas_antes["nombre"].str.lower() == "edgar"]["total"].sum()
    ventas_julian_antes = total_ventas_antes - ventas_edgar_antes

    costos_julian_antes = (costos_antes["total"] - costos_antes["edgar"]).sum()
    costos_edgar_antes = costos_antes["edgar"].sum()
    gastos_julian_antes = (gastos_antes["total"] - gastos_antes["edgar"]).sum()
    gastos_edgar_antes = gastos_antes["edgar"].sum()

    abonos_edgar_antes = abonos_antes["edgar"].sum()
    abono_edgar_positivo_antes = abonos_edgar_antes if abonos_edgar_antes > 0 else 0
    abono_edgar_negativo_antes = abonos_edgar_antes if abonos_edgar_antes < 0 else 0

    inicial_julian = flujo_df[flujo_df["nombre"].str.lower() == "julian"]["inicial"].sum()
    inicial_edgar = flujo_df[flujo_df["nombre"].str.lower() == "edgar"]["inicial"].sum()

    acumulado_julian = (
        inicial_julian + ventas_julian_antes 
        - gastos_julian_antes - costos_julian_antes 
        - abono_edgar_positivo_antes + abs(abono_edgar_negativo_antes)
    )
    acumulado_edgar = (
        inicial_edgar + ventas_edgar_antes 
        - gastos_edgar_antes - costos_edgar_antes 
        + abono_edgar_positivo_antes - abs(abono_edgar_negativo_antes)
    )

    # ---------- Inventario (igual) ----------
    inventario = {
        rowp["producto"]: {
            "Precio": rowp["precio"],
            "Inicial": rowp["inicial"],
            "Entradas": 0,
            "Salidas": 0,
            "Final": rowp["inicial"]
        }
        for _, rowp in productos_df.iterrows()
    }

    for _, row in inventario_df.iterrows():
        p = row["producto"]
        if p in inventario:
            inventario[p]["Entradas"] += row["entradas"]
            inventario[p]["Salidas"] += row["salidas"]
            inventario[p]["Final"] += (row["entradas"] - row["salidas"])

    df_inv = pd.DataFrame.from_dict(inventario, orient="index").reset_index().rename(columns={"index": "Producto"})
    df_inv["Valor Venta"] = df_inv["Precio"] * df_inv["Salidas"]

    # ---------- Totales (igual) ----------
    total_venta_productos = df_inv[
        ~df_inv["Producto"].str.upper().str.startswith("TIEMPO")
        & (df_inv["Producto"].str.upper() != "GUANTES ALQUILER")
    ]["Valor Venta"].sum()

    total_tiempos = tiempos_df["total"].sum()  # si la tabla 'tiempos' si las maneja
    guantes = inventario.get("GUANTES ALQUILER", {"Salidas": 0, "Precio": 0})
    total_guantes = guantes["Salidas"] * guantes["Precio"]

    total_servicios = total_venta_productos + total_tiempos + total_guantes

    # => "VENTA" en Resumen = total_servicios
    ventas_total = total_servicios

    # Ventas Edgar
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

    saldo_final_julian = (
        acumulado_julian + ventas_julian 
        - gastos_julian - costos_julian 
        - abono_edgar_positivo + abs(abono_edgar_negativo)
    )
    saldo_final_edgar = (
        acumulado_edgar + ventas_edgar 
        - gastos_edgar - costos_edgar 
        + abono_edgar_positivo - abs(abono_edgar_negativo)
    )

    df_costos = costos_df.groupby("nombre")[["julian", "edgar"]].sum().reset_index()
    df_gastos = gastos_df.groupby("motivo")[["julian", "edgar"]].sum().reset_index()
    df_abonos = abonos_df[abonos_df["edgar"] != 0][["fecha", "concepto", "edgar"]]

    # ---------- Exportar a Excel (igual) ----------
    import xlsxwriter
    file_path = "/tmp/informe_final.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df_inv.to_excel(writer, sheet_name="Inventario", index=False)
        sheet = writer.sheets["Inventario"]
        book = writer.book

        money_fmt = book.add_format({'num_format': '$ #,##0', 'align': 'right'})
        bold = book.add_format({'bold': True})
        center = book.add_format({'align': 'center'})

        sheet.set_column("A:A", 25)
        sheet.set_column("F:F", 15)
        sheet.set_column("G:G", 18, money_fmt)

        resumen_inv = [
            ["TOTAL VENTA PRODUCTOS", total_venta_productos],
            ["TOTAL TIEMPOS", total_tiempos],
            ["GUANTES ALQUILER", total_guantes],
            ["TOTAL SERVICIOS", total_servicios],
        ]
        start_row = 3
        for i, (concepto, valor) in enumerate(resumen_inv):
            sheet.write(f"J{start_row + i}", concepto, bold)
            sheet.write(f"K{start_row + i}", valor, money_fmt)

        # Hoja Resumen
        resumen_data = [
            ["VENTA", ventas_total],  # = total_servicios
            ["COSTOS", costos_julian],
            ["GASTOS", gastos_julian],
            ["UTILIDAD", ventas_total - costos_julian - gastos_julian],
            [],
            ["ACUMULADO JULIAN (antes)", acumulado_julian],
            ["ACUMULADO EDGAR (antes)", acumulado_edgar],
            [],
            ["SALDO FINAL JULIAN", saldo_final_julian],
            ["SALDO FINAL EDGAR", saldo_final_edgar],
        ]
        df_resumen = pd.DataFrame(resumen_data, columns=["CONCEPTO", "VALOR"])
        df_resumen.to_excel(writer, sheet_name="Resumen", startrow=1, index=False)

        df_costos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=0, index=False)
        df_gastos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=4, index=False)
        df_abonos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=8, index=False)

        sht_resumen = writer.sheets["Resumen"]
        sht_resumen.set_column("A:A", 35, center)
        sht_resumen.set_column("B:B", 18, money_fmt)
        sht_resumen.set_column("E:F", 18, money_fmt)
        sht_resumen.set_column("I:J", 18, money_fmt)
        sht_resumen.write("A1", f"Resumen desde ID: {id_valido}", bold)

    cursor.close()
    conn.close()
    return send_file(file_path, as_attachment=True, download_name="informe_final.xlsx")



if __name__ == '__main__':
    app.run(debug=True)
