import psycopg2

# ✅ URL de la base de datos PostgreSQL en Render
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

def conectar_db():
    """Establece conexión con la base de datos PostgreSQL en Render."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        return None

def buscar_por_codigo(codigo):
    """Busca un código en la tabla 'mesas' en PostgreSQL y obtiene la factura asociada."""
    conn = conectar_db()
    if not conn:
        return None  # Si no hay conexión, no hacemos la consulta

    cursor = conn.cursor()

    try:
        # 🔍 Consultar la tabla 'mesas' en PostgreSQL
        print(f"🟡 Buscando código {codigo} en la tabla 'mesas'...")
        cursor.execute("SELECT factura_no, nombre FROM mesas WHERE codigo = %s;", (codigo,))
        resultado = cursor.fetchone()

        if resultado:
            print(f"✅ Factura encontrada para código {codigo}: {resultado}")
            return {"factura": resultado[0], "cliente": resultado[1]}
        else:
            print(f"❌ No se encontró una factura para el código {codigo}")
            return None

    except Exception as e:
        print(f"❌ Error en la consulta SQL: {e}")
        return None

    finally:
        conn.close()

def obtener_lista_precios():
    """Obtiene la lista de productos y precios, asegurando el formato correcto."""
    conn = conectar_db()
    if not conn:
        print("❌ No se pudo conectar a la base de datos.")
        return None

    cursor = conn.cursor()

    try:
        # 🔍 Obtener todas las tablas para verificar la estructura
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        tablas = cursor.fetchall()

        if tablas:
            print("🔹 Tablas en la base de datos:")
            for tabla in tablas:
                print(f"- {tabla[0]}")
        else:
            print("❌ No se encontraron tablas en la base de datos.")
            return None  # No tiene sentido seguir si no hay tablas

        # 🔍 Obtener lista de productos con precios ordenados por ID ASC
        cursor.execute("SELECT producto, precio FROM productos ORDER BY id ASC;")
        productos = cursor.fetchall()

        if productos:
            return [(row[0], row[1]) for row in productos]  # Solo devolver producto y precio
        else:
            print("❌ No se encontraron productos en la base de datos.")
            return None

    except Exception as e:
        print(f"❌ Error en la consulta SQL: {e}")
        return None

    finally:
        conn.close()
