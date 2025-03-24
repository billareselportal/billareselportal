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
        WHERE fecha < %s AND producto NOT ILIKE 'TIEMPO%'
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
        WHERE fecha >= %s AND fecha <= %s AND producto NOT ILIKE 'TIEMPO%'
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
    from flask import request, jsonify, send_file
    import pandas as pd
    import xlsxwriter

    # 1. Leer parámetros id_inicio, id_fin
    id_inicio_str = request.args.get("id_inicio", "").strip()
    id_fin_str = request.args.get("id_fin", "").strip()

    conn = connect_db()
    cursor = conn.cursor()

    # Función auxiliar para convertir el ID 'S999' → numérico 999
    def id_a_num(s: str) -> int:
        try:
            return int(s)
        except ValueError:
            return 0

    # Si no se proporcionó id_inicio, buscar el primer ID cerrado en ventas
    if not id_inicio_str:
        cursor.execute("""
            SELECT id 
            FROM ventas
            WHERE estado <> 'activo'
              AND id ~ '^S[0-9]+$'
            ORDER BY CAST(SUBSTRING(id FROM 2) AS INTEGER) ASC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            id_inicio_str = row[0][1:]  # quitar la 'S'
        else:
            return jsonify({"error": "No existen IDs cerrados en la base de datos"}), 400

    # Si no se proporcionó id_fin, buscar el último ID cerrado en ventas
    if not id_fin_str:
        cursor.execute("""
            SELECT id 
            FROM ventas
            WHERE estado <> 'activo'
              AND id ~ '^S[0-9]+$'
            ORDER BY CAST(SUBSTRING(id FROM 2) AS INTEGER) DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            id_fin_str = row[0][1:]  # quitar la 'S'
        else:
            return jsonify({"error": "No existen IDs cerrados en la base de datos"}), 400

    # Convertir a entero
    try:
        base_inicio = int(id_inicio_str)
    except ValueError:
        base_inicio = 1
    try:
        base_fin = int(id_fin_str)
    except ValueError:
        base_fin = base_inicio

    if base_inicio > base_fin:
        # si el inicio es mayor que el fin, intercambiarlos
        base_inicio, base_fin = base_fin, base_inicio

    # IDs cerrados en el rango [base_inicio..base_fin]
    ids_cerrados = []
    for num in range(base_inicio, base_fin + 1):
        s_id = f"S{num}"
        # verificar si en ventas id=s_id con estado <> 'activo'
        cursor.execute("""
            SELECT estado FROM ventas
            WHERE id = %s
            LIMIT 1
        """, (s_id,))
        row = cursor.fetchone()
        if row:
            estado = (row[0] or "").lower()
            if estado != "activo":
                # cerrado
                ids_cerrados.append(num)

    if not ids_cerrados:
        return jsonify({"error": f"No hay IDs cerrados en el rango [{base_inicio}..{base_fin}]"}), 400

    # Ahora construimos los sub-IDs para buscar en eventos_inventario
    eventos_ids = []
    for num in ids_cerrados:
        base_id = f"S{num}"
        eventos_ids.append(base_id)
        eventos_ids.append(base_id + "-1")
        eventos_ids.append(base_id + "-1P1")

    # Cargar eventos_inventario con esos IDs
    format_str = ",".join(["%s"] * len(eventos_ids))
    query = f"SELECT * FROM eventos_inventario WHERE id IN ({format_str})"
    cursor.execute(query, tuple(eventos_ids))
    inv_rows = cursor.fetchall()
    inv_cols = [desc[0] for desc in cursor.description]
    inventario_df = pd.DataFrame(inv_rows, columns=inv_cols)

    # Cargar productos (no tiene fecha ni estado)
    cursor.execute("SELECT * FROM productos")
    prod_rows = cursor.fetchall()
    prod_cols = [desc[0] for desc in cursor.description]
    productos_df = pd.DataFrame(prod_rows, columns=prod_cols)

    # Construir inventario excluyendo TIEMPO
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
            # excluimos
            continue
        if p in inventario:
            inventario[p]["Entradas"] += row["entradas"]
            inventario[p]["Salidas"] += row["salidas"]
            inventario[p]["Final"] += (row["entradas"] - row["salidas"])

    df_inv = pd.DataFrame.from_dict(inventario, orient="index").reset_index().rename(columns={"index": "Producto"})
    df_inv["Valor Venta"] = df_inv["Precio"] * df_inv["Salidas"]

    # Cálculo: sumamos Valor Venta excluyendo TIEMPO y GUANTES ALQUILER
    df_excl = df_inv[~df_inv["Producto"].str.upper().str.startswith("TIEMPO") &
                     (df_inv["Producto"].str.upper() != "GUANTES ALQUILER")]
    total_venta_productos = df_excl["Valor Venta"].sum()

    # Guantes
    guantes_info = inventario.get("GUANTES ALQUILER", {"Salidas": 0, "Precio": 0})
    total_guantes = guantes_info["Salidas"] * guantes_info["Precio"]

    # Sin filtrar tiempos_df, pues no hay fecha
    total_tiempos = 0
    total_servicios = total_venta_productos + total_tiempos + total_guantes

    # Generar Excel
    file_path = "/tmp/informe_final.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df_inv.to_excel(writer, sheet_name="Inventario", index=False)
        sheet = writer.sheets["Inventario"]

        money_fmt = writer.book.add_format({'num_format': '$ #,##0', 'align': 'right'})
        bold = writer.book.add_format({'bold': True})

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
        for i, (label, val) in enumerate(resumen_inv):
            sheet.write(f"J{start_row + i}", label, bold)
            sheet.write(f"K{start_row + i}", val, money_fmt)

        # Hoja Resumen
        df_resumen = pd.DataFrame([
            ["VENTA (SERVICIOS)", total_servicios],
            ["COSTOS", 0],
            ["GASTOS", 0],
            ["UTILIDAD", total_servicios - 0 - 0],
        ], columns=["CONCEPTO", "VALOR"])
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)

        sht_resumen = writer.sheets["Resumen"]
        sht_resumen.set_column("A:A", 35)
        sht_resumen.set_column("B:B", 18, money_fmt)
        titulo = f"Informe desde {base_inicio} hasta {base_fin} (IDs cerrados en ventas)"
        sht_resumen.write("A1", titulo, bold)

    cursor.close()
    conn.close()

    return send_file(file_path, as_attachment=True, download_name="informe_final.xlsx")



if __name__ == '__main__':
    app.run(debug=True)
