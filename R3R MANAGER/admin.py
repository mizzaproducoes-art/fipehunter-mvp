import streamlit as st
import pandas as pd
import re
import pdfplumber
from io import BytesIO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="R3R Enterprise", layout="wide", page_icon="🏢")

st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        div[data-testid="stMetric"] {
            background-color: #1E1E1E; border: 1px solid #333;
            padding: 15px; border-radius: 10px; color: white;
        }
        div.stDownloadButton > button {
            width: 100%; background-color: #00C853; color: white;
            font-weight: bold; padding: 15px; border-radius: 8px;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# --- MOTOR DE LEITURA BLINDADO (V3.2 - CLEAN & SHIELDED) ---


def parse_money(value_str):
    if not value_str:
        return None
    clean = re.sub(r"[^\d,]", "", str(value_str))
    if not clean:
        return None
    try:
        if "," in clean:
            val = float(clean.replace(".", "").replace(",", "."))
        else:
            val = float(clean.replace(".", ""))
        return val if val > 2000 else None
    except:
        return None


def clean_model_v32(text):
    text = str(text).upper().replace("\n", " ")

    # 1. Remove Placas
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)

    # 2. Remove Preços (R$ ou formato numérico de preço)
    text = re.sub(r"R\$\s?[\d\.,]+", "", text)
    text = re.sub(r"\b\d{2}\.\d{3},\d{2}\b", "", text)

    # 3. Lista de Bloqueio Pesada (Endereços e Metadados)
    blocklist = [
        "OFERTA",
        "DISPONIVEL",
        "VCPBR",
        "VCPER",
        "APROVADO",
        "BARUERI",
        "ALPHAVILLE",
        "SP",
        "MARGIN",
        "FIPE",
        "ORCAMENTO",
        "LOJA",
        "ENDEREÇO",
        "KM",
        "PRECO",
        "ESTOQUE",
        "ALAMEDA",
        "RUA",
        "AVENIDA",
        "VIA",
        "CENTRO",
        "MARGEM",
        "LUCRO",
        "RIO",
        "NEGRO",
        "ARAGUAIA",
        "MAMORE",
        "AMERICA",
        "BRASIL",
        "SANTANA",
        "PARNAIBA",
        "TAMBORE",
        "INDUSTRIAL",
        "JARDIM",
        "VILA",
        "EDIFICIO",
        "ANDAR",
        "SALA",
        "LOJA",
        "BLOCO",
        "NUMERO",
        "CEP",
        "BAIRRO",
        "CIDADE",
        "ESTADO",
        "FIXO",
        "MOVEL",
        "TEL",
        "PHONE",
        "COM",
        "BRANCO",
        "PRETO",
        "PRATA",
        "CINZA",
        "VERMELHO",
        "AZUL",
        "BEGE",
        "VERDE",
        "AMARELO",
        "OUTROS",
    ]

    # Marcadores de marca para priorizar
    marcas = [
        "CHEVROLET",
        "VOLKSWAGEN",
        "FIAT",
        "TOYOTA",
        "HONDA",
        "HYUNDAI",
        "JEEP",
        "RENAULT",
        "NISSAN",
        "FORD",
        "MITSUBISHI",
        "BMW",
        "MERCEDES",
        "AUDI",
        "CITROEN",
        "PEUGEOT",
    ]

    words = text.split()

    # Tenta identificar a marca primeiro
    marca_detectada = ""
    for w in words:
        if w in marcas:
            marca_detectada = w
            break

    # Filtra palavras inúteis
    clean_words = []
    for w in words:
        # Se for a marca e já detectamos, mantém
        if w == marca_detectada:
            if w not in clean_words:
                clean_words.append(w)
            continue

        # Filtra se estiver na blocklist ou for muito curta/vazia ou for número puro
        if w in blocklist or len(w) <= 2 or w.isdigit():
            continue

        # Filtra se contiver símbolos de endereço
        if any(char in w for char in ["/", "-", ",", "."]):
            continue

        clean_words.append(w)

    # Se detectou a marca, garante que ela esteja no início
    if marca_detectada and marca_detectada in clean_words:
        clean_words.remove(marca_detectada)
        final_list = [marca_detectada] + clean_words
    else:
        final_list = clean_words

    return " ".join(final_list[:6])


def process_pdf_v32(file):
    data_found = []
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    if not full_text:
        return []

    plate_pattern = r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b"
    plates_found = list(re.finditer(plate_pattern, full_text))

    processed_plates = set()

    for match in plates_found:
        placa = match.group()
        if placa in processed_plates:
            continue

        start_idx = match.start()
        end_idx = match.end()

        # Contexto bidirecional reduzido para mais precisão (150 antes, 300 depois)
        context_start = max(0, start_idx - 150)
        context_end = min(len(full_text), end_idx + 300)
        context = full_text[context_start:context_end]

        # Extrai preços
        prices_raw = re.findall(
            r"R\$\s?[\d\.,]+|(?<=\s)[\d\.]{5,8},[\d]{2}(?=\s|$)|\b\d{2}\.\d{3}\b",
            context,
        )
        prices = []
        for p in prices_raw:
            val = parse_money(p)
            if val and val > 10000:
                prices.append(val)

        prices = sorted(list(set(prices)), reverse=True)

        if len(prices) >= 2:
            fipe = prices[0]
            custo = prices[1]

            # KM
            km = 0
            km_matches = re.findall(r"\b\d{1,3}\.?\d{3}\b", context)
            for km_cand in km_matches:
                k_val = int(str(km_cand).replace(".", ""))
                if 1000 < k_val < 300000:
                    km = k_val
                    break

            modelo = clean_model_v32(context)

            # Ano
            ano_matches = re.findall(r"\b(20[1-2][0-9])\b", context)
            ano_fab = ano_matches[0] if len(ano_matches) > 0 else "N/D"
            ano_mod = ano_matches[1] if len(ano_matches) > 1 else ano_fab

            data_found.append(
                {
                    "Placa": placa,
                    "Modelo": modelo,
                    "Ano": f"{ano_fab}/{ano_mod}",
                    "KM": km,
                    "Fipe": fipe,
                    "Custo_Original": custo,
                }
            )
            processed_plates.add(placa)

    return data_found


# --- FRONTEND B2B ---
with st.sidebar:
    st.title("🏢 R3R Admin v3.2")
    st.divider()
    st.header("Margem R3R")
    margem = st.number_input("Adicionar Valor Fixo (R$):", value=2000.0, step=100.0)

st.title("Gerador de Listas R3R 🚀")
st.caption("Motor Clean & Shielded v3.2")

uploaded_file = st.file_uploader("📂 PDF da Fonte (Alphaville/Localiza)", type="pdf")

if uploaded_file:
    with st.spinner("Refinando Extração de Dados..."):
        data = process_pdf_v32(uploaded_file)
        if data:
            df = pd.DataFrame(data)

            # Cálculos
            df["Preco_Venda"] = df["Custo_Original"] + margem
            df["Lucro_R3R"] = df["Preco_Venda"] - df["Custo_Original"]
            df = df.sort_values(by="Preco_Venda")

            # Dashboard
            c1, c2, c3 = st.columns(3)
            c1.metric("Veículos", len(df))
            c2.metric("Total Compra", f"R$ {df['Custo_Original'].sum():,.0f}")
            c3.metric("Lucro Estimado", f"R$ {df['Lucro_R3R'].sum():,.0f}")

            # Tabela
            st.dataframe(
                df[
                    [
                        "Placa",
                        "Modelo",
                        "Ano",
                        "KM",
                        "Fipe",
                        "Custo_Original",
                        "Preco_Venda",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo_Original": st.column_config.NumberColumn(
                        "🔴 Custo", format="R$ %.2f"
                    ),
                    "Preco_Venda": st.column_config.NumberColumn(
                        "🟢 Venda", format="R$ %.2f"
                    ),
                    "Fipe": st.column_config.NumberColumn("Fipe", format="R$ %.2f"),
                    "KM": st.column_config.NumberColumn("KM", format="%d km"),
                },
            )

            # Exportar
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_exp = df[
                    [
                        "Modelo",
                        "Placa",
                        "Ano",
                        "KM",
                        "Fipe",
                        "Custo_Original",
                        "Preco_Venda",
                    ]
                ]
                df_exp.columns = [
                    "MODELO",
                    "PLACA",
                    "ANO",
                    "KM",
                    "FIPE",
                    "CUSTO COMPRA",
                    "PREÇO VENDA",
                ]
                df_exp.to_excel(writer, index=False)

            st.download_button(
                "📥 BAIXAR EXCEL R3R",
                output.getvalue(),
                "Lista_R3R_Oficial.xlsx",
                "application/vnd.ms-excel",
            )
        else:
            st.error("Nenhum veículo detectado com as regras de filtragem atuais.")
