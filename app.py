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
    import pandas as pd
    from flask import send_file, request, jsonify
    from datetime import datetime
    import os

    id_inicio = request.args.get('id_inicio')

    conn = connect_db()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    cursor = conn.cursor()

    # ⬆️ Verificamos tipo de columna 'fecha' en cada tabla y la convertimos si es texto
    tablas_con_fecha = ["eventos_inventario", "ventas", "costos", "gastos", "abonos"]
    for tabla in tablas_con_fecha:
        try:
            cursor.execute(f"""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = '{tabla}' AND column_name = 'fecha';
            """)
            tipo_fecha = cursor.fetchone()
            if tipo_fecha and tipo_fecha[0] == 'text':
                cursor.execute(f"""
                    ALTER TABLE {tabla} 
                    ALTER COLUMN fecha TYPE TIMESTAMP 
                    USING fecha::timestamp;
                """)
                conn.commit()
        except:
            conn.rollback()

    # 🔍 Buscar fecha del primer ID válido a partir del ID numérico ingresado
    def buscar_id_y_fecha(base_id):
        while int(base_id) < 9999:
            posibles_ids = [f"S{base_id}", f"S{base_id}-1", f"S{base_id}-1P1"]
            for pid in posibles_ids:
                cursor.execute("SELECT fecha FROM eventos_inventario WHERE id = %s LIMIT 1", (pid,))
                row = cursor.fetchone()
                if row:
                    return pid, row[0]
            base_id = str(int(base_id) + 1)
        return None, None

    if not id_inicio:
        return jsonify({"error": "Debe especificar id_inicio"}), 400

    id_valido, fecha_inicio = buscar_id_y_fecha(id_inicio)
    if not id_valido:
        return jsonify({"error": "No se encontró un ID válido"}), 400

    # 🔍 Funciones para obtener DataFrames
    def fetch_df(query, params=()):
        cursor.execute(query, params)
        cols = [desc[0] for desc in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=cols)

    inventario_df = fetch_df("SELECT * FROM eventos_inventario WHERE fecha >= %s", (fecha_inicio,))
    ventas_df = fetch_df("SELECT * FROM ventas WHERE fecha >= %s", (fecha_inicio,))
    gastos_df = fetch_df("SELECT * FROM gastos WHERE fecha >= %s", (fecha_inicio,))
    costos_df = fetch_df("SELECT * FROM costos WHERE fecha >= %s", (fecha_inicio,))
    abonos_df = fetch_df("SELECT * FROM abonos WHERE fecha >= %s", (fecha_inicio,))
    productos_df = fetch_df("SELECT * FROM productos")
    flujo_df = fetch_df("SELECT * FROM flujo_dinero")

    # 📊 Construcción del inventario con cálculo de valor venta
    inventario = []
    for _, row in productos_df.iterrows():
        if row['id'] > 53:
            continue
        producto = row['producto']
        precio = row['precio']
        entradas = inventario_df[inventario_df['producto'] == producto]['entradas'].sum()
        salidas = inventario_df[inventario_df['producto'] == producto]['salidas'].sum()
        inicial = row['inicial']
        final = inicial + entradas - salidas
        valor_total = salidas * precio
        inventario.append({
            "Producto": producto,
            "Precio": precio,
            "Inicial": inicial,
            "Entradas": entradas,
            "Salidas": salidas,
            "Final": final,
            "Total Venta": valor_total
        })

    df_inv = pd.DataFrame(inventario)

    # 💸 Totales y resumen financiero
    ventas_total = ventas_df['total'].sum()
    ventas_edgar = ventas_df[ventas_df['nombre'].str.lower() == 'edgar']['total'].sum()
    ventas_julian = ventas_total - ventas_edgar

    gastos_edgar = gastos_df['edgar'].sum()
    gastos_julian = gastos_df['total'].sum() - gastos_edgar

    costos_edgar = costos_df['edgar'].sum()
    costos_julian = costos_df['total'].sum() - costos_edgar

    abonos_edgar = abonos_df['edgar'].sum() if 'edgar' in abonos_df.columns else 0
    abonos_julian = abonos_df['julian'].sum() if 'julian' in abonos_df.columns else 0

    ab_edgar_pos = abonos_edgar if abonos_edgar > 0 else 0
    ab_edgar_neg = abonos_edgar if abonos_edgar < 0 else 0

    inicial_julian = flujo_df[flujo_df['nombre'].str.lower() == 'julian']['inicial'].sum()
    inicial_edgar = flujo_df[flujo_df['nombre'].str.lower() == 'edgar']['inicial'].sum()

    saldo_julian = inicial_julian + ventas_julian - gastos_julian - costos_julian - ab_edgar_pos + abs(ab_edgar_neg)
    saldo_edgar = inicial_edgar + ventas_edgar - gastos_edgar - costos_edgar + ab_edgar_pos - abs(ab_edgar_neg)

    # 📊 DataFrame resumen (para hoja 2)
    resumen = pd.DataFrame([
        ["VENTA", ventas_julian],
        ["COSTOS", costos_julian],
        ["GASTOS", gastos_julian],
        ["UTILIDAD", ventas_julian - costos_julian - gastos_julian]
    ], columns=["CONCEPTO", "VALOR"])

    # Agregamos debajo el consolidado de Julián y Edgar
    consolidado = pd.DataFrame([
        ["Julian", inicial_julian, ventas_julian, costos_julian, gastos_julian, abonos_julian, saldo_julian],
        ["Edgar", inicial_edgar, ventas_edgar, costos_edgar, gastos_edgar, abonos_edgar, saldo_edgar]
    ], columns=["Nombre", "Inicial", "Ventas", "Costos", "Gastos", "Abonos", "Saldo Final"])

    # 📃 Guardar el archivo Excel
    file_path = "/tmp/informe.xlsx"
    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        df_inv.to_excel(writer, sheet_name="Inventario", index=False)
        resumen.to_excel(writer, sheet_name="Resumen", startrow=1, index=False)
        consolidado.to_excel(writer, sheet_name="Resumen", startrow=7, index=False)

    cursor.close()
    conn.close()

    return send_file(file_path, as_attachment=True, download_name="informe.xlsx")


if __name__ == '__main__':
    app.run(debug=True)
