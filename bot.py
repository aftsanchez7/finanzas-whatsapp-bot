from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from pytz import timezone
import re
import random

app = Flask(__name__)
ZONE = timezone("America/Santiago")

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Finanzas WhatsApp Bot").worksheet("Datos")

metodos_pago = ["efectivo", "debito", "débito", "transferencia", "credito", "crédito"]

def parse_frase_natural(texto):
    texto = texto.lower()
    hoy = datetime.now(ZONE).strftime("%Y-%m-%d")
    ayer = (datetime.now(ZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if "gast" in texto:
        tipo = "Gasto"
    elif "ingres" in texto or "pagaron" in texto or "cobré" in texto:
        tipo = "Ingreso"
    else:
        return None

    monto_match = re.search(r"(\d{1,3}(?:[.,]?\d{3})*(?:[.,]?\d{2})?)", texto)
    if not monto_match:
        return None
    monto = monto_match.group(1).replace(".", "").replace(",", "")

    metodo = next((m for m in metodos_pago if m in texto), "No especificado")

    if "ayer" in texto:
        fecha = ayer
    else:
        fecha = hoy

    categoria_match = re.search(r"en\s+([\w\s]+?)(?:\s+con|\s*$)", texto)
    categoria = categoria_match.group(1).strip().capitalize() if categoria_match else "General"
    descripcion = f"{categoria}"

    return {
        "Fecha": fecha,
        "Tipo": tipo,
        "Monto": monto,
        "Categoría": categoria,
        "Método": metodo.capitalize(),
        "Descripción": descripcion
    }

def respuesta_humana(tipo, categoria):
    if tipo == "Gasto":
        opciones = [
            f"💸 Gasto anotado en {categoria}. ¡A cuidar esa billetera!",
            f"✅ Listo, registré tu gasto en {categoria}.",
            f"📉 Otro gasto en {categoria}. ¡Vamos controlando!",
        ]
    else:
        opciones = [
            f"🤑 ¡Ingreso en {categoria} anotado! Qué rico cobrar.",
            f"✅ Registro guardado. ¡Vamos sumando ingresos!",
            f"💰 Ingreso recibido y anotado como {categoria}.",
        ]
    return random.choice(opciones)

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    resp = MessagingResponse()
    msg = resp.message()

    # Intentar primero formato separado por comas
    datos = [x.strip() for x in incoming_msg.split(',')]

    if len(datos) == 5 or len(datos) == 6:
        if len(datos) == 5:
            tipo, monto, categoria, metodo, descripcion = datos
            fecha = datetime.now(ZONE).strftime("%Y-%m-%d")
        else:
            tipo, monto, categoria, metodo, descripcion, fecha_str = datos
            try:
                if fecha_str.lower() == "hoy":
                    fecha = datetime.now(ZONE).strftime("%Y-%m-%d")
                elif fecha_str.lower() == "ayer":
                    fecha = (datetime.now(ZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    fecha = datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%Y-%m-%d")
            except:
                msg.body("❌ Fecha inválida. Usa AAAA-MM-DD o 'hoy'/'ayer'.")
                return str(resp)

        try:
            monto_num = float(monto)
        except:
            msg.body("❌ Monto inválido, debe ser un número.")
            return str(resp)

        fila = [fecha, tipo, monto_num, categoria, metodo, descripcion, from_number]
        try:
            sheet.append_row(fila)
            msg.body(respuesta_humana(tipo, categoria))
        except:
            msg.body("❌ Error al guardar el registro.")
        return str(resp)

    # Si no es formato con comas, intentar parser de frase natural
    resultado = parse_frase_natural(incoming_msg)
    if resultado:
        try:
            fila = [
                resultado["Fecha"],
                resultado["Tipo"],
                float(resultado["Monto"]),
                resultado["Categoría"],
                resultado["Método"],
                resultado["Descripción"],
                from_number
            ]
            sheet.append_row(fila)
            msg.body(respuesta_humana(resultado["Tipo"], resultado["Categoría"]))
        except:
            msg.body("❌ Hubo un problema al guardar tu registro.")
        return str(resp)

    # Si no entendió ni como comando ni como frase
    msg.body("⚠️ No entendí tu mensaje. Puedes decir algo como:\n- Gasté 2500 en comida\n- Hoy me pagaron 50000\n- O usa: Gasto, 2500, Comida, Efectivo, Almuerzo")
    return str(resp)

if __name__ == "__main__":
    app.run()
