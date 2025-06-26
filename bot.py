from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from pytz import timezone
import re
import random
from collections import defaultdict
from word2number import w2n

app = Flask(__name__)
ZONE = timezone("America/Santiago")

# Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_file("credenciales.json", scopes=SCOPES)
client = gspread.authorize(credentials)
sheet = client.open("Finanzas WhatsApp Bot").worksheet("Datos")

metodos_pago = ["efectivo", "debito", "débito", "transferencia", "credito", "crédito"]

categoria_iconos = {
    "Comida": "🍽️",
    "Transporte": "🚌",
    "Uber": "🚗",
    "Sueldo": "💼",
    "Almuerzo": "🥪",
    "Delivery": "📦",
    "Educación": "🎓",
    "Salud": "💊",
    "General": "🧾",
    "Efectivo": "💵",
    "Transferencia": "💳"
}

def normalizar_monto(texto):
    texto = texto.lower()

    # Convertir expresiones tipo "3 mil", "4k"
    texto = re.sub(r'(\d+(?:[.,]?\d+)?)[ ]?(mil|lucas)', lambda m: str(int(float(m.group(1)) * 1000)), texto)
    texto = re.sub(r'(\d+(?:[.,]?\d+)?)k', lambda m: str(int(float(m.group(1)) * 1000)), texto)

    # Convertir palabras numéricas como "dos mil" -> "2000"
    try:
        palabras = texto.split()
        for i in range(len(palabras)):
            subfrase = " ".join(palabras[i:i+4])
            try:
                valor = w2n.word_to_num(subfrase)
                texto = texto.replace(subfrase, str(valor))
                break
            except:
                continue
    except:
        pass

    return texto

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

    fecha = ayer if "ayer" in texto else hoy

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

def detectar_consulta(texto):
    texto = texto.lower()

    if re.search(r"\b(gast(e|é|ado)?|gastos?)\b", texto):
        tipo = "Gasto"
    elif re.search(r"\b(ingres(o|é|ado)?|cobré|me pagaron|pagaron)\b", texto):
        tipo = "Ingreso"
    else:
        return None

    hoy = datetime.now(ZONE).date()
    if "esta semana" in texto:
        inicio = hoy - timedelta(days=hoy.weekday())
        fin = hoy
    elif "este mes" in texto:
        inicio = hoy.replace(day=1)
        fin = hoy
    elif "ayer" in texto:
        inicio = hoy - timedelta(days=1)
        fin = inicio
    elif "hoy" in texto:
        inicio = hoy
        fin = hoy
    else:
        inicio = hoy
        fin = hoy

    categoria_match = re.search(r"en (\w+)", texto)
    categoria = categoria_match.group(1).capitalize() if categoria_match else None

    return {
        "Tipo": tipo,
        "FechaInicio": inicio.strftime("%Y-%m-%d"),
        "FechaFin": fin.strftime("%Y-%m-%d"),
        "Categoría": categoria
    }

def respuesta_humana(tipo, categoria):
    categoria = categoria.capitalize()
    icono = categoria_iconos.get(categoria, "🧾")
    if tipo == "Gasto":
        opciones = [
            f"{icono} ¡Anotado tu gasto en {categoria}! A seguir controlando 💸",
            f"{icono} Registro guardado. Otro gasto más en {categoria} 😅",
            f"{icono} Gasto en {categoria} añadido. ¡Vamos bien! ✅"
        ]
    else:
        opciones = [
            f"{icono} Ingreso en {categoria} registrado. ¡Vamos creciendo! 💰",
            f"{icono} ¡Qué bien! Anoté tu ingreso en {categoria} ✅",
            f"{icono} Ingreso guardado. ¡Sigue así! 📈"
        ]
    return random.choice(opciones)

def generar_resumen_mes():
    hoy = datetime.now(ZONE).date()
    inicio_mes = hoy.replace(day=1).strftime("%Y-%m-%d")
    fin_mes = hoy.strftime("%Y-%m-%d")
    registros = sheet.get_all_records()

    resumen = defaultdict(float)
    for row in registros:
        fecha = row.get("Fecha", "")
        tipo = row.get("Tipo", "")
        categoria = row.get("Categoría", "General")
        monto = row.get("Monto", 0)

        if inicio_mes <= fecha <= fin_mes:
            key = f"{tipo} - {categoria}"
            try:
                resumen[key] += float(monto)
            except ValueError:
                continue

    if not resumen:
        return "📉 Aún no hay movimientos registrados este mes."

    mensaje = "📊 *Resumen del mes:*\n"
    for k, v in resumen.items():
        tipo, cat = k.split(" - ")
        icono = categoria_iconos.get(cat, "🧾")
        mensaje += f"{icono} {tipo} en {cat}: ${int(v):,}\n".replace(",", ".")

    return mensaje.strip()

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    resp = MessagingResponse()
    msg = resp.message()

    limpio = incoming_msg.lower().strip("¿?.,! ")

    if any(p in limpio for p in ["resumen del mes", "mostrar resumen", "resumen"]):
        resumen = generar_resumen_mes()
        msg.body(resumen)
        return str(resp)

    # Primero intentamos registrar gasto o ingreso
    resultado = parse_frase_natural(limpio)
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

    # Luego, consulta
    consulta = detectar_consulta(limpio)
    if consulta:
        registros = sheet.get_all_records()
        total = 0
        for row in registros:
            fecha = row.get("Fecha", "")
            tipo = row.get("Tipo", "")
            categoria = row.get("Categoría", "").lower()

            if (
                tipo == consulta["Tipo"]
                and consulta["FechaInicio"] <= fecha <= consulta["FechaFin"]
                and (consulta["Categoría"] is None or categoria == consulta["Categoría"].lower())
            ):
                try:
                    total += float(row.get("Monto", 0))
                except ValueError:
                    continue

        msg.body(f"📊 Total de {consulta['Tipo'].lower()}s"
                 f"{' en ' + consulta['Categoría'] if consulta['Categoría'] else ''}"
                 f" entre {consulta['FechaInicio']} y {consulta['FechaFin']}: ${int(total):,}".replace(",", "."))
        return str(resp)

    # Formato manual CSV
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

    msg.body("🤖 No entendí tu mensaje. Puedes decir:\n"
             "- *Gasté 2500 en comida con débito*\n"
             "- *Hoy me pagaron 50000*\n"
             "- *¿Cuánto gasté esta semana?*\n"
             "- *Resumen del mes*")
    return str(resp)

if __name__ == "__main__":
    app.run()
