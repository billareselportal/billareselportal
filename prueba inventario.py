from datetime import datetime
import pytz

# Define la zona horaria local, por ejemplo, para Colombia
zona_horaria_local = pytz.timezone('America/Bogota')

# Obtén la hora actual en la zona horaria local
hora_local = datetime.now(zona_horaria_local)
print("Hora local:", hora_local.strftime("%Y-%m-%d %H:%M:%S %Z%z"))
