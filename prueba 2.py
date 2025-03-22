import psycopg2
import pandas as pd

# Conexión a PostgreSQL
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # 🔹 Obtener los nombres de las columnas en el orden correcto
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'flujo_dinero' 
        ORDER BY ordinal_position;  -- 🔥 Esto asegura el orden correcto
    """)
    columnas = [col[0] for col in cursor.fetchall()]
    
    print("✅ Orden de columnas obtenidas:", columnas)  # Debugging

    # 🔹 Obtener los datos asegurando el mismo orden
    cursor.execute(f"SELECT {', '.join(columnas)} FROM flujo_dinero LIMIT 10;")
    datos = cursor.fetchall()

    # 🔹 Crear el DataFrame con el orden correcto
    df = pd.DataFrame(datos, columns=columnas)

    # 🔹 Mostrar el DataFrame corregido
    print("✅ Datos alineados correctamente:")
    print(df)

    # Cerrar conexión
    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error al conectar o consultar la base de datos: {e}")
