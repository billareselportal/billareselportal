import psycopg2
from datetime import datetime, timedelta

# Configuración de conexión a PostgreSQL
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

import psycopg2
from datetime import datetime, timedelta

# Configuración de la base de datos PostgreSQL en Render
DATABASE_URL = "postgresql://billares_el_portal_turistico_user:QEX58wGwvEukhK7FaYHfhIalGdrcdxJh@dpg-cup80l2j1k6c739gors0-a.oregon-postgres.render.com/billares_el_portal_turistico"

def obtener_inventario():
    print("🔄 Iniciando prueba de inventario...")

    try:
        # Conectar a PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✅ Conectado a PostgreSQL en Render")

        # 1️⃣ Obtener el horario dinámico
        cursor.execute("SELECT hora_inicial, hora_final FROM horarios ORDER BY id DESC LIMIT 1")
        horario_result = cursor.fetchone()
        
        if horario_result:
            hora_inicial, hora_final = horario_result
        else:
            hora_inicial, hora_final = "12:00", "12:00"  # Valores por defecto
        
        print(f"📌 Horario dinámico: {hora_inicial} - {hora_final}")

        # 2️⃣ Calcular el rango de fechas
        ahora = datetime.now()
        hora_actual = ahora.time()
        
        hora_inicial_time = datetime.strptime(hora_inicial, "%H:%M").time()
        hora_final_time = datetime.strptime(hora_final, "%H:%M").time()

        # Determinar la fecha de inicio
        if hora_actual < hora_inicial_time:
            fecha_inicio = (ahora - timedelta(days=1)).date()
        else:
            fecha_inicio = ahora.date()
        
        # ✅ Si la hora final es menor o igual a la hora inicial, el rango es hasta el día siguiente
        if hora_final_time <= hora_inicial_time:
            fecha_fin = fecha_inicio + timedelta(days=1)
        else:
            fecha_fin = fecha_inicio

        # Crear los límites de la consulta
        limite_inferior = datetime.combine(fecha_inicio, hora_inicial_time)
        limite_superior = datetime.combine(fecha_fin, hora_final_time)

        print(f"📌 Rango de consulta: {limite_inferior} → {limite_superior}")

        # 3️⃣ Obtener todos los productos con su inventario inicial desde la tabla productos
        print("🔍 Consultando valores de 'inicial' desde la tabla productos...")
        cursor.execute("SELECT producto, COALESCE(inicial, 0) FROM productos")
        productos_rows = cursor.fetchall()

        # Diccionario de inventario base desde la tabla productos
        inventario = {row[0]: {"producto": row[0], "inicial": float(row[1]), "entradas": 0, "salidas": 0, "final": float(row[1])} for row in productos_rows}

        print(f"📋 Productos obtenidos de la tabla productos: {len(inventario)} productos")

        # 4️⃣ Consultar inventario inicial (antes del límite inferior) en eventos_inventario
        print("🔍 Consultando inventario inicial desde eventos_inventario...")
        cursor.execute(
            """
            SELECT producto, COALESCE(SUM(entradas - salidas), 0)
            FROM eventos_inventario
            WHERE fecha::timestamp < %s
            GROUP BY producto;
            """,
            (limite_inferior,)
        )
        iniciales_rows = cursor.fetchall()

        # Sumar los valores obtenidos a los productos existentes en el diccionario
        for producto, cantidad in iniciales_rows:
            if producto in inventario:
                inventario[producto]["inicial"] += cantidad
                inventario[producto]["final"] += cantidad
            else:
                inventario[producto] = {"producto": producto, "inicial": cantidad, "entradas": 0, "salidas": 0, "final": cantidad}

        print(f"✅ Inventario inicial actualizado con eventos_inventario")

        # 5️⃣ Consultar entradas y salidas en el período
        print("🔍 Consultando movimientos del período...")
        cursor.execute(
            """
            SELECT producto, 
                   COALESCE(SUM(entradas), 0) AS entradas, 
                   COALESCE(SUM(salidas), 0) AS salidas
            FROM eventos_inventario
            WHERE fecha::timestamp >= %s AND fecha::timestamp <= %s
            GROUP BY producto;
            """,
            (limite_inferior, limite_superior)
        )
        periodo_rows = cursor.fetchall()

        # Aplicar los cambios al inventario final
        for producto, entradas, salidas in periodo_rows:
            if producto in inventario:
                inventario[producto]["entradas"] += entradas
                inventario[producto]["salidas"] += salidas
                inventario[producto]["final"] += entradas - salidas
            else:
                inventario[producto] = {"producto": producto, "inicial": 0, "entradas": entradas, "salidas": salidas, "final": entradas - salidas}

        print("📋 Inventario final calculado:")
        for item in inventario.values():
            print(item)

        # Cerrar conexión
        cursor.close()
        conn.close()
        print("✅ Conexión cerrada correctamente")

        return list(inventario.values())  # Devolver en formato de lista de diccionarios

    except Exception as e:
        print(f"❌ Error en la consulta: {e}")



# Ejecutar la prueba
obtener_inventario()
