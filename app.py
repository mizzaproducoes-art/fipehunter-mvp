import streamlit as st
import pandas as pd
import re
import pdfplumber

st.set_page_config(
    page_title="FipeHunter v0.7 (Organized)", page_icon="🧰", layout="wide"
)


# --- UTILITÁRIOS ---
def clean_currency(value_str):
    if not value_str:
        return 0.0
    # Limpa apenas números e separadores
    clean = re.sub(r"[^\d,.]", "", str(value_str))
    if not clean:
        return 0.0

    # Lógica de Pontuação (BR vs US)
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    else:
        # Se > 3 dígitos e sem vírgula, assume que ponto é milhar (ex: 100.000)
        clean = clean.replace(".", "")

    try:
        return float(clean)
    except:
        return 0.0


def clean_model_name(text):
    # Remove lixo comum para deixar só o nome do carro
    text = text.replace('"', "").replace("'", "").replace("\n", " ")
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)  # Remove Placa
    text = re.sub(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", "", text)  # Remove Preços

    stopwords = [
        "oferta",
        "disponivel",
        "sp",
        "barueri",
        "sorocaba",
        "campinas",
        "margem",
        "fipe",
        "preço",
        "ganho",
        "ipva",
    ]
    words = text.split()
    clean = [w for w in words if w.lower() not in stopwords and len(w) > 2]
    return " ".join(clean[:6])


# --- DRIVERS ESPECÍFICOS (A ORGANIZAÇÃO) ---


def driver_r3r(text):
    """Lógica exclusiva para listas R3R (Excel exportado)"""
    data = []
    # R3R tem linhas claras começando com placa.
    # Ex: "RUV5G79", "MOBI LIKE...", "2022", "R$ 53.602"

    lines = text.split("\n")
    for line in lines:
        plate_match = re.search(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", line)
        if plate_match:
            # Captura todos os valores monetários da linha
            prices = re.findall(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", line)
            clean_prices = sorted(
                [clean_currency(p) for p in prices if clean_currency(p) > 3000],
                reverse=True,
            )

            # R3R Típica: [Fipe, Preço, Lucro] ou [Fipe, Preço]
            if len(clean_prices) >= 2:
                item = {
                    "Placa": plate_match.group(),
                    "Modelo": clean_model_name(line),
                    "Fipe": clean_prices[0],  # Maior valor
                    "Repasse": clean_prices[1],  # Segundo maior
                    "Origem": "R3R/Excel",
                }
                # Tenta achar ano
                ym = re.search(r"\b(20[1-2][0-9])\b", line)
                item["Ano"] = ym.group(0) if ym else "-"

                data.append(item)
    return data


def driver_alphaville(text):
    """Lógica para Alphaville (Texto bagunçado com IPVA misturado)"""
    data = []
    # Alphaville quebra linhas, então usamos o 'Aspirador' (acumula texto até achar nova placa)

    contexts = re.split(r"(\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b)", text)

    # O split retorna [lixo, PLACA, dados, PLACA, dados...]
    # Pulamos o primeiro elemento e iteramos em pares (Placa, Dados)
    for i in range(1, len(contexts) - 1, 2):
        placa = contexts[i]
        content = contexts[i + 1]

        prices = re.findall(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", content)
        clean_prices = sorted(
            [clean_currency(p) for p in prices if clean_currency(p) > 2000],
            reverse=True,
        )

        # Alphaville: [Fipe, Repasse, IPVA (opcional)]
        if len(clean_prices) >= 2:
            item = {
                "Placa": placa,
                "Modelo": clean_model_name(content),
                "Fipe": clean_prices[0],
                "Repasse": clean_prices[1],
                "Origem": "Alphaville",
            }

            # Se tiver um terceiro valor que parece taxa (entre 2k e 15k)
            # E esse valor NÃO for igual ao Lucro Bruto (Fipe - Repasse)
            lucro_bruto = item["Fipe"] - item["Repasse"]
            if len(clean_prices) > 2:
                terceiro = clean_prices[2]
                if 2000 < terceiro < 15000 and abs(lucro_bruto - terceiro) > 500:
                    item["IPVA_Extra"] = terceiro

            ym = re.search(r"\b(20[1-2][0-9])\b", content)
            item["Ano"] = ym.group(0) if ym else "-"
            data.append(item)
    return data


def driver_universal(text):
    """Fallback para listas desconhecidas"""
    data = []
    lines = text.split("\n")
    for line in lines:
        plate_match = re.search(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", line)
        if plate_match:
            prices = re.findall(r"(?:R\$|RS|R|\$)\s?[\d\.\s,]+", line)
            clean_prices = sorted(
                [clean_currency(p) for p in prices if clean_currency(p) > 3000],
                reverse=True,
            )

            if len(clean_prices) >= 2:
                data.append(
                    {
                        "Placa": plate_match.group(),
                        "Modelo": clean_model_name(line),
                        "Ano": "-",
                        "Fipe": clean_prices[0],
                        "Repasse": clean_prices[1],
                        "Origem": "Universal",
                    }
                )
    return data


# --- ROTEADOR (O CÉREBRO) ---
def process_file_smartly(text):
    # Detecta assinaturas no texto para escolher o driver
    if "Ganho IPVA" in text or "PREÇO CLIENTE" in text:
        st.toast("Layout R3R detectado! Aplicando Driver R3R.", icon="🚜")
        return driver_r3r(text)
    elif (
        "Alphaville" in text or "ALPHAVILLE" in text or "Ganho" in text
    ):  # Alphaville também usa termo Ganho as vezes
        st.toast("Layout Alphaville detectado! Aplicando Driver Complexo.", icon="🏙️")
        return driver_alphaville(text)
    else:
        st.toast("Layout Padrão. Aplicando Driver Universal.", icon="⚙️")
        return driver_universal(text)


# --- FRONTEND ---
st.title("🧰 FipeHunter v0.7")
st.markdown("**O Canivete Suíço dos Repasses**")

uploaded_file = st.file_uploader(
    "Arraste seu PDF (R3R, Alphaville, Desmobja...)", type="pdf"
)

if uploaded_file:
    with st.spinner("Identificando layout e processando..."):
        try:
            full_text = ""
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        full_text += t + "\n"

            # O Roteador decide quem trabalha
            raw_data = process_file_smartly(full_text)

            # Processamento Final (Calcula Lucros)
            final_data = []
            for item in raw_data:
                ipva = item.get("IPVA_Extra", 0.0)
                lucro = item["Fipe"] - item["Repasse"] - ipva
                margem = (lucro / item["Fipe"]) * 100 if item["Fipe"] > 0 else 0

                # Filtro de Sanidade (Margem entre 2% e 70%)
                if 2 < margem < 70:
                    item["Lucro_Real"] = lucro
                    item["Margem_%"] = round(margem, 1)
                    item["Status"] = "Com IPVA" if ipva > 0 else "Ok"
                    final_data.append(item)

            df = pd.DataFrame(final_data)

            if not df.empty:
                df = df.sort_values(by="Lucro_Real", ascending=False)

                st.divider()
                st.subheader("🏆 Top Oportunidades")
                cols = st.columns(3)
                for i in range(min(3, len(df))):
                    row = df.iloc[i]
                    cols[i].metric(
                        f"{row['Modelo'][:20]}..",
                        f"R$ {row['Lucro_Real']:,.0f}",
                        f"{row['Margem_%']}%",
                    )
                    cols[i].caption(f"{row['Placa']} | {row['Origem']}")

                st.divider()
                st.dataframe(
                    df[
                        [
                            "Modelo",
                            "Ano",
                            "Placa",
                            "Fipe",
                            "Repasse",
                            "Lucro_Real",
                            "Margem_%",
                            "Status",
                            "Origem",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.error(
                    "Não encontrei carros válidos. O layout pode ser muito novo ou imagem."
                )

        except Exception as e:
            st.error(f"Erro no processamento: {e}")
