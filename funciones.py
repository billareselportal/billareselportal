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
