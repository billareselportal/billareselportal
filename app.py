import sqlite3
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='templates')  # Asegurar que use la carpeta de plantillas

# ✅ Ruta absoluta de la base de datos
DB_PATH = r"C:\Users\Usuario\Desktop\SISTEMA PORTAL\portal.db"

def connect_db():
    print(f"📌 Conectando a la base de datos: {DB_PATH}")  # Imprimir la ruta
    conn = sqlite3.connect(DB_PATH)
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/consulta', methods=['GET'])
def consulta():
    codigo = request.args.get('codigo')
    if not codigo:
        return jsonify({'success': False, 'message': 'Código no proporcionado'})

    conn = connect_db()
    cursor = conn.cursor()

    # 🔍 Imprimir todas las tablas de la base de datos
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"🔍 Tablas en la base de datos: {tables}")

    # 🔎 Verificar si la tabla 'mesas' existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mesas';")
    if not cursor.fetchone():
        return jsonify({'success': False, 'message': '❌ La tabla mesas no existe en la base de datos.'})

    # 🔍 Imprimir los códigos de la tabla 'mesas'
    cursor.execute("SELECT codigo FROM mesas;")
    codigos = cursor.fetchall()
    print(f"📌 Códigos en la tabla 'mesas': {codigos}")

    # 🔎 Consultar la tabla 'mesas' con los nombres correctos de columnas
    cursor.execute("SELECT factura_no, nombre FROM mesas WHERE codigo = ?", (codigo,))
    result = cursor.fetchone()

    print(f"🔍 Consulta realizada para código {codigo}: {result}")

    conn.close()

    if result:
        factura, cliente = result
        return jsonify({'success': True, 'factura': factura, 'cliente': cliente})
    else:
        return jsonify({'success': False, 'message': 'No encontrado'})

@app.route('/resultado', methods=['POST'])
def resultado():
    codigo = request.form.get('codigo')  # Código ingresado en el formulario
    if not codigo:
        return render_template('resultado.html', mensaje="Debe ingresar un código.")

    conn = connect_db()
    cursor = conn.cursor()

    # 🔎 Paso 1: Buscar el `factura_no` en la tabla `mesas` usando el `codigo`
    cursor.execute("SELECT factura_no FROM mesas WHERE codigo = ?", (codigo,))
    factura_result = cursor.fetchone()

    if not factura_result:
        return render_template('resultado.html', mensaje="No encontrado en la base de datos. Verifique el código ingresado.")

    factura_no = factura_result[0]  # Extraer el número de factura
    print(f"📌 Factura encontrada para código {codigo}: {factura_no}")

    # 🔎 Paso 2: Buscar en `ventas` usando `factura_no`
    cursor.execute("""
        SELECT factura_no, nombre, estado, total, saldo, caja, nequi, bancolombia, datafono, julian, fiado, fecha, concepto
        FROM ventas
        WHERE factura_no = ?""", (factura_no,))
    venta_result = cursor.fetchone()

    if not venta_result:
        return render_template('resultado.html', mensaje="No hay información de ventas para esta factura.")

    factura, nombre, estado, total, saldo, caja, nequi, bancolombia, datafono, julian, fiado, fecha, concepto = venta_result

    # 🔎 Paso 3: Buscar en `eventos_inventarios` los productos asociados a la factura
    cursor.execute("""
        SELECT producto, salidas, costo, metodo
        FROM eventos_inventario
        WHERE factura_no = ?""", (factura_no,))
    eventos = cursor.fetchall()

    conn.close()

    return render_template('resultado.html', 
                           datos_venta=[factura, nombre, estado, total, saldo, caja, nequi, bancolombia, datafono, julian, fiado, fecha, concepto], 
                           detalle_eventos=eventos)


if __name__ == '__main__':
    app.run(debug=True)
