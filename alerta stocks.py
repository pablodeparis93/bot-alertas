# ================================================================
#  BOT DE ALERTAS DE ACCIONES - TELEGRAM
#  Indicadores: MACD + RSI + Estocástico | Diario y Semanal
#  Sin pandas_ta — todo calculado con pandas y numpy
# ================================================================
#
#  INSTALACIÓN (correr UNA sola vez en la terminal/cmd):
#  pip install yfinance pandas requests schedule
#
# ================================================================

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import schedule
import time
from datetime import datetime

# ================================================================
#  ⚙️  CONFIGURACIÓN - COMPLETAR CON TUS DATOS
# ================================================================

TOKEN = "8676946788:AAGuf2ZsVrTBLj9DwZztfLE01ijdZpmVk-g"
CHAT_ID = "1569295509"

TICKERS = {
    "Meta":          "META",
    "Microsoft":     "MSFT",
    "Mercado Libre": "MELI",
    "S&P 500":       "SPY",
    "NUBANK":        "NU",
    "NOW SERVICES"   "NOW",
    "NVIDIA"         "NVDA",
    "XLP"            "XLP",
    "YPF"            "YPF",
    "BRKB"           "BRK.B",
    "IBM"            "IBM",
    "BTC"            "IBIT",
    "XLF"            "XLF",
    "BIOCERES"       "BIOX",
    "NIKE"           "NKE",
    "RIO TINTO"      "RIO",
    "VISA"           "V",
    "IWM"            "IWM",
    "SHORT SPY"      "SH",
    "SNAPCHAT"       "SNAP",
    "ALIBABA"        "BABA",
    "DIGITAL REALTY" "DLR",
    "VISTA"          "VIST",
    "CONSTELLATION ENERGY" "CEG",
}

RSI_SOBREVENTA    = 30
RSI_SOBRECOMPRA   = 75
STOCH_SOBREVENTA  = 20
STOCH_SOBRECOMPRA = 80
MINIMO_SEÑALES    = 2   # Cuántos indicadores deben coincidir para alertar

# ================================================================
#  📐  CÁLCULO DE INDICADORES (sin librerías externas)
# ================================================================

def calcular_macd(close, fast=12, slow=26, signal=9):
    ema_fast    = close.ewm(span=fast,   adjust=False).mean()
    ema_slow    = close.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram

def calcular_rsi(close, periodos=14):
    delta    = close.diff()
    ganancia = delta.clip(lower=0)
    perdida  = (-delta).clip(lower=0)
    avg_gan  = ganancia.ewm(com=periodos - 1, adjust=False).mean()
    avg_per  = perdida.ewm(com=periodos - 1, adjust=False).mean()
    rs  = avg_gan / avg_per
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calcular_estocastico(high, low, close, k=14, d=3):
    low_min        = low.rolling(window=k).min()
    high_max       = high.rolling(window=k).max()
    stoch_k        = 100 * (close - low_min) / (high_max - low_min)
    stoch_k_smooth = stoch_k.rolling(window=d).mean()
    stoch_d        = stoch_k_smooth.rolling(window=d).mean()
    return stoch_k_smooth, stoch_d

def obtener_y_calcular(ticker, periodo, intervalo):
    df = yf.download(ticker, period=periodo, interval=intervalo,
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    if len(df) < 40:
        return None

    close = df["Close"].squeeze()
    high  = df["High"].squeeze()
    low   = df["Low"].squeeze()

    df["MACD"], df["MACD_signal"], df["MACD_hist"] = calcular_macd(close)
    df["RSI"]                                       = calcular_rsi(close)
    df["STOCH_K"], df["STOCH_D"]                   = calcular_estocastico(high, low, close)

    return df.dropna()

# ================================================================
#  📡  TELEGRAM
# ================================================================

def enviar_telegram(mensaje):
    url   = f"https://api.telegram.org/bot8676946788:AAGuf2ZsVrTBLj9DwZztfLE01ijdZpmVk-g/sendMessage"
    datos = {"1569295509": CHAT_ID, "ALERTA": mensaje, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=datos, timeout=10)
        if r.status_code != 200:
            print(f"  ⚠️  Error Telegram: {r.text}")
    except Exception as e:
        print(f"  ⚠️  No se pudo enviar: {e}")

# ================================================================
#  🔍  ANÁLISIS DE SEÑALES
# ================================================================

def analizar(df, nombre, temporalidad):
    if df is None or len(df) < 3:
        return

    u = df.iloc[-1]   # última vela
    a = df.iloc[-2]   # vela anterior

    def v(col, fila):
        return float(fila[col])

    # --- SEÑALES DE COMPRA ---
    macd_cruce_alcista = v("MACD", a) < v("MACD_signal", a) and v("MACD", u) > v("MACD_signal", u)
    rsi_compra         = v("RSI", u) < RSI_SOBREVENTA
    stoch_cruce_compra = (v("STOCH_K", u) < STOCH_SOBREVENTA and
                          v("STOCH_K", u) > v("STOCH_D", u) and
                          v("STOCH_K", a) <= v("STOCH_D", a))
    stoch_zona_compra  = v("STOCH_K", u) < STOCH_SOBREVENTA

    señales_compra = [
        macd_cruce_alcista,
        rsi_compra,
        stoch_cruce_compra or stoch_zona_compra,
    ]

    # --- SEÑALES DE VENTA ---
    macd_cruce_bajista = v("MACD", a) > v("MACD_signal", a) and v("MACD", u) < v("MACD_signal", u)
    rsi_venta          = v("RSI", u) > RSI_SOBRECOMPRA
    stoch_cruce_venta  = (v("STOCH_K", u) > STOCH_SOBRECOMPRA and
                          v("STOCH_K", u) < v("STOCH_D", u) and
                          v("STOCH_K", a) >= v("STOCH_D", a))
    stoch_zona_venta   = v("STOCH_K", u) > STOCH_SOBRECOMPRA

    señales_venta = [
        macd_cruce_bajista,
        rsi_venta,
        stoch_cruce_venta or stoch_zona_venta,
    ]

    n_c    = sum(señales_compra)
    n_v    = sum(señales_venta)
    precio = v("Close", u)

    # Log en consola
    icono = "🟢" if n_c >= MINIMO_SEÑALES else ("🔴" if n_v >= MINIMO_SEÑALES else "⚪")
    print(f"  {icono} {temporalidad:7s} | RSI={v('RSI',u):.1f}  "
          f"STOCH={v('STOCH_K',u):.1f}  "
          f"MACD_hist={v('MACD_hist',u):.4f}")

    # --- ALERTA DE COMPRA ---
    if n_c >= MINIMO_SEÑALES:
        lineas = []
        if macd_cruce_alcista:  lineas.append("✅ MACD: cruce alcista")
        if rsi_compra:          lineas.append(f"✅ RSI: en sobreventa ({v('RSI',u):.1f})")
        if stoch_cruce_compra:  lineas.append(f"✅ Estocástico: cruce alcista ({v('STOCH_K',u):.1f})")
        elif stoch_zona_compra: lineas.append(f"✅ Estocástico: en sobreventa ({v('STOCH_K',u):.1f})")

        enviar_telegram(
            f"🟢 <b>SEÑAL DE COMPRA — {nombre}</b>\n"
            f"📅 Temporalidad: <b>{temporalidad}</b>\n"
            f"💵 Precio: <b>${precio:,.2f}</b>\n"
            f"{'—'*24}\n"
            + "\n".join(lineas) +
            f"\n{'—'*24}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

    # --- ALERTA DE VENTA ---
    elif n_v >= MINIMO_SEÑALES:
        lineas = []
        if macd_cruce_bajista:  lineas.append("🔴 MACD: cruce bajista")
        if rsi_venta:           lineas.append(f"🔴 RSI: en sobrecompra ({v('RSI',u):.1f})")
        if stoch_cruce_venta:   lineas.append(f"🔴 Estocástico: cruce bajista ({v('STOCH_K',u):.1f})")
        elif stoch_zona_venta:  lineas.append(f"🔴 Estocástico: en sobrecompra ({v('STOCH_K',u):.1f})")

        enviar_telegram(
            f"🔴 <b>SEÑAL DE VENTA — {nombre}</b>\n"
            f"📅 Temporalidad: <b>{temporalidad}</b>\n"
            f"💵 Precio: <b>${precio:,.2f}</b>\n"
            f"{'—'*24}\n"
            + "\n".join(lineas) +
            f"\n{'—'*24}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

# ================================================================
#  🔁  CICLO PRINCIPAL
# ================================================================

def verificar_todas():
    print(f"\n{'='*45}")
    print(f"  {datetime.now().strftime('%d/%m/%Y  %H:%M:%S')}")
    print(f"{'='*45}")

    for nombre, ticker in TICKERS.items():
        print(f"\n📊 {nombre} ({ticker})")
        try:
            df_d = obtener_y_calcular(ticker, "6mo", "1d")
            analizar(df_d, nombre, "Diaria")

            df_w = obtener_y_calcular(ticker, "2y", "1wk")
            analizar(df_w, nombre, "Semanal")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\n✅ Próxima verificación en 1 hora.\n")

# ================================================================
#  🚀  INICIO
# ================================================================

if __name__ == "__main__":
    print("\n🤖 Bot de alertas iniciado!")
    enviar_telegram(
        "🤖 <b>Bot de alertas iniciado</b>\n\n"
        "📊 Monitoreando:\n" +
        "\n".join([f"  • {n}" for n in TICKERS.keys()]) +
        "\n\n⏱ Verificación cada 1 hora."
    )

    verificar_todas()
    schedule.every(1).hours.do(verificar_todas)

    while True:
        schedule.run_pending()
        time.sleep(60)
        
        
