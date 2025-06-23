from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)

# Conectar con Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
client = gspread.authorize(creds)

# Abre la hoja de cálculo
sheet = client.open("Finanzas WhatsApp Bot").worksheet("Datos")

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    resp = MessagingResponse()
    msg = resp.message()

    try:
        datos = [x.strip() for x in incoming_msg.split(',')]

        if len(datos) < 6:
            msg.body("⚠️ Formato incorrecto. Usa:\nTipo, Monto, Categoría, Método, Fecha (YYYY-MM-DD), Descripción")
            return str(resp)

        tipo, monto, categoria, metodo, fecha, descripcion = datos
        fecha = datetime.strptime(fecha, "%Y-%m-%d").strftime("%Y-%m-%d")

        fila = [fecha, tipo, monto, categoria, metodo, descripcion, from_number]
        sheet.append_row(fila)

        msg.body("✅ Registro guardado exitosamente.")
    except Exception as e:
        print("Error:", e)
        msg.body("❌ Ocurrió un error al guardar. Revisa el formato.")

    return str(resp)