import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import locale
import time
import pytz # Nueva librería para manejar zonas horarias
from keep_alive import keep_alive # Para mantenerlo activo en Replit

# --- CONFIGURACIÓN ---
TOKEN = os.environ['DISCORD_TOKEN'] 
CHANNEL_ID = 1400472034374324335   # Tu ID de canal
URL = "https://altertime.es/feed?rss" 

# --- NUEVO: CONFIGURACIÓN DE HORARIO ---
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
HORA_INICIO = 9  # 9 AM
HORA_FIN = 3     # 3 AM

# --- VARIABLES GLOBALES ---
urls_noticias_enviadas = set()

# --- INICIALIZACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Intentamos configurar el idioma a español para los nombres de los meses.
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    print("Locale 'es_ES.UTF-8' no disponible. Se usarán los nombres de mes por defecto.")


def extraer_noticias():
    """
    Esta función se conecta al feed RSS de la web, lo analiza
    y extrae una lista de las noticias más recientes.
    """
    try:
        url_cache_bust = f"{URL}&_={int(time.time())}"
        response = requests.get(url_cache_bust, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'xml')

        lista_de_noticias = []

        contenedores = soup.find_all('item', limit=3)

        for item in contenedores:
            titulo_tag = item.find('title')
            enlace_tag = item.find('link')

            if not titulo_tag or not enlace_tag:
                continue

            titulo = titulo_tag.text
            enlace = enlace_tag.text

            descripcion_html_tag = item.find('description')
            descripcion_html = descripcion_html_tag.text if descripcion_html_tag else ""
            descripcion_soup = BeautifulSoup(descripcion_html, 'html.parser')
            descripcion = descripcion_soup.get_text(strip=True)

            # --- MEJORA EN LA EXTRACCIÓN DE IMAGEN (3 MÉTODOS) ---
            imagen_url = None
            # Método 1: Buscar imagen dentro de la descripción
            imagen_tag_desc = descripcion_soup.find('img')
            if imagen_tag_desc and imagen_tag_desc.has_attr('src'):
                imagen_url = imagen_tag_desc['src']

            # Método 2: Buscar en la etiqueta <media:content>
            if not imagen_url:
                media_content_tag = item.find('media:content')
                if media_content_tag and media_content_tag.has_attr('url'):
                    imagen_url = media_content_tag['url']

            # Método 3: Buscar en la etiqueta <enclosure> (muy común en RSS)
            if not imagen_url:
                enclosure_tag = item.find('enclosure')
                if enclosure_tag and enclosure_tag.has_attr('url') and 'image' in enclosure_tag.get('type', ''):
                    imagen_url = enclosure_tag['url']


            fecha_str = "Fecha no disponible"
            pub_date_tag = item.find('pubDate')
            if pub_date_tag:
                try:
                    dt_objeto = datetime.strptime(pub_date_tag.text, '%a, %d %b %Y %H:%M:%S GMT')
                    fecha_str = dt_objeto.strftime('%d de %B de %Y')
                except ValueError:
                    try:
                        dt_objeto = datetime.strptime(pub_date_tag.text, '%a, %d %b %Y %H:%M:%S %z')
                        fecha_str = dt_objeto.strftime('%d de %B de %Y')
                    except ValueError:
                        print(f"No se pudo procesar la fecha: {pub_date_tag.text}")


            lista_de_noticias.append({
                'titulo': titulo,
                'enlace': enlace,
                'descripcion': descripcion,
                'imagen_url': imagen_url,
                'fecha': fecha_str
            })

        return lista_de_noticias

    except requests.exceptions.RequestException as e:
        print(f"Error al acceder a la URL: {e}")
        return []
    except Exception as e:
        print(f"Error al extraer noticias: {e}")
        return []


@tasks.loop(hours=1)
async def revisar_pagina_periodicamente():
    """Tarea en bucle que revisa la página y envía notificaciones si hay algo nuevo."""
    hora_actual = datetime.now(ZONA_HORARIA).hour
    if not (hora_actual >= HORA_INICIO or hora_actual < HORA_FIN):
        print(f"Hora actual ({hora_actual}:00 en Madrid) fuera del rango activo ({HORA_INICIO}:00 - {HORA_FIN}:00). Saltando revisión.")
        return

    global urls_noticias_enviadas
    print("Revisando el feed en busca de nuevas noticias (dentro del horario activo)...")

    noticias_actuales = extraer_noticias()
    if not noticias_actuales:
        return

    if not urls_noticias_enviadas:
        urls_noticias_enviadas.update(n['enlace'] for n in noticias_actuales)
        print(f"Primera revisión completada. Se han guardado {len(urls_noticias_enviadas)} noticias iniciales.")
        return

    canal = bot.get_channel(CHANNEL_ID)
    if not canal:
        print(f"Error: No se pudo encontrar el canal con ID {CHANNEL_ID}")
        return

    for noticia in reversed(noticias_actuales):
        if noticia['enlace'] not in urls_noticias_enviadas:
            print(f"¡Noticia nueva encontrada!: {noticia['titulo']}")

            embed = discord.Embed(
                title=noticia['titulo'],
                url=noticia['enlace'],
                description=noticia['descripcion'],
                color=discord.Color.dark_blue()
            )
            if noticia['imagen_url']:
                embed.set_image(url=noticia['imagen_url'])

            embed.set_footer(text=f"Publicado el {noticia['fecha']} • AlterTime")

            await canal.send(embed=embed)

            urls_noticias_enviadas.add(noticia['enlace'])


@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user.name}")
    print("------------------------------------")
    if not revisar_pagina_periodicamente.is_running():
        revisar_pagina_periodicamente.start()


@bot.command()
async def probar(ctx):
    """Extrae y muestra las 3 noticias más recientes de la página."""
    await ctx.send("Analizando el feed y extrayendo las últimas 3 noticias...")

    noticias = extraer_noticias()

    if not noticias:
        await ctx.send("No se pudieron extraer noticias. Revisa la consola de Replit en busca de errores.")
        return

    await ctx.send(f"Se han encontrado {len(noticias)} noticias. Mostrando las más recientes:")
    for noticia in noticias[:3]:
        embed = discord.Embed(
            title=noticia['titulo'],
            url=noticia['enlace'],
            description=noticia['descripcion'],
            color=discord.Color.green()
        )
        if noticia['imagen_url']:
            embed.set_image(url=noticia['imagen_url'])

        embed.set_footer(text=f"Publicado el {noticia['fecha']}")

        await ctx.send(embed=embed)


# --- EJECUCIÓN DEL BOT ---
keep_alive() 
bot.run(TOKEN)
