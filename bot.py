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

# --- Función para normalizar montos tipo "2 mil", "10k", "lucas"
def normalizar_monto(texto):
    texto = texto.lower()
    texto = re.sub(r'(\d+(?:[.,]?\d+)?)[ ]?(mil|lucas)', lambda m: str(int(float(m.group(1)) * 1000)), texto)
    texto = re.sub(r'(\d+(?:[.,]?\d+)?)k', lambda m: str(int(float(m.group(1)) * 1000)), texto)
    return texto

# --- Parser natural
def parse_frase_natural(texto):
    texto = normalizar_monto(texto.lower())
    hoy = datetime.now(ZONE).strftime("%Y-%m-%d")
    ayer = (datetime.now(ZONE) - timedelta(days=1)).strftime("%Y-%m-%d")

    if "gast" in texto:
        tipo = "Gasto"
    elif "ingres" in texto or "pagaron" in texto or "cobré" in texto:
        tipo = "Ingreso"
    else:
        return None

    monto_match = re.search(r"(\d{3,})", texto)
    if not monto_match:
        return None
    monto = monto_match.group(1)

    metodo = next((m for m in metodos_pago if m in texto), "No especificado")

    if "ayer" in texto:
        fecha = ayer
    else:
        fecha = hoy

    categoria_match = re.search(r"en\s+([\w\s]+?)(?:\s+con|\s*$)", texto)
    categoria = categoria_match.group(1).strip().capitalize() if categoria_match else "General"
    descripcion = categoria

    return {
        "Fecha": fecha,
        "Tipo": tipo,
        "Monto": monto,
        "Categoría": categoria,
        "Método": metodo.capitalize(),
        "Descripción": descripcion
    }

# --- Consultas por lenguaje natural
def detectar_consulta(texto):
    texto = texto.lower()
    tipo = None
    categoria = None
    fecha_inicio = None
    fecha_fin = datetime.now(ZONE).date()

    if "gasté" in texto or "gasto" in texto:
        tipo = "Gasto"
    elif "ingres" in texto or "cobré" in texto or "pagaron" in texto:
        tipo = "Ingreso"
    else:
        return None

    if "esta semana" in texto:
        fecha_inicio = fecha_fin - timedelta(days=fecha_fin.weekday())
    elif "este mes" in texto:
        fecha_inicio = fecha_fin.replace(day=1)
    elif "ayer" in texto:
        fecha_inicio = fecha_fin - timedelta(days=1)
        fecha_fin = fecha_inicio
    else:
        fecha_inicio = fecha_fin

    categoria_match = re.search(r"en (\w+)", texto)
    if categoria_match:
        categoria = categoria_match.group(1).capitalize()
    else:
        categoria = None

    return {
        "Tipo": tipo,
        "FechaInicio": fecha_inicio.strftime("%Y-%m-%d"),
        "FechaFin": fecha_fin.strftime("%Y-%m-%d"),
        "Categoría": categoria
    }

# --- Respuestas más humanas
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

    # Intentar detectar una consulta
    consulta = detectar_consulta(incoming_msg)
    if consulta:
        registros = sheet.get_all_records()
        total = 0
        for row in registros:
            if (
                row["Tipo"] == consulta["Tipo"]
                and consulta["FechaInicio"] <= row["Fecha"] <= consulta["FechaFin"]
                and (consulta["Categoría"] is None or row["Categoría"].lower() == consulta["Categoría"].lower())
            ):
                total += float(row["Monto"])
        msg.body(f"📊 Total de {consulta['Tipo'].lower()}s"
                 f"{' en ' + consulta['Categoría'] if consulta['Categoría'] else ''}"
                 f" entre {consulta['FechaInicio']} y {consulta['FechaFin']}: ${int(total):,}".replace(",", "."))
        return str(resp)

    # Intentar como mensaje con comas
    datos = [x.strip() for x in incoming_msg.split(',')]
    if len(datos) in [5, 6]:
        if len(datos) == 5:
            tipo, monto, categoria, metodo, descripcion = datos
            fecha = datetime.now(ZONE).strftime("%Y-%m-%d")
        else:
            tipo, monto, categoria, metodo, descripcion, fecha = datos
        fila = [fecha, tipo, float(monto), categoria, metodo, descripcion, from_number]
        sheet.append_row(fila)
        msg.body(respuesta_humana(tipo, categoria))
        return str(resp)

    # Parser natural como última opción
    resultado = parse_frase_natural(incoming_msg)
    if resultado:
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
        return str(resp)

    msg.body("⚠️ No entendí tu mensaje. Puedes decir:\n- Gasté 2500 en pan\n- Hoy me pagaron 50000\n- ¿Cuánto gasté esta semana en comida?")
    return str(resp)

if __name__ == "__main__":
    app.run()
