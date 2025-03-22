import psycopg2
import pandas as pd

# Datos de conexión
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public';
    """)
    tablas = cursor.fetchall()
    df = pd.DataFrame(tablas, columns=["Nombre de Tabla"])
    print(df.to_string(index=False))

    cursor.close()
    conn.close()

except Exception as e:
    print("❌ Error:", e)
