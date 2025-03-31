import psycopg2

def listar_tablas_postgres():
    # URL de conexión a PostgreSQL en Render
    postgres_url = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

    print("🟢 Iniciando conexión a PostgreSQL...")

    try:
        # Conectar a PostgreSQL
        conn = psycopg2.connect(postgres_url)
        print("✅ Conexión exitosa a PostgreSQL.")
        cursor = conn.cursor()

        # Obtener todas las tablas del esquema 'public'
        print("🟢 Consultando tablas en el esquema 'public'...")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tablas = cursor.fetchall()

        if not tablas:
            print("🚫 No hay tablas en el esquema 'public'.")
        else:
            print("📋 Tablas en el esquema 'public':")
            for tabla in tablas:
                print(f"- {tabla[0]}")

    except Exception as e:
        print(f"❌ Error al conectar o consultar PostgreSQL: {e}")

    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()
            print("🔒 Conexión cerrada.")

listar_tablas_postgres()
