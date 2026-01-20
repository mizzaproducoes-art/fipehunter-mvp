import streamlit as st
import pandas as pd
import re
import pdfplumber
from io import BytesIO

# --- 1. CONFIGURAÇÃO VISUAL PREMIUM (CSS) ---
st.set_page_config(page_title="R3R Enterprise", layout="wide", page_icon="🏢")

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
            font-size: 18px;
        }
        div.stDownloadButton > button:hover {
            background-color: #00E676;
            color: black;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# --- 2. MOTORES DE INTELIGÊNCIA ---


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
    except:
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
    except:
        return 0


def clean_model_name(text):
    text = str(text).replace("\n", " ").replace('"', "").replace("'", "")
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)
    text = re.sub(r"R\$\s?[\d\.,]+", "", text)
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
    ]
    words = text.split()
    clean = [
        w
        for w in words
        if w.lower() not in stopwords and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(clean[:6])


# --- 3. DRIVERS DE LEITURA BLINDADOS ---


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
                                data_found.append(
                                    {
                                        "Placa": plate_match.group(),
                                        "Modelo": clean_model_name(row_str),
                                        "KM": km,
                                        "Fipe": prices[0],
                                        "Custo_Original": prices[1],
                                    }
                                )
        except:
            pass

        # ESTRATÉGIA B: Texto (Fallback)
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
                    temp_data.append(
                        {
                            "Placa": placa,
                            "Modelo": clean_model_name(content),
                            "KM": km,
                            "Fipe": prices[0],
                            "Custo_Original": prices[1],
                        }
                    )
            if len(temp_data) > len(data_found):
                data_found = temp_data
    return data_found


# --- 4. INTERFACE ---
with st.sidebar:
    st.markdown("## 🏢 R3R Admin")
    st.markdown("---")
    st.markdown("### ⚙️ Configuração de Margem")
    margem_tipo = st.radio("Adicionar:", ["Valor Fixo (R$)", "Porcentagem (%)"])
    if margem_tipo == "Valor Fixo (R$)":
        margem_valor = st.number_input("Valor Extra (R$)", value=2000.0, step=100.0)
    else:
        margem_pct = st.number_input("Porcentagem Extra (%)", value=5.0, step=0.5)
    st.markdown("---")
    st.caption("Sistema v2.1 Enterprise")

st.title("Gerenciador de Estoque & Precificação")
uploaded_file = st.file_uploader("📂 Arraste o PDF da Fonte", type="pdf")

if uploaded_file:
    with st.spinner("🔄 Processando dados..."):
        data = process_pdf_universal(uploaded_file)

        if data:
            df = pd.DataFrame(data)

            # --- CÁLCULOS ---
            if margem_tipo == "Valor Fixo (R$)":
                df["Preco_Venda"] = df["Custo_Original"] + margem_valor
            else:
                df["Preco_Venda"] = df["Custo_Original"] * (1 + margem_pct / 100)

            df["Margem_R3R"] = df["Preco_Venda"] - df["Custo_Original"]

            # Ordena pelo MENOR preço de venda (mais fácil de vender)
            df = df.sort_values(by="Preco_Venda", ascending=True)

            # --- KPI DASHBOARD ---
            st.markdown("### 📊 Resumo da Operação")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Veículos", len(df))
            c2.metric(
                "Custo Total (Compra)",
                f"R$ {df['Custo_Original'].sum():,.0f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
            )
            c3.metric(
                "Venda Total (Receita)",
                f"R$ {df['Preco_Venda'].sum():,.0f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
            )
            c4.metric(
                "Lucro Estimado R3R",
                f"R$ {df['Margem_R3R'].sum():,.0f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
                delta="Caixa",
            )

            st.divider()

            # --- TABELA DETALHADA ---
            st.subheader("📋 Tabela de Precificação")

            # Configuração visual das colunas
            st.dataframe(
                df[
                    [
                        "Placa",
                        "Modelo",
                        "Fipe",
                        "Custo_Original",
                        "Preco_Venda",
                        "Margem_R3R",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Custo_Original": st.column_config.NumberColumn(
                        "🔴 Custo (Você Paga)", format="R$ %.2f"
                    ),
                    "Preco_Venda": st.column_config.NumberColumn(
                        "🟢 Venda (Você Cobra)", format="R$ %.2f"
                    ),
                    "Margem_R3R": st.column_config.NumberColumn(
                        "💰 Sua Margem", format="R$ %.2f"
                    ),
                    "Fipe": st.column_config.NumberColumn("Fipe", format="R$ %.2f"),
                },
            )

            # --- EXPORTAÇÃO EXCEL ---
            st.divider()

            # Fallback para coluna 'Ano' se não existir no df original
            if "Ano" not in df.columns:
                df["Ano"] = "-"

            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                # Prepara DataFrame para Exportação (Nomes amigáveis)
                df_export = df[
                    [
                        "Modelo",
                        "Placa",
                        "KM",
                        "Ano",
                        "Fipe",
                        "Custo_Original",
                        "Preco_Venda",
                        "Margem_R3R",
                    ]
                ]
                df_export.columns = [
                    "MODELO",
                    "PLACA",
                    "KM",
                    "ANO",
                    "FIPE",
                    "CUSTO COMPRA",
                    "PREÇO VENDA R3R",
                    "LUCRO R3R",
                ]

                df_export.to_excel(writer, index=False, sheet_name="Oportunidades R3R")

                # Ajuste de largura das colunas
                worksheet = writer.sheets["Oportunidades R3R"]
                format_money = writer.book.add_format({"num_format": "R$ #,##0.00"})

                worksheet.set_column("A:B", 25)  # Modelo/Placa
                worksheet.set_column("E:H", 18, format_money)  # Colunas de Dinheiro

            processed_data = output.getvalue()

            st.download_button(
                label="📥 BAIXAR PLANILHA FORMATADA (EXCEL)",
                data=processed_data,
                file_name="Lista_R3R_Oficial.xlsx",
                mime="application/vnd.ms-excel",
            )
        else:
            st.error("Erro na leitura. Verifique o PDF.")
