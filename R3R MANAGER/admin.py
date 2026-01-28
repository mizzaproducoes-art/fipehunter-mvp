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

# --- MOTOR DE LEITURA BLINDADO (V3.0 - BIDIRECIONAL) ---


def parse_money(value_str):
    if not value_str:
        return None
    # Remove R$, whitespace, etc.
    clean = re.sub(r"[^\d,]", "", str(value_str))
    if not clean:
        return None
    try:
        # Tenta formato BRL (123.456,78 ou 123456,78)
        if "," in clean:
            val = float(clean.replace(".", "").replace(",", "."))
        else:
            val = float(clean.replace(".", ""))
        return val if val > 2000 else None  # Filtra ruído
    except:
        return None


def clean_model_v3(text):
    text = str(text).upper().replace("\n", " ")
    # Regex para remover placas e preços
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)
    text = re.sub(r"R\$\s?[\d\.,]+", "", text)

    stopwords = [
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
    ]
    words = text.split()
    clean = [w for w in words if w not in stopwords and len(w) > 2 and not w.isdigit()]
    return " ".join(clean[:7])


def process_pdf_v3(file):
    data_found = []
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text += t + "\n"

    if not full_text:
        return []

    # Localiza todas as placas
    plate_pattern = r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b"
    plates_found = list(re.finditer(plate_pattern, full_text))

    for i, match in enumerate(plates_found):
        placa = match.group()
        start_idx = match.start()
        end_idx = match.end()

        # Pega contexto bidirecional (250 chars antes, 500 depois)
        context_start = max(0, start_idx - 250)
        context_end = min(len(full_text), end_idx + 500)
        context = full_text[context_start:context_end]

        # Extrai todos os preços no contexto
        # Aceita "R$ 123.456" ou apenas "123.456" se estiver perto do contexto veicular
        prices_raw = re.findall(
            r"R\$\s?[\d\.,]+|(?<=\s)[\d\.]{5,8},[\d]{2}(?=\s|$)|\b\d{2}\.\d{3}\b",
            context,
        )

        # Refina a limpeza dos preços
        prices = []
        for p in prices_raw:
            val = parse_money(p)
            if val and val > 10000:  # Carros geralmente > 10k
                prices.append(val)

        prices = sorted(list(set(prices)), reverse=True)

        if len(prices) >= 2:
            # Lógica Alphaville 2026: Maior=Fipe, Segundo=Custo
            fipe = prices[0]
            custo = prices[1]

            # Tenta pegar KM (número entre 1.000 e 300.000 perto da placa)
            km = 0
            km_matches = re.findall(r"\b\d{1,3}\.?\d{3}\b", context)
            for km_cand in km_matches:
                k_val = int(str(km_cand).replace(".", ""))
                if 1000 < k_val < 300000:
                    km = k_val
                    break

            modelo = clean_model_v3(context)

            # Tenta extrair Ano (20XX)
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

    return data_found


# --- FRONTEND B2B ---
with st.sidebar:
    st.title("🏢 R3R Admin v3.0")
    st.divider()
    st.header("Margem R3R")
    margem = st.number_input("Adicionar Valor Fixo (R$):", value=2000.0, step=100.0)

st.title("Gerador de Listas R3R 🚀")
st.caption("Motor Blindado v3.0 (Bidirecional)")

uploaded_file = st.file_uploader("📂 PDF da Fonte (Alphaville/Localiza)", type="pdf")

if uploaded_file:
    with st.spinner("Processando com Motor v3.0..."):
        data = process_pdf_v3(uploaded_file)
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
            st.error(
                "Nenhum veículo detectado. O layout do PDF pode ter mudado ou as placas não foram localizadas."
            )
