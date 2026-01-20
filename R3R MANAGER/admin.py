import streamlit as st
import pandas as pd
import re
import pdfplumber
from io import BytesIO

# --- CONFIGURAÇÃO B2B ---
st.set_page_config(page_title="R3R Admin System", layout="wide", page_icon="🏢")


# --- PARSERS BLINDADOS (Mesmo motor do v1.0) ---
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
    ]
    words = text.split()
    clean = [
        w
        for w in words
        if w.lower() not in stopwords and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(clean[:6])


# --- LÓGICA DE EXTRAÇÃO (Motor v1.0) ---
def driver_structured(pdf):
    data = []
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
                    if not plate_match:
                        continue

                    prices = []
                    km = 0
                    for cell in row:
                        c_str = str(cell).strip()
                        m_val = parse_money(c_str)
                        if m_val:
                            prices.append(m_val)
                        else:
                            k_val = parse_km(c_str)
                            if k_val > km:
                                km = k_val

                    prices = sorted(list(set(prices)), reverse=True)
                    if len(prices) >= 2:
                        fipe = prices[0]
                        repasse = prices[1]
                        data.append(
                            {
                                "Placa": plate_match.group(),
                                "Modelo": clean_model_name(row_str),
                                "KM": km,
                                "Fipe": fipe,
                                "Custo_Original": repasse,
                            }
                        )
    except:
        pass
    return data


def driver_universal(pdf):
    data = []
    try:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
        parts = re.split(r"(\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b)", text)
        for i in range(1, len(parts) - 1, 2):
            placa = parts[i]
            content = parts[i + 1]
            prices_raw = re.findall(r"R\$\s?[\d\.,]+", content)
            prices = sorted(
                [p for p in [parse_money(pr) for pr in prices_raw] if p], reverse=True
            )
            km = 0
            km_match = re.search(r"(?:KM|Km)\s?([\d\.]+)", content)
            if km_match:
                km = parse_km(km_match.group(1))

            if len(prices) >= 2:
                data.append(
                    {
                        "Placa": placa,
                        "Modelo": clean_model_name(content),
                        "KM": km,
                        "Fipe": prices[0],
                        "Custo_Original": prices[1],
                    }
                )
    except:
        pass
    return data


def process_file(file):
    with pdfplumber.open(file) as pdf:
        first_page = pdf.pages[0].extract_text() or ""
        if (
            "Placa" in first_page
            or "Modelo" in first_page
            or "Desmob" in first_page
            or "R3R" in first_page
        ):
            return driver_structured(pdf)
        else:
            return driver_universal(pdf)


# --- FRONTEND EXCLUSIVO B2B ---
st.sidebar.title("🏢 R3R Admin")
st.sidebar.info("Ferramenta Interna de Precificação")

# INPUTS DE MARGEM
st.sidebar.header("1. Configurar Margem")
tipo_margem = st.sidebar.radio(
    "Tipo de Acréscimo:", ["Valor Fixo (R$)", "Porcentagem (%)"]
)

if tipo_margem == "Valor Fixo (R$)":
    valor_extra = st.sidebar.number_input("Adicionar R$:", value=2000.0, step=100.0)
else:
    pct_extra = st.sidebar.number_input("Adicionar %:", value=5.0, step=0.5)

st.title("Gerador de Listas R3R 🚀")
st.markdown("Transforme listas bagunçadas em planilhas limpas com sua margem aplicada.")

uploaded_file = st.file_uploader(
    "Subir PDF da Fonte (Localiza, Alphaville, etc)", type="pdf"
)

if uploaded_file:
    with st.spinner("Processando e padronizando..."):
        data = process_file(uploaded_file)

        if data:
            df = pd.DataFrame(data)

            # --- CÁLCULO DA NOVA TABELA ---
            if tipo_margem == "Valor Fixo (R$)":
                df["Preco_Venda_R3R"] = df["Custo_Original"] + valor_extra
            else:
                df["Preco_Venda_R3R"] = df["Custo_Original"] * (1 + pct_extra / 100)

            # Formatação Fipe
            df["Margem_R3R_Estimada"] = df["Preco_Venda_R3R"] - df["Custo_Original"]
            df["Distancia_Fipe"] = df["Fipe"] - df["Preco_Venda_R3R"]

            # Ordenar
            df = df.sort_values(by="Preco_Venda_R3R", ascending=True)

            # --- VISUALIZAÇÃO ---
            st.success(f"{len(df)} veículos processados com sucesso!")

            st.dataframe(
                df[
                    [
                        "Placa",
                        "Modelo",
                        "KM",
                        "Fipe",
                        "Custo_Original",
                        "Preco_Venda_R3R",
                    ]
                ],
                use_container_width=True,
                column_config={
                    "Custo_Original": st.column_config.NumberColumn(
                        "Custo (Fonte)", format="R$ %.2f"
                    ),
                    "Preco_Venda_R3R": st.column_config.NumberColumn(
                        "✅ Preço Final R3R", format="R$ %.2f"
                    ),
                    "Fipe": st.column_config.NumberColumn("Fipe", format="R$ %.2f"),
                },
            )

            # --- EXPORTAÇÃO (O Ouro) ---
            def to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Lista R3R")
                return output.getvalue()

            excel_data = to_excel(
                df[["Modelo", "Placa", "KM", "Fipe", "Preco_Venda_R3R"]]
            )

            st.download_button(
                label="📥 Baixar Excel Formatado (Pronto para Grupo)",
                data=excel_data,
                file_name="Lista_R3R_Formatada.xlsx",
                mime="application/vnd.ms-excel",
                type="primary",
            )
        else:
            st.error("Não foi possível ler o arquivo. Verifique se é um PDF válido.")
