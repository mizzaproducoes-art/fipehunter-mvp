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
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        div[data-testid="stMetric"] { background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px; color: white; }
        div.stDownloadButton > button { width: 100%; background-color: #00C853; color: white; font-weight: bold; padding: 15px; border-radius: 8px; }
    </style>
""",
    unsafe_allow_html=True,
)


# --- MOTOR DE LEITURA BLINDADO (V3.0) ---
def parse_money(value_str):
    if not value_str:
        return None
    clean = re.sub(r"[^\d,]", "", str(value_str))
    if not clean:
        return None
    try:
        val = (
            float(clean.replace(".", "").replace(",", "."))
            if "," in clean
            else float(clean.replace(".", ""))
        )
        return val if val > 2000 else None
    except:
        return None


def clean_model(text):
    text = str(text).upper().replace("\n", " ")
    remove = [
        "VCPBR",
        "VCPER",
        "OFERTA",
        "DISPONIVEL",
        "FLEX",
        "GASOLINA",
        "ALCOOL",
        "AUTOMATICO",
        "MANUAL",
        "C/AR",
        "4P",
        "2P",
    ]
    clean = re.sub(r"R\$\s?[\d\.,]+", "", text)
    words = clean.split()
    final = [w for w in words if w not in remove and len(w) > 2 and not w.isdigit()]
    return " ".join(final[:6])


def extract_cars_alphaville(row):
    """Lógica 'Explosão de Linha' para tabelas mescladas"""
    extracted = []

    # Coluna 0: Placas (Pode ter mais de uma)
    raw_placas = str(row[0])
    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", raw_placas)

    if not placas:
        return []

    # Colunas de Dados (Tenta pegar texto, se não existir usa vazio)
    # Ajuste: No PDF Alphaville, a coluna de preços costuma ser a de índice 5 ou 6
    # Vamos procurar a coluna que tem "R$"
    idx_price = -1
    for i, col in enumerate(row):
        if col and "R$" in str(col):
            idx_price = i
            break

    if idx_price == -1:
        return []  # Não achou dinheiro na linha

    raw_prices = str(row[idx_price])
    raw_models = str(row[1]) if len(row) > 1 else ""

    # Divide o bloco de texto de preços por quebra de linha
    price_chunks = [x for x in re.split(r"\n+", raw_prices) if len(x) > 5]
    model_chunks = [x for x in re.split(r"\n+", raw_models) if len(x) > 3]

    # Sincronização
    for i, placa in enumerate(placas):
        car = {"Placa": placa}

        # Modelo
        try:
            raw_m = model_chunks[i] if i < len(model_chunks) else model_chunks[-1]
        except:
            raw_m = "Modelo N/D"
        car["Modelo"] = clean_model(raw_m)

        # Preços (Fipe vs Custo)
        # Pega o chunk correspondente ou o texto todo se falhar
        search_text = price_chunks[i] if i < len(price_chunks) else raw_prices

        # Extrai todos os valores monetários do trecho
        vals = sorted(
            [
                parse_money(m)
                for m in re.findall(r"R\$\s?[\d\.,]+", search_text)
                if parse_money(m)
            ],
            reverse=True,
        )

        # Lógica: Maior = Fipe, Segundo Maior = Custo (Orçamento)
        if len(vals) >= 2:
            car["Fipe"] = vals[0]
            car["Custo_Original"] = vals[1]

            # Filtro de segurança (Custo > 5k)
            if car["Custo_Original"] > 5000:
                extracted.append(car)

    return extracted


def process_pdf(file):
    data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Ignora cabeçalho
                    if row and row[0] and "LOJA" not in str(row[0]):
                        cars = extract_cars_alphaville(row)
                        data.extend(cars)
    return data


# --- FRONTEND ---
with st.sidebar:
    st.header("Margem R3R")
    margem = st.number_input("Adicionar R$:", value=2000.0, step=100.0)

st.title("🏢 R3R Admin System")
st.write("Importador de Listas Alphaville/Localiza")

uploaded_file = st.file_uploader("Arraste o PDF aqui", type="pdf")

if uploaded_file:
    with st.spinner("Lendo Tabela Complexa..."):
        raw_data = process_pdf(uploaded_file)
        df = pd.DataFrame(raw_data)

        if not df.empty:
            # Cálculos B2B
            df["Preco_Venda"] = df["Custo_Original"] + margem
            df["Lucro_R3R"] = df["Preco_Venda"] - df["Custo_Original"]

            # Dashboard
            c1, c2, c3 = st.columns(3)
            c1.metric("Veículos Lidos", len(df))
            c2.metric("Total Investimento", f"R$ {df['Custo_Original'].sum():,.0f}")
            c3.metric("Lucro Projetado", f"R$ {df['Lucro_R3R'].sum():,.0f}")

            st.divider()

            # Tabela
            st.dataframe(
                df[["Placa", "Modelo", "Fipe", "Custo_Original", "Preco_Venda"]],
                use_container_width=True,
                column_config={
                    "Custo_Original": st.column_config.NumberColumn(
                        "🔴 Custo Compra", format="R$ %.2f"
                    ),
                    "Preco_Venda": st.column_config.NumberColumn(
                        "🟢 Preço Venda", format="R$ %.2f"
                    ),
                    "Fipe": st.column_config.NumberColumn("Fipe", format="R$ %.2f"),
                },
            )

            # Exportar Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            st.download_button(
                "📥 Baixar Excel Formatado", output.getvalue(), "Lista_R3R.xlsx"
            )

        else:
            st.error(
                "Não encontrei carros. O PDF pode ser imagem ou o layout mudou drasticamente."
            )
