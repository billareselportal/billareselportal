import psycopg2
from flask import Flask, request, jsonify, render_template
from funciones import buscar_por_codigo
from funciones import obtener_lista_precios
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


if __name__ == '__main__':
    app.run(debug=True)
