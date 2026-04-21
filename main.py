# ================================================================
#  BOT DE ALERTAS DE ACCIONES - TELEGRAM
#  Versión: Servidor en la nube (Railway)
#  Las credenciales se leen desde variables de entorno (seguro)
# ================================================================

import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import schedule
import time
from datetime import datetime

# ================================================================
#  ⚙️  CONFIGURACIÓN
#  NO pongas el token acá. Se configura en Railway como variable.
# ================================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")

TICKERS = {
    "Meta":          "META",
    "Microsoft":     "MSFT",
    "Mercado Libre": "MELI",
    "S&P 500":       "SPY",
    "NUBANK":        "NU",
    "NOW SERVICES":   "NOW",
    "NVIDIA":         "NVDA",
    "XLP":            "XLP",
    "YPF":            "YPF",
    "BRKB":           "BRK.B",
    "IBM":            "IBM",
    "BTC":            "IBIT",
    "XLF":            "XLF",
    "BIOCERES":       "BIOX",
    "NIKE":           "NKE",
    "RIO TINTO":      "RIO",
    "VISA":           "V",
    "IWM":            "IWM",
    "SHORT SPY":      "SH",
    "SNAPCHAT":       "SNAP",
    "ALIBABA":        "BABA",
    "DIGITAL REALTY": "DLR",
    "VISTA":          "VIST",
    "CONSTELLATION ENERGY": "CEG",
}

RSI_SOBREVENTA    = 30
RSI_SOBRECOMPRA   = 70
STOCH_SOBREVENTA  = 19
STOCH_SOBRECOMPRA = 81
MINIMO_SEÑALES    = 2

# ================================================================
#  📐  INDICADORES
# ================================================================

def calcular_macd(close, fast=12, slow=26, signal=9):
    ema_fast    = close.ewm(span=fast,   adjust=False).mean()
    ema_slow    = close.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line

def calcular_rsi(close, periodos=14):
    delta   = close.diff()
    avg_gan = delta.clip(lower=0).ewm(com=periodos-1, adjust=False).mean()
    avg_per = (-delta).clip(lower=0).ewm(com=periodos-1, adjust=False).mean()
    return 100 - (100 / (1 + avg_gan / avg_per))

def calcular_estocastico(high, low, close, k=14, d=3):
    stoch_k        = 100 * (close - low.rolling(k).min()) / (high.rolling(k).max() - low.rolling(k).min())
    stoch_k_smooth = stoch_k.rolling(d).mean()
    return stoch_k_smooth, stoch_k_smooth.rolling(d).mean()

def obtener_y_calcular(ticker, periodo, intervalo):
    df = yf.download(ticker, period=periodo, interval=intervalo,
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    if len(df) < 40:
        return None

    close, high, low = df["Close"].squeeze(), df["High"].squeeze(), df["Low"].squeeze()
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = calcular_macd(close)
    df["RSI"]                                       = calcular_rsi(close)
    df["STOCH_K"], df["STOCH_D"]                   = calcular_estocastico(high, low, close)
    return df.dropna()

# ================================================================
#  📡  TELEGRAM
# ================================================================

def enviar_telegram(mensaje):
    if not BOT_TOKEN or not CHAT_ID:
        print("  ⚠️  BOT_TOKEN o CHAT_ID no configurados.")
        return
    if not mensaje or not mensaje.strip():
        print("  ⚠️  Mensaje vacío, no se envía.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    print(f"  📨 Enviando mensaje ({len(mensaje)} chars)...")
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": mensaje, "parse_mode": "HTML"}, timeout=10)
        if r.status_code != 200:
            print(f"  ⚠️  Error Telegram: {r.text}")
            print(f"  ⚠️  Mensaje problemático: {repr(mensaje[:200])}")
    except Exception as e:
        print(f"  ⚠️  Error enviando: {e}")

# ================================================================
#  🔍  ANÁLISIS
# ================================================================

def analizar(df, nombre, temporalidad):
    if df is None or len(df) < 3:
        return

    u, a = df.iloc[-1], df.iloc[-2]
    def v(col, fila): return float(fila[col])

    macd_alcista   = v("MACD",a) < v("MACD_signal",a) and v("MACD",u) > v("MACD_signal",u)
    rsi_compra     = v("RSI",u) < RSI_SOBREVENTA
    stoch_c_compra = v("STOCH_K",u) < STOCH_SOBREVENTA and v("STOCH_K",u) > v("STOCH_D",u) and v("STOCH_K",a) <= v("STOCH_D",a)
    stoch_z_compra = v("STOCH_K",u) < STOCH_SOBREVENTA

    macd_bajista   = v("MACD",a) > v("MACD_signal",a) and v("MACD",u) < v("MACD_signal",u)
    rsi_venta      = v("RSI",u) > RSI_SOBRECOMPRA
    stoch_c_venta  = v("STOCH_K",u) > STOCH_SOBRECOMPRA and v("STOCH_K",u) < v("STOCH_D",u) and v("STOCH_K",a) >= v("STOCH_D",a)
    stoch_z_venta  = v("STOCH_K",u) > STOCH_SOBRECOMPRA

    n_c = sum([macd_alcista, rsi_compra, stoch_c_compra or stoch_z_compra])
    n_v = sum([macd_bajista, rsi_venta,  stoch_c_venta  or stoch_z_venta])
    precio = v("Close", u)

    icono = "🟢" if n_c >= MINIMO_SEÑALES else ("🔴" if n_v >= MINIMO_SEÑALES else "⚪")
    print(f"  {icono} {temporalidad:7s} | RSI={v('RSI',u):.1f}  STOCH={v('STOCH_K',u):.1f}  MACD_hist={v('MACD_hist',u):.4f}")

    if n_c >= MINIMO_SEÑALES:
        lineas = []
        if macd_alcista:   lineas.append("✅ MACD: cruce alcista")
        if rsi_compra:     lineas.append(f"✅ RSI: en sobreventa ({v('RSI',u):.1f})")
        if stoch_c_compra: lineas.append(f"✅ Estocástico: cruce alcista ({v('STOCH_K',u):.1f})")
        elif stoch_z_compra: lineas.append(f"✅ Estocástico: en sobreventa ({v('STOCH_K',u):.1f})")
        enviar_telegram(
            f"🟢 <b>SEÑAL DE COMPRA — {nombre}</b>\n"
            f"📅 Temporalidad: <b>{temporalidad}</b>\n"
            f"💵 Precio: <b>${precio:,.2f}</b>\n——————————————————————\n"
            + "\n".join(lineas) +
            f"\n——————————————————————\n🕐 {datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

    elif n_v >= MINIMO_SEÑALES:
        lineas = []
        if macd_bajista:  lineas.append("🔴 MACD: cruce bajista")
        if rsi_venta:     lineas.append(f"🔴 RSI: en sobrecompra ({v('RSI',u):.1f})")
        if stoch_c_venta: lineas.append(f"🔴 Estocástico: cruce bajista ({v('STOCH_K',u):.1f})")
        elif stoch_z_venta: lineas.append(f"🔴 Estocástico: en sobrecompra ({v('STOCH_K',u):.1f})")
        enviar_telegram(
            f"🔴 <b>SEÑAL DE VENTA — {nombre}</b>\n"
            f"📅 Temporalidad: <b>{temporalidad}</b>\n"
            f"💵 Precio: <b>${precio:,.2f}</b>\n——————————————————————\n"
            + "\n".join(lineas) +
            f"\n——————————————————————\n🕐 {datetime.now().strftime('%d/%m/%Y  %H:%M')}"
        )

# ================================================================
#  🔁  CICLO
# ================================================================

def verificar_todas():
    print(f"\n{'='*45}\n  {datetime.now().strftime('%d/%m/%Y  %H:%M:%S')}\n{'='*45}")
    for nombre, ticker in TICKERS.items():
        print(f"\n📊 {nombre} ({ticker})")
        try:
            analizar(obtener_y_calcular(ticker, "6mo", "1d"),  nombre, "Diaria")
            analizar(obtener_y_calcular(ticker, "2y",  "1wk"), nombre, "Semanal")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    print(f"\n✅ Próxima verificación en 1 hora.\n")

# ================================================================
#  🚀  INICIO
# ================================================================

if __name__ == "__main__":
    print("\n🤖 Bot iniciado en el servidor!")
    enviar_telegram(
        "🤖 <b>Bot de alertas iniciado en la nube</b>\n\n"
        "📊 Monitoreando:\n" +
        "\n".join([f"  • {n}" for n in TICKERS.keys()]) +
        "\n\n⏱ Verificación automática cada 1 hora."
    )
    verificar_todas()
    schedule.every(1).hours.do(verificar_todas)
    while True:
        schedule.run_pending()
        time.sleep(60)
