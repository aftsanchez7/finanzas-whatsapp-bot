from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from pytz import timezone

app = Flask(__name__)

# Configuración zona horaria
ZONE = timezone('America/Santiago')

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Finanzas WhatsApp Bot").worksheet("Datos")

def parse_fecha(fecha_str):
    fecha_str = fecha_str.strip().lower()
    hoy = datetime.now(ZONE).date()
    if fecha_str == "hoy":
        return hoy.strftime("%Y-%m-%d")
    elif fecha_str == "ayer":
        ayer = hoy - timedelta(days=1)
        return ayer.strftime("%Y-%m-%d")
    else:
        try:
            # Intentar parsear formato YYYY-MM-DD
            return datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        except:
            return None

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg.lower() == "/resumen":
        try:
            return enviar_resumen(msg)
        except Exception as e:
            msg.body("❌ Error al generar resumen.")
            return str(resp)

    datos = [x.strip() for x in incoming_msg.split(',')]

    if len(datos) == 5:
        tipo, monto, categoria, metodo, descripcion = datos
        fecha = datetime.now(ZONE).strftime("%Y-%m-%d")
    elif len(datos) == 6:
        tipo, monto, categoria, metodo, descripcion, fecha_str = datos
        fecha = parse_fecha(fecha_str)
        if not fecha:
            msg.body("❌ Fecha inválida. Usa AAAA-MM-DD o 'hoy'/'ayer'.")
            return str(resp)
    else:
        msg.body("⚠️ Formato incorrecto. Usa:\nTipo, Monto, Categoría, Método, Descripción [, Fecha (opcional)]\nO envía /resumen para ver totales.")
        return str(resp)

    # Validar monto numérico
    try:
        monto_num = float(monto)
    except:
        msg.body("❌ Monto inválido, debe ser un número.")
        return str(resp)

    # Guardar fila
    fila = [fecha, tipo, monto_num, categoria, metodo, descripcion, from_number]
    try:
        sheet.append_row(fila)
        msg.body(f"✅ Registro guardado:\n{fecha} - {tipo} {monto_num} {categoria}")
    except Exception as e:
        msg.body("❌ Error al guardar el registro.")

    return str(resp)

def enviar_resumen(msg):
    hoy = datetime.now(ZONE)
    mes_actual = hoy.strftime("%Y-%m")
    # Obtener todos los datos (asumiendo encabezado en fila 1)
    registros = sheet.get_all_records()
    total_gastos = 0.0
    total_ingresos = 0.0

    for r in registros:
        fecha = r.get("Fecha", "")
        tipo = r.get("Tipo", "").lower()
        monto = float(r.get("Monto", 0))
        if fecha.startswith(mes_actual):
            if tipo == "gasto":
                total_gastos += monto
            elif tipo == "ingreso":
                total_ingresos += monto

    saldo = total_ingresos - total_gastos
    resumen = (
        f"📊 Resumen {mes_actual}\n"
        f"Ingresos: {total_ingresos:.2f}\n"
        f"Gastos: {total_gastos:.2f}\n"
        f"Saldo: {saldo:.2f}"
    )
    msg.body(resumen)
    return str(msg)

if __name__ == "__main__":
    app.run()
