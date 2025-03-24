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
    return jsonify(list(inventario.values()))

@app.route("/api/generar_informe")
def generar_informe():
    id_inicio_str = request.args.get("id_inicio", "30")
    id_fin_str = request.args.get("id_fin", "250")

    conn = connect_db()
    cursor = conn.cursor()

    # 🔹 Verificar y convertir 'fecha' en las tablas donde exista
    tablas_con_fecha = ["eventos_inventario", "tiempos", "ventas", "gastos", "costos", "abonos"]
    for tabla in tablas_con_fecha:
        cursor.execute(f"""
            SELECT data_type 
            FROM information_schema.columns
            WHERE table_name = '{tabla}' AND column_name = 'fecha'
        """)
        col_type = cursor.fetchone()
        if col_type and col_type[0] == "text":
            cursor.execute(f"""
                ALTER TABLE {tabla}
                ALTER COLUMN fecha TYPE TIMESTAMP USING fecha::timestamp
            """)
            conn.commit()

    # 🔹 Función para comprobar si un ID existe en ventas y si está activo o no
    #    Retorna (existe: bool, estado: str|null)
    def verificar_id_ventas(id_buscar: str):
        cursor.execute("""
            SELECT estado, fecha
            FROM ventas
            WHERE id = %s
            LIMIT 1
        """, (id_buscar,))
        row = cursor.fetchone()
        if row:
            return True, row[0], row[1]  # (existe, estado, fecha)
        return False, None, None

    # 🔹 Buscar ID de venta cerrado (no activo), subiendo o bajando en caso de no hallarlo
    #    - modo="inicio": si el ID está activo, sube a id+1
    #    - modo="fin": si el ID está activo, baja a id-1
    def buscar_id_cerrado(base_num: int, modo: str) -> str:
        """Retorna la cadena 'SXX', 'SXX-1' o 'SXX-1P1' que no esté activo,
           o None si no encontró nada."""
        paso = +1 if modo == "inicio" else -1
        limite = 99999 if modo == "inicio" else 0

        while 0 <= base_num <= limite:
            # Probar sufijos en el ID
            for suf in ["", "-1", "-1P1"]:
                id_buscar = f"S{base_num}{suf}"
                existe, estado, _ = verificar_id_ventas(id_buscar)
                if existe and (estado != "activo"):
                    return id_buscar
            base_num += paso
        return None

    # 🔹 Buscar fecha en ventas
    def fecha_de_venta(id_ventas: str):
        """Devuelve la fecha de esa venta (id_ventas) o None si no existe."""
        cursor.execute("""
            SELECT fecha 
            FROM ventas
            WHERE id = %s
            LIMIT 1
        """, (id_ventas,))
        row = cursor.fetchone()
        return row[0] if row else None

    # 1. Convertir string a entero
    try:
        base_inicio = int(id_inicio_str)
    except ValueError:
        base_inicio = 30  # fallback si no es válido
    try:
        base_fin = int(id_fin_str)
    except ValueError:
        base_fin = base_inicio  # fallback

    # 2. Buscar ID inicio cerrado
    id_valido_inicio = buscar_id_cerrado(base_inicio, modo="inicio")
    # 3. Buscar ID fin cerrado
    id_valido_fin = buscar_id_cerrado(base_fin, modo="fin")

    # Si no hallamos nada para el inicio o el fin, error
    if not id_valido_inicio:
        return jsonify({"error": "No se encontró un ID válido (cerrado) para inicio."}), 400
    if not id_valido_fin:
        return jsonify({"error": "No se encontró un ID válido (cerrado) para fin."}), 400

    # Fechas en ventas
    fecha_inicio = fecha_de_venta(id_valido_inicio)
    fecha_fin = fecha_de_venta(id_valido_fin)
    if not fecha_inicio:
        return jsonify({"error": f"No existe venta con ID {id_valido_inicio}"}), 400
    if not fecha_fin:
        return jsonify({"error": f"No existe venta con ID {id_valido_fin}"}), 400

    # Helper para filtrar por rango de fechas (ventas, costos, etc.), excluyendo estado=activo
    def fetch_df_ventas(query_base, params=()):
        """Filtra la tabla x con: fecha >= fecha_inicio, fecha <= fecha_fin, estado <> 'activo'."""
        nuevo_query = query_base + " AND estado <> 'activo'"
        nuevo_params = list(params)

        nuevo_query += " AND fecha >= %s"
        nuevo_params.append(fecha_inicio)

        if fecha_fin:
            nuevo_query += " AND fecha <= %s"
            nuevo_params.append(fecha_fin)

        cursor.execute(nuevo_query, tuple(nuevo_params))
        cols = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    # events no tiene estado, ni productos
    def fetch_df_eventos(query_base, params=()):
        """Filtra la tabla eventos_inventario con fecha >= inicio y <= fin (no hay estado)."""
        nuevo_query = query_base
        nuevo_params = list(params)
        nuevo_query += " AND fecha >= %s"
        nuevo_params.append(fecha_inicio)
        if fecha_fin:
            nuevo_query += " AND fecha <= %s"
            nuevo_params.append(fecha_fin)

        cursor.execute(nuevo_query, tuple(nuevo_params))
        cols = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    # Cargar data
    inventario_df = fetch_df_eventos("SELECT * FROM eventos_inventario WHERE 1=1")
    
    # productos no tiene fecha ni estado
    cursor.execute("SELECT * FROM productos")
    col_products = [desc[0] for desc in cursor.description]
    productos_df = pd.DataFrame(cursor.fetchall(), columns=col_products)

    ventas_df = fetch_df_ventas("SELECT * FROM ventas WHERE 1=1")
    gastos_df = fetch_df_ventas("SELECT * FROM gastos WHERE 1=1")
    costos_df = fetch_df_ventas("SELECT * FROM costos WHERE 1=1")
    abonos_df = fetch_df_ventas("SELECT * FROM abonos WHERE 1=1")

    # tiempos no tiene estado
    cursor.execute("SELECT * FROM tiempos WHERE fecha >= %s", (fecha_inicio,))
    col_tiempos = [desc[0] for desc in cursor.description]
    tiempos_tmp = cursor.fetchall()
    # si existe fecha_fin
    if fecha_fin:
        tiempos_filtrados = []
        for row in tiempos_tmp:
            # asumiendo row[1] es fecha
            # Veamos la posicion: definimos col_tiempos
            row_dict = dict(zip(col_tiempos, row))
            if row_dict["fecha"] and row_dict["fecha"] <= fecha_fin:
                tiempos_filtrados.append(row)
        tiempos_df = pd.DataFrame(tiempos_filtrados, columns=col_tiempos)
    else:
        tiempos_df = pd.DataFrame(tiempos_tmp, columns=col_tiempos)

    # flujo_dinero no tiene fecha ni estado
    cursor.execute("SELECT * FROM flujo_dinero")
    col_flujo = [desc[0] for desc in cursor.description]
    flujo_df = pd.DataFrame(cursor.fetchall(), columns=col_flujo)

    # Acumulado anterior
    ventas_antes = pd.DataFrame()
    gastos_antes = pd.DataFrame()
    costos_antes = pd.DataFrame()
    abonos_antes = pd.DataFrame()

    # Filtramos las que estén antes de fecha_inicio
    # y estado <> 'activo'
    def fetch_df_antes_ventas(tabla: str):
        cursor.execute(f"""
            SELECT * FROM {tabla}
            WHERE fecha < %s AND estado <> 'activo'
        """, (fecha_inicio,))
        c = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=c)

    ventas_antes = fetch_df_antes_ventas("ventas")
    gastos_antes = fetch_df_antes_ventas("gastos")
    costos_antes = fetch_df_antes_ventas("costos")
    abonos_antes = fetch_df_antes_ventas("abonos")

    total_ventas_antes = ventas_antes["total"].sum()
    ventas_edgar_antes = ventas_antes[ventas_antes["nombre"].str.lower() == "edgar"]["total"].sum()
    ventas_julian_antes = total_ventas_antes - ventas_edgar_antes

    costos_antes["julian"] = costos_antes["total"] - costos_antes["edgar"]
    costos_julian_antes = costos_antes["julian"].sum()
    costos_edgar_antes = costos_antes["edgar"].sum()

    gastos_antes["julian"] = gastos_antes["total"] - gastos_antes["edgar"]
    gastos_julian_antes = gastos_antes["julian"].sum()
    gastos_edgar_antes = gastos_antes["edgar"].sum()

    abonos_edgar_antes = abonos_antes["edgar"].sum()
    abono_edgar_positivo_antes = abonos_edgar_antes if abonos_edgar_antes > 0 else 0
    abono_edgar_negativo_antes = abonos_edgar_antes if abonos_edgar_antes < 0 else 0

    inicial_julian = flujo_df[flujo_df["nombre"].str.lower() == "julian"]["inicial"].sum()
    inicial_edgar = flujo_df[flujo_df["nombre"].str.lower() == "edgar"]["inicial"].sum()

    acumulado_julian = (inicial_julian + ventas_julian_antes 
                        - gastos_julian_antes - costos_julian_antes 
                        - abono_edgar_positivo_antes + abs(abono_edgar_negativo_antes))
    acumulado_edgar = (inicial_edgar + ventas_edgar_antes 
                       - gastos_edgar_antes - costos_edgar_antes 
                       + abono_edgar_positivo_antes - abs(abono_edgar_negativo_antes))

    # Construir inventario EXCLUYENDO productos TIEMPO
    inventario = {}
    for _, rowp in productos_df.iterrows():
        inventario[rowp["producto"]] = {
            "Precio": rowp["precio"],
            "Inicial": rowp["inicial"],
            "Entradas": 0,
            "Salidas": 0,
            "Final": rowp["inicial"]
        }

    for _, row in inventario_df.iterrows():
        p = row["producto"]
        if p.upper().startswith("TIEMPO"):
            # Lo excluimos
            continue
        if p in inventario:
            inventario[p]["Entradas"] += row["entradas"]
            inventario[p]["Salidas"] += row["salidas"]
            inventario[p]["Final"] += (row["entradas"] - row["salidas"])

    df_inv = pd.DataFrame.from_dict(inventario, orient="index").reset_index().rename(columns={"index": "Producto"})
    df_inv["Valor Venta"] = df_inv["Precio"] * df_inv["Salidas"]

    # Cálculo total_servicios
    total_venta_productos = df_inv[
        ~df_inv["Producto"].str.upper().str.startswith("TIEMPO") &
        (df_inv["Producto"].str.upper() != "GUANTES ALQUILER")
    ]["Valor Venta"].sum()

    # Tiempos
    total_tiempos = tiempos_df["total"].sum() if "total" in tiempos_df.columns else 0

    # Guantes
    guantes_data = inventario.get("GUANTES ALQUILER", {"Salidas": 0, "Precio": 0})
    total_guantes = guantes_data["Salidas"] * guantes_data["Precio"]

    total_servicios = total_venta_productos + total_tiempos + total_guantes

    # Ventas
    ventas_edgar = ventas_df[ventas_df["nombre"].str.lower() == "edgar"]["total"].sum()
    ventas_julian = total_servicios - ventas_edgar

    costos_df["julian"] = costos_df["total"] - costos_df["edgar"]
    gastos_df["julian"] = gastos_df["total"] - gastos_df["edgar"]
    costos_julian = costos_df["julian"].sum()
    costos_edgar = costos_df["edgar"].sum()
    gastos_julian = gastos_df["julian"].sum()
    gastos_edgar = gastos_df["edgar"].sum()
    abonos_edgar = abonos_df["edgar"].sum()
    abono_edgar_positivo = abonos_edgar if abonos_edgar > 0 else 0
    abono_edgar_negativo = abonos_edgar if abonos_edgar < 0 else 0

    saldo_final_julian = (acumulado_julian + ventas_julian 
                          - gastos_julian - costos_julian 
                          - abono_edgar_positivo + abs(abono_edgar_negativo))
    saldo_final_edgar = (acumulado_edgar + ventas_edgar 
                         - gastos_edgar - costos_edgar 
                         + abono_edgar_positivo - abs(abono_edgar_negativo))

    # Agrupaciones
    df_costos = costos_df.groupby("nombre", dropna=False)[["julian", "edgar"]].sum().reset_index()
    df_gastos = gastos_df.groupby("motivo", dropna=False)[["julian", "edgar"]].sum().reset_index()
    df_abonos = abonos_df[abonos_df["edgar"] != 0][["fecha", "concepto", "edgar"]]

    # Generar Excel
    file_path = "/tmp/informe_final.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        # Hoja: Inventario
        df_inv.to_excel(writer, sheet_name="Inventario", index=False)
        sheet = writer.sheets["Inventario"]
        book = writer.book
        money = book.add_format({'num_format': '$ #,##0', 'align': 'right'})
        bold = book.add_format({'bold': True})
        center = book.add_format({'align': 'center'})

        sheet.set_column("A:A", 25)
        sheet.set_column("F:F", 15)      # Final
        sheet.set_column("G:G", 18, money)  # Valor Venta

        # Totales en la Hoja Inventario
        inventario_resumen = [
            ["TOTAL VENTA PRODUCTOS", total_venta_productos],
            ["TOTAL TIEMPOS", total_tiempos],
            ["GUANTES ALQUILER", total_guantes],
            ["TOTAL SERVICIOS", total_servicios],
        ]
        start_row = 3
        for i, (desc, val) in enumerate(inventario_resumen):
            sheet.write(f"J{start_row+i}", desc, bold)
            sheet.write(f"K{start_row+i}", val, money)

        # Hoja Resumen
        df_res = [
            ["VENTA", ventas_julian],
            ["COSTOS", costos_julian],
            ["GASTOS", gastos_julian],
            ["UTILIDAD", ventas_julian - costos_julian - gastos_julian],
            [],
            ["ACUMULADO JULIAN (antes)", acumulado_julian],
            ["ACUMULADO EDGAR (antes)", acumulado_edgar],
            [],
            ["SALDO FINAL JULIAN", saldo_final_julian],
            ["SALDO FINAL EDGAR", saldo_final_edgar],
        ]
        df_resumen = pd.DataFrame(df_res, columns=["CONCEPTO", "VALOR"])
        df_resumen.to_excel(writer, sheet_name="Resumen", startrow=1, index=False)

        # Costos/Gastos/Abonos
        df_costos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=0, index=False)
        df_gastos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=4, index=False)
        df_abonos.to_excel(writer, sheet_name="Resumen", startrow=14, startcol=8, index=False)

        resumen_sheet = writer.sheets["Resumen"]
        resumen_sheet.set_column("A:A", 45, center)
        resumen_sheet.set_column("B:B", 18, money)
        resumen_sheet.set_column("E:F", 18, money)
        resumen_sheet.set_column("I:J", 18, money)

        # Titulo: "Resumen desde ID: SXX hasta ID: SYY"
        titulo = f"Resumen desde {id_valido_inicio}"
        if id_valido_fin:
            titulo += f" hasta {id_valido_fin}"
        resumen_sheet.write("A1", titulo, bold)

    cursor.close()
    conn.close()

    return send_file(file_path, as_attachment=True, download_name="informe_final.xlsx")




if __name__ == '__main__':
    app.run(debug=True)
