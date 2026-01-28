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

# --- MOTOR DE LEITURA MATRIX (V4.0 - 15 COLUNAS) ---


def parse_money(value_str):
    if not value_str or pd.isna(value_str):
        return 0.0
    # Remove R$, espaços, letras e caracteres não numéricos exceto vírgula
    # Exemplo: "R$ 7 0.309,00" -> "70309,00"
    clean = re.sub(r"[^\d,]", "", str(value_str).replace(" ", ""))
    if not clean:
        return 0.0
    try:
        if "," in clean:
            val = float(clean.replace(".", "").replace(",", "."))
        else:
            val = float(clean)
        return val
    except:
        return 0.0


def clean_text(text):
    if not text or pd.isna(text):
        return ""
    return str(text).upper().strip().replace("\n", " ")


def process_pdf_v4(file):
    data_found = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Verifica se a linha tem as 15 colunas esperadas (ou aproximado)
                    # E se a primeira coluna parece uma placa ou se a linha não é cabeçalho
                    if not row or len(row) < 10:
                        continue

                    placa = clean_text(row[0])
                    # Pula cabeçalho ou linhas vazias de placa
                    if placa == "PLACA" or not placa or len(placa) < 7:
                        continue

                    # Mapping v4.0 Matrix:
                    # 0: Placa, 2: Modelo, 3: Ano Fab, 4: Ano Mod, 5: KM, 6: Cor, 7: Fipe, 9: Repasse
                    modelo = clean_text(row[2])
                    ano_fab = clean_text(row[3])
                    ano_mod = clean_text(row[4])
                    km_raw = clean_text(row[5])
                    cor = clean_text(row[6])
                    fipe_raw = row[7]
                    repasse_raw = row[9]

                    # Conversões
                    fipe = parse_money(fipe_raw)
                    repasse = parse_money(repasse_raw)

                    try:
                        km = int(re.sub(r"\D", "", km_raw))
                    except:
                        km = 0

                    if fipe > 0 and repasse > 0:
                        data_found.append(
                            {
                                "Placa": placa,
                                "Modelo": modelo,
                                "Ano": f"{ano_fab}/{ano_mod}",
                                "Cor": cor,
                                "KM": km,
                                "Fipe": fipe,
                                "Custo_Original": repasse,
                            }
                        )

    return data_found


# --- FRONTEND B2B ---
with st.sidebar:
    st.title("🏢 R3R Admin v4.0")
    st.divider()
    st.header("Margem R3R")
    margem = st.number_input("Adicionar Valor Fixo (R$):", value=2000.0, step=100.0)

st.title("Gerador de Listas R3R 🚀")
st.caption("Motor Matrix v4.0 (15 Colunas)")

uploaded_file = st.file_uploader("📂 PDF da Fonte (Alphaville/Localiza)", type="pdf")

if uploaded_file:
    with st.spinner("Analisando Colunas Matrix..."):
        data = process_pdf_v4(uploaded_file)
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
                "Nenhum veículo detectado. Verifique se o PDF tem as 15 colunas do padrão Alphaville."
            )
