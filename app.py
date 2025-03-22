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
    print(f"[DEBUG] Horario dinámico: {hora_inicial} - {hora_final}")

    # 🔹 2️⃣ Convertir hora actual a UTC
    zona_horaria_utc = pytz.utc
    ahora = datetime.utcnow().replace(tzinfo=zona_horaria_utc)
    hora_actual = ahora.time()
    hora_inicial_time = datetime.strptime(hora_inicial, "%H:%M").time()
    hora_final_time = datetime.strptime(hora_final, "%H:%M").time()

    # 🔹 3️⃣ Calcular rango de fechas
    if periodo == "dia":
        fecha_inicio = (ahora - timedelta(days=1)).date() if hora_actual < hora_inicial_time else ahora.date()
        fecha_fin = fecha_inicio + timedelta(days=1) if hora_final_time <= hora_inicial_time else fecha_inicio
    elif periodo == "semana":
        fecha_inicio = (ahora - timedelta(days=ahora.weekday())).date()
        fecha_fin = fecha_inicio + timedelta(days=7)
    elif periodo == "mes":
        fecha_inicio = ahora.replace(day=1).date()
        fecha_fin = (fecha_inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        return jsonify({"error": "Periodo no válido"}), 400

    limite_inferior = datetime.combine(fecha_inicio, hora_inicial_time).replace(tzinfo=zona_horaria_utc)
    limite_superior = datetime.combine(fecha_fin, hora_final_time).replace(tzinfo=zona_horaria_utc)
    print(f"[DEBUG] Rango de consulta en UTC: {limite_inferior} → {limite_superior}")

    # 🔹 4️⃣ Obtener productos y valores iniciales
    cursor.execute("SELECT producto, COALESCE(inicial, 0) FROM productos ORDER BY id ASC")
    productos_rows = cursor.fetchall()
    inventario = {
        row[0]: {"producto": row[0], "inicial": float(row[1]), "entradas": 0, "salidas": 0, "final": float(row[1])}
        for row in productos_rows
    }
    print(f"[DEBUG] Productos obtenidos: {len(inventario)}")

    # 🔹 5️⃣ Inventario anterior al periodo
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
    print(f"[DEBUG] Inventario inicial actualizado con eventos_inventario")

    # 🔹 6️⃣ Movimientos dentro del período
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

    print(f"[DEBUG] Inventario final calculado")

    cursor.close()
    conn.close()
    return jsonify(list(inventario.values()))

@app.route('/api/generar_informe')
def generar_informe():
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    id_inicio = request.args.get('id_inicio')
    id_fin = request.args.get('id_fin')

    # Transforma el ID numérico a formato alfanumérico S{id}
    if id_inicio:
        id_inicio = f"S{id_inicio}"
    if id_fin:
        id_fin = f"S{id_fin}"

    conn = connect_db()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500

    cursor = conn.cursor()

    where_clause = ""
    filtro_usado = ""

    if id_inicio:
        if not id_fin:
            cursor.execute("SELECT id FROM eventos_inventario WHERE id LIKE 'S%' ORDER BY id DESC LIMIT 1")
            id_fin = cursor.fetchone()[0]
        where_clause = f"id >= '{id_inicio}' AND id <= '{id_fin}'"
        filtro_usado = f"Desde ID: {id_inicio} hasta ID: {id_fin}"
    elif fecha_inicio and fecha_fin:
        where_clause = f"fecha >= '{fecha_inicio}' AND fecha <= '{fecha_fin}'"
        filtro_usado = f"Desde fecha: {fecha_inicio} hasta fecha: {fecha_fin}"
    else:
        return jsonify({"error": "Debe especificar un rango de fechas o un rango de ID"}), 400

    ### 🔹 1️⃣ OBTENER INVENTARIO ###
    cursor.execute(f"""
        SELECT producto, COALESCE(SUM(entradas), 0) AS entradas, 
               COALESCE(SUM(salidas), 0) AS salidas
        FROM eventos_inventario
        WHERE {where_clause}
        GROUP BY producto
    """)
    inventario_data = cursor.fetchall()
    df_inventario = pd.DataFrame(inventario_data, columns=["Producto", "Entradas", "Salidas"])

    cursor.execute("""
        SELECT producto, COALESCE(inicial, 0) 
        FROM productos
    """)
    iniciales = {row[0]: row[1] for row in cursor.fetchall()}

    df_inventario["Inicial"] = df_inventario["Producto"].map(iniciales)
    df_inventario["Final"] = df_inventario["Inicial"] + df_inventario["Entradas"] - df_inventario["Salidas"]

    ### 🔹 2️⃣ OBTENER RESUMEN FINANCIERO ###
    cursor.execute(f"""
        SELECT nombre, COALESCE(SUM(total), 0) 
        FROM ventas 
        WHERE saldo = 0 AND {where_clause}
        GROUP BY nombre
    """)
    ventas_totales = dict(cursor.fetchall())

    cursor.execute(f"""
        SELECT nombre, COALESCE(SUM(valor), 0) 
        FROM costos 
        WHERE {where_clause}
        GROUP BY nombre
    """)
    costos_totales = dict(cursor.fetchall())

    cursor.execute(f"""
        SELECT nombre, COALESCE(SUM(valor), 0) 
        FROM gastos 
        WHERE {where_clause}
        GROUP BY nombre
    """)
    gastos_totales = dict(cursor.fetchall())

    cursor.execute(f"""
        SELECT nombre, COALESCE(SUM(valor), 0) 
        FROM abonos 
        WHERE {where_clause}
        GROUP BY nombre
    """)
    abonos_totales = dict(cursor.fetchall())

    cursor.execute("SELECT nombre, COALESCE(inicial, 0) FROM flujo_dinero")
    iniciales_dinero = {row[0]: row[1] for row in cursor.fetchall()}

    finanzas_data = []
    for nombre in iniciales_dinero.keys():
        inicial = iniciales_dinero.get(nombre, 0)
        ingresos = ventas_totales.get(nombre, 0)
        costos = costos_totales.get(nombre, 0)
        gastos = gastos_totales.get(nombre, 0)
        abonos = abonos_totales.get(nombre, 0)
        saldo_final = inicial + ingresos - costos - gastos + abonos

        finanzas_data.append([nombre, inicial, ingresos, costos, gastos, abonos, saldo_final])

    df_finanzas = pd.DataFrame(finanzas_data, columns=["Cuenta", "Inicial", "Ingresos", "Costos", "Gastos", "Abonos", "Saldo Final"])

    ### 🔹 3️⃣ OBTENER TIEMPO DE USO DE MESAS ###
    cursor.execute(f"""
        SELECT mesa, SUM(tiempo) 
        FROM tiempos 
        WHERE {where_clause}
        GROUP BY mesa
    """)
    tiempos_data = cursor.fetchall()
    df_tiempos = pd.DataFrame(tiempos_data, columns=["Mesa", "Tiempo Total"])
    df_tiempos.loc["TOTAL"] = df_tiempos.sum(numeric_only=True)

    ### 🔹 GUARDAR INFORME EN EXCEL ###
    file_path = "/tmp/informe.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df_inventario.to_excel(writer, sheet_name="Inventario", index=False)
        df_finanzas.to_excel(writer, sheet_name="Finanzas", index=False)
        df_tiempos.to_excel(writer, sheet_name="Tiempos de Uso", index=False)

        # Agregar hoja con resumen del filtro usado
        pd.DataFrame([[filtro_usado]], columns=["Filtro aplicado"]).to_excel(writer, sheet_name="Resumen", index=False)

    cursor.close()
    conn.close()

    return send_file(file_path, as_attachment=True, download_name="informe.xlsx")

if __name__ == '__main__':
    app.run(debug=True)
