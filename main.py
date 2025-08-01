import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import locale
import time
from keep_alive import keep_alive # Para mantenerlo activo en Replit

# --- CONFIGURACIÓN ---
TOKEN = os.environ['DISCORD_TOKEN'] 
CHANNEL_ID = 1400472034374324335   # Reemplaza con el ID del canal donde se enviarán las notificaciones
URL = "https://altertime.es/feed?rss" 

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
        # Añadimos un parámetro extra a la URL para evitar la caché y obtener siempre la versión más reciente.
        url_cache_bust = f"{URL}&_={int(time.time())}"
        response = requests.get(url_cache_bust, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'xml')

        lista_de_noticias = []

        contenedores = soup.find_all('item', limit=10)

        for item in contenedores:
            titulo = item.find('title').text
            enlace = item.find('link').text

            descripcion_html = item.find('description').text
            descripcion_soup = BeautifulSoup(descripcion_html, 'html.parser')
            descripcion = descripcion_soup.get_text(strip=True)

            imagen_tag = descripcion_soup.find('img')
            imagen_url = imagen_tag['src'] if imagen_tag else None

            fecha_str = "Fecha no disponible"
            pub_date_tag = item.find('pubDate')
            if pub_date_tag:
                try:
                    # CORRECCIÓN: El formato de fecha en este feed usa 'GMT' en lugar de un offset numérico.
                    # Lo manejamos como un texto literal en el formato.
                    dt_objeto = datetime.strptime(pub_date_tag.text, '%a, %d %b %Y %H:%M:%S GMT')
                    # Formateamos la fecha a un formato más legible en español
                    fecha_str = dt_objeto.strftime('%d de %B de %Y')
                except ValueError:
                    # Si el formato anterior falla, intentamos con el formato con offset por si cambia.
                    dt_objeto = datetime.strptime(pub_date_tag.text, '%a, %d %b %Y %H:%M:%S %z')
                    fecha_str = dt_objeto.strftime('%d de %B de %Y')


            lista_de_noticias.append({
                'titulo': titulo,
                'enlace': enlace,
                'descripcion': descripcion,
                'imagen_url': imagen_url,
                'fecha': fecha_str # Añadimos la fecha al diccionario
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
    global urls_noticias_enviadas
    print("Revisando el feed en busca de nuevas noticias...")

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
    """Extrae y muestra las 5 noticias más recientes de la página."""
    await ctx.send("Analizando el feed y extrayendo las últimas 5 noticias...")

    noticias = extraer_noticias()

    if not noticias:
        await ctx.send("No se pudieron extraer noticias. Revisa la consola de Replit en busca de errores.")
        return

    await ctx.send(f"Se han encontrado {len(noticias)} noticias. Mostrando las 5 más recientes:")
    for noticia in noticias[:5]:
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
