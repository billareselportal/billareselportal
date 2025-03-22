import psycopg2
import pandas as pd

# Datos de conexión a PostgreSQL
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

# Conectar a PostgreSQL
try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Obtener nombres de columnas en la tabla flujo_dinero
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'productos';
    """)
    columnas = cursor.fetchall()
    columnas = [col[0] for col in columnas]

    # Obtener contenido de la tabla flujo_dinero
    cursor.execute("SELECT * FROM productos LIMIT 10;")
    datos = cursor.fetchall()

    # Crear un DataFrame para visualizar mejor
    df = pd.DataFrame(datos, columns=columnas)
    
    # Mostrar el contenido en la consola
    print("Contenido de la tabla flujo_dinero:")
    print(df)

    # Cerrar conexión
    cursor.close()
    conn.close()

except Exception as e:
    print(f"Error al conectar o consultar la base de datos: {e}")
