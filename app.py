import streamlit as st
import pandas as pd
import re
import pdfplumber

# --- 1. CONFIGURAÇÃO VISUAL PREMIUM ---
st.set_page_config(page_title="FipeHunter Pro", layout="wide", page_icon="🎯")

st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        div[data-testid="stMetric"] {
            background-color: #1E1E1E;
            border: 1px solid #333;
            padding: 15px;
            border-radius: 10px;
            color: white;
        }
        div.stDownloadButton > button {
            width: 100%;
            background-color: #00C853;
            color: white;
            font-weight: bold;
            border: none;
            padding: 15px;
            border-radius: 8px;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# --- 2. DADOS PRÉ-CARREGADOS (PARA OS FILTROS APARECEREM ANTES) ---
LISTA_MARCAS = [
    "CHEVROLET",
    "VOLKSWAGEN",
    "FIAT",
    "TOYOTA",
    "HONDA",
    "HYUNDAI",
    "JEEP",
    "RENAULT",
    "NISSAN",
    "PEUGEOT",
    "CITROEN",
    "FORD",
    "MITSUBISHI",
    "BMW",
    "MERCEDES-BENZ",
    "AUDI",
    "KIA",
    "CAOA CHERY",
    "RAM",
    "BYD",
    "GWM",
]
LISTA_CORES = [
    "BRANCO",
    "PRETO",
    "PRATA",
    "CINZA",
    "VERMELHO",
    "AZUL",
    "BEGE",
    "AMARELO",
    "VERDE",
    "MARROM",
    "DOURADO",
    "LARANJA",
    "VINHO",
]
LISTA_ANOS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017]


# --- 3. SISTEMA DE SEGURANÇA ---
def check_password():
    if st.session_state.get("authenticated", False):
        return True

    st.markdown("### 🔒 Acesso Restrito - FipeHunter")
    st.markdown("Digite a senha enviada no seu e-mail de compra.")
    password = st.text_input("Senha de Acesso", type="password")

    if st.button("Entrar"):
        if password == "FIPE2026":
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
            return False
    return False


if not check_password():
    st.stop()

# --- 4. MOTORES DE EXTRAÇÃO ---


def parse_money(value_str):
    if not value_str:
        return None
    s = str(value_str).strip()
    if "R$" not in s and "," not in s:
        return None
    clean = re.sub(r"[^\d,]", "", s)
    if not clean:
        return None
    try:
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(".", "")
        val = float(clean)
        return val if val > 2000 else None
    except Exception:
        return None


def parse_km(value_str):
    if not value_str:
        return 0
    s = str(value_str).strip()
    if "R$" in s or "," in s:
        return 0
    clean = re.sub(r"[^\d]", "", s)
    try:
        val = int(clean)
        return val if 0 <= val < 400000 else 0
    except Exception:
        return 0


def extract_years(text):
    short_years = re.search(r"\b(\d{2})/(\d{2})\b", text)
    if short_years:
        y1 = int(short_years.group(1)) + 2000
        y2 = int(short_years.group(2)) + 2000
        return y1, y2
    years = re.findall(r"\b(20[1-2][0-9])\b", text)
    unique_years = sorted(list(set([int(y) for y in years])))
    if len(unique_years) >= 2:
        return unique_years[0], unique_years[1]
    elif len(unique_years) == 1:
        return unique_years[0], unique_years[0]
    return 0, 0


def extract_color(text):
    text_upper = text.upper()
    for cor in LISTA_CORES:
        if cor in text_upper:
            if cor == "BRANCA":
                return "BRANCO"  # Normalização simples
            return cor
    return "OUTROS"


def clean_model_and_brand(text):
    text = str(text).replace("\n", " ").replace('"', "").replace("'", "")
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)
    text = re.sub(r"R\$\s?[\d\.,]+", "", text)
    text = re.sub(r"\b20[1-2][0-9]\b", "", text)

    stopwords = [
        "oferta",
        "disponivel",
        "sp",
        "barueri",
        "maua",
        "sorocaba",
        "campinas",
        "margem",
        "fipe",
        "preco",
        "ganho",
        "ipva",
        "km",
        "flex",
        "diesel",
        "manual",
        "automatico",
        "automático",
        "aut",
    ] + LISTA_CORES
    words = text.split()
    clean_words = [
        w
        for w in words
        if w.lower() not in [s.lower() for s in stopwords]
        and len(w) > 2
        and not w.isdigit()
    ]
    full_name = " ".join(clean_words[:6])

    # Extração de Marca Baseada na Lista Pré-definida
    marca_encontrada = "OUTROS"
    if clean_words:
        first = clean_words[0].upper()
        # Normalizações comuns
        if first in ["VW", "VOLKS"]:
            first = "VOLKSWAGEN"
        if first in ["GM", "CHEV"]:
            first = "CHEVROLET"

        if first in LISTA_MARCAS:
            marca_encontrada = first
        else:
            # Tenta achar a marca no meio do nome se não for a primeira palavra
            for m in LISTA_MARCAS:
                if m in full_name.upper():
                    marca_encontrada = m
                    break

    return full_name, marca_encontrada


def process_pdf_universal(file):
    data_found = []
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

        # ESTRATÉGIA A: Tabela
        try:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        row_str = " ".join([str(c) for c in row if c])
                        plate_match = re.search(
                            r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", row_str
                        )
                        if plate_match:
                            prices = []
                            km = 0
                            for cell in row:
                                c_str = str(cell).strip()
                                m = parse_money(c_str)
                                if m:
                                    prices.append(m)
                                else:
                                    k = parse_km(c_str)
                                    if k > km:
                                        km = k
                            prices = sorted(list(set(prices)), reverse=True)
                            if len(prices) >= 2:
                                modelo, marca = clean_model_and_brand(row_str)
                                ano_fab, ano_mod = extract_years(row_str)
                                cor = extract_color(row_str)
                                data_found.append(
                                    {
                                        "Marca": marca,
                                        "Modelo": modelo,
                                        "Placa": plate_match.group(),
                                        "Ano_Fab": ano_fab,
                                        "Ano_Mod": ano_mod,
                                        "Cor": cor,
                                        "KM": km,
                                        "Fipe": prices[0],
                                        "Repasse": prices[1],
                                    }
                                )
        except Exception:
            pass

        # ESTRATÉGIA B: Texto
        if len(data_found) < 3:
            parts = re.split(r"(\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b)", full_text)
            temp_data = []
            for i in range(1, len(parts) - 1, 2):
                placa = parts[i]
                content = parts[i + 1]
                prices_raw = re.findall(r"R\$\s?[\d\.,]+", content)
                prices = sorted(
                    [p for p in [parse_money(pr) for pr in prices_raw] if p],
                    reverse=True,
                )
                km = 0
                km_match = re.search(r"(?:KM|Km)\s?([\d\.]+)", content)
                if km_match:
                    km = parse_km(km_match.group(1))
                else:
                    loose = re.search(r"\b(\d{4,6})\b", content)
                    if loose and 0 < int(loose.group(1)) < 300000:
                        km = int(loose.group(1))
                if len(prices) >= 2:
                    modelo, marca = clean_model_and_brand(content)
                    ano_fab, ano_mod = extract_years(content)
                    cor = extract_color(content)
                    temp_data.append(
                        {
                            "Marca": marca,
                            "Modelo": modelo,
                            "Placa": placa,
                            "Ano_Fab": ano_fab,
                            "Ano_Mod": ano_mod,
                            "Cor": cor,
                            "KM": km,
                            "Fipe": prices[0],
                            "Repasse": prices[1],
                        }
                    )
            if len(temp_data) > len(data_found):
                data_found = temp_data
    return data_found


# --- 5. SIDEBAR COM FILTROS FIXOS (A MÁGICA) ---

st.sidebar.header("🔍 Filtros Pré-Upload")
st.sidebar.caption("Configure antes ou depois de carregar.")

# 1. Filtros Financeiros
max_invest = st.sidebar.number_input(
    "💰 Investimento Máximo (R$):", min_value=0.0, value=0.0, step=5000.0
)
target_km = st.sidebar.slider("🚗 KM Máxima:", 0, 200000, 150000, step=5000)
min_margin = st.sidebar.slider("📈 Margem Mínima (%):", 0, 50, 10)

st.sidebar.divider()
st.sidebar.header("🚙 Filtros de Veículo")

# 2. Filtros de Atributos (AGORA FIXOS)
# Deixamos vazio [] como padrão para "TODOS"
sel_marcas = st.sidebar.multiselect("Montadora:", LISTA_MARCAS)
sel_anos = st.sidebar.multiselect("Ano Modelo:", LISTA_ANOS)
sel_cores = st.sidebar.multiselect("Cor:", LISTA_CORES)

# 3. Filtro de Modelo (Texto Livre - Funciona antes do Upload)
txt_modelo = st.sidebar.text_input("Buscar Modelo (ex: Corolla):", "")

# --- 6. ÁREA PRINCIPAL ---

st.title("🎯 FipeHunter Pro")
st.markdown("### Inteligência Artificial para Repasses")

if sel_marcas or txt_modelo:
    st.info(
        f"🎯 Filtro Ativo: Buscando {sel_marcas if sel_marcas else ''} {txt_modelo}"
    )

uploaded_file = st.file_uploader("Arraste seu PDF aqui para processar", type="pdf")

if uploaded_file:
    with st.spinner("Aplicando seus filtros..."):
        try:
            raw_data = process_pdf_universal(uploaded_file)
            df = pd.DataFrame(raw_data)

            if not df.empty:
                final_data = []

                for index, item in df.iterrows():
                    lucro = item["Fipe"] - item["Repasse"]

                    if item["Fipe"] > 0:
                        margem = (lucro / item["Fipe"]) * 100

                        # --- VERIFICAÇÃO DE FILTROS ---

                        # 1. Marca (Se lista vazia, passa tudo. Se não, checa)
                        pass_marca = True
                        if sel_marcas:
                            if item["Marca"] not in sel_marcas:
                                pass_marca = False

                        # 2. Ano (Se lista vazia, passa tudo)
                        pass_ano = True
                        if sel_anos:
                            if item["Ano_Mod"] not in sel_anos:
                                pass_ano = False

                        # 3. Cor
                        pass_cor = True
                        if sel_cores:
                            if item["Cor"] not in sel_cores:
                                pass_cor = False

                        # 4. Modelo (Busca Texto Parcial)
                        pass_modelo = True
                        if txt_modelo:
                            if txt_modelo.upper() not in item["Modelo"].upper():
                                pass_modelo = False

                        # 5. Financeiros
                        pass_invest = (
                            True if max_invest == 0 else (item["Repasse"] <= max_invest)
                        )
                        pass_km = True if item["KM"] <= target_km else False
                        pass_margin = True if margem >= min_margin else False

                        if (
                            pass_marca
                            and pass_ano
                            and pass_cor
                            and pass_modelo
                            and pass_invest
                            and pass_km
                            and pass_margin
                            and (1 < margem < 70)
                        ):
                            row_dict = item.to_dict()
                            row_dict["Lucro_Real"] = lucro
                            row_dict["Margem_%"] = round(margem, 1)
                            final_data.append(row_dict)

                df_final = pd.DataFrame(final_data)

                if not df_final.empty:
                    df_final = df_final.sort_values(by="Lucro_Real", ascending=False)

                    st.success(f"Encontramos {len(df_final)} veículos!")

                    # --- TOP 3 CARDS ---
                    st.divider()
                    st.subheader("🔥 Top 3 Oportunidades")
                    cols = st.columns(3)
                    for i in range(min(3, len(df_final))):
                        row = df_final.iloc[i]

                        lucro_fmt = (
                            f"R$ {row['Lucro_Real']:,.0f}".replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )
                        paga_fmt = (
                            f"R$ {row['Repasse']:,.0f}".replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )
                        ano_str = (
                            f"{row['Ano_Fab']}/{row['Ano_Mod']}"
                            if row["Ano_Mod"] > 0
                            else "N/D"
                        )

                        cols[i].metric(
                            label=f"{row['Marca']} {row['Modelo']}",
                            value=f"Lucro: {lucro_fmt}",
                            delta=f"{row['Margem_%']}% Margem",
                        )
                        cols[i].markdown(f"**Cor:** {row['Cor']} | **Ano:** {ano_str}")
                        cols[i].markdown(f"💸 **Paga:** {paga_fmt}")
                        cols[i].caption(
                            f"Fipe: R$ {row['Fipe']:,.0f} | KM: {row['KM']}"
                        )
                        cols[i].markdown(f"`{row['Placa']}`")

                    # --- TABELA DETALHADA ---
                    st.divider()
                    st.subheader("📋 Lista Completa")

                    st.dataframe(
                        df_final[
                            [
                                "Marca",
                                "Modelo",
                                "Ano_Mod",
                                "Cor",
                                "Repasse",
                                "Fipe",
                                "KM",
                                "Lucro_Real",
                                "Margem_%",
                            ]
                        ],
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Marca": "Montadora",
                            "Ano_Mod": st.column_config.NumberColumn(
                                "Ano", format="%d"
                            ),
                            "Repasse": st.column_config.NumberColumn(
                                "🔴 Você Paga", format="R$ %.2f"
                            ),
                            "Fipe": st.column_config.NumberColumn(
                                "Fipe", format="R$ %.2f"
                            ),
                            "Lucro_Real": st.column_config.NumberColumn(
                                "🟢 Seu Lucro", format="R$ %.2f"
                            ),
                            "KM": st.column_config.NumberColumn("KM", format="%d km"),
                            "Margem_%": st.column_config.NumberColumn(
                                "Margem %", format="%.1f%%"
                            ),
                        },
                    )
                else:
                    st.warning(
                        "Nenhum resultado com esses filtros. Tente limpar os filtros na lateral."
                    )
            else:
                st.warning("O arquivo não contém veículos reconhecíveis.")

        except Exception as e:
            st.error("Erro ao processar.")
            st.code(e)
else:
    # Mensagem de Boas Vindas quando não tem arquivo
    st.info(
        "👈 Configure seus filtros na barra lateral (Marca, Ano, Cor) e arraste o PDF para ver a mágica."
    )
