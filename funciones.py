import sqlite3

# ✅ Ruta absoluta de la base de datos
DB_PATH = r"C:\Users\Usuario\OneDrive\SISTEMA PORTAL\portal.db"

def conectar_db():
    print(f"📌 Conectando a la base de datos: {DB_PATH}")  # Imprimir la ruta
    conn = sqlite3.connect(DB_PATH)
    return conn

def buscar_por_codigo(codigo):
    conn = conectar_db()
    cursor = conn.cursor()

    # 🔍 Imprimir todas las tablas de la base de datos
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"🔍 Tablas en la base de datos: {tables}")

    # 🔎 Verificar si la tabla 'mesas' existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mesas';")
    if not cursor.fetchone():
        print("❌ Error: La tabla 'mesas' no existe en la base de datos.")
        return None

    # 🔍 Imprimir los códigos de la tabla 'mesas'
    cursor.execute("SELECT codigo FROM mesas;")
    codigos = cursor.fetchall()
    print(f"📌 Códigos en la tabla 'mesas': {codigos}")

    # 🔎 Consultar la tabla 'mesas'
    cursor.execute("SELECT factura_no, nombre FROM mesas WHERE codigo = ?", (codigo,))
    resultado = cursor.fetchone()

    print(f"🔍 Consulta en funciones.py para código {codigo}: {resultado}")

    conn.close()
    
    if resultado:
        return {"factura": resultado[0], "cliente": resultado[1]}
    return None
