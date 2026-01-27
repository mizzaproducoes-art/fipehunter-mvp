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

# --- INTELLIGENT PARSER V2.0 (ROW EXPLODER) ---


def parse_money(value_str):
    """Converte valores monetários para float, tratando formatos como 'R$ 6 2.095,00'"""
    if not value_str:
        return None
    # Remove tudo exceto dígitos e vírgula, incluindo espaços
    clean = re.sub(r"[^\d,]", "", str(value_str).replace(" ", ""))
    if not clean:
        return None
    try:
        val = (
            float(clean.replace(".", "").replace(",", "."))
            if "," in clean
            else float(clean.replace(".", ""))
        )
        return val if val > 2000 else None  # Filtra valores de margem pequenos
    except Exception:
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
    clean = re.sub(r"R\$\s?[\d\.,]+", "", text)  # Tira preço
    words = clean.split()
    # Pega as primeiras 5 palavras que não sejam proibidas
    final = [w for w in words if w not in remove and len(w) > 2 and not w.isdigit()]
    return " ".join(final[:6])


def extract_cars_from_row(row):
    """
    Extrai carros da linha usando layout de 16 colunas:
    0: Placa (pode estar vazio), 1: LOJA, 2: MODELO, 3: ANO FAB, 4: ANO MOD,
    5: KM, 6: COR, 7: FIPE, 8: MARGEM, 9: PREÇO CLIENTE (Custo),
    10: Orçamento (alternativo)
    """
    extracted = []

    # Verifica se tem colunas suficientes
    if len(row) < 10:
        return []

    # Verifica se tem modelo (coluna essencial)
    if not row[2] or "MODELO" in str(row[2]).upper():
        return []  # Pula cabeçalho ou linha vazia

    # Dados da linha (podem ter múltiplos carros separados por \n)
    modelos = str(row[2]).split("\n") if row[2] else []
    anos_fab = str(row[3]).split("\n") if row[3] else []
    anos_mod = str(row[4]).split("\n") if row[4] else []
    kms = str(row[5]).split("\n") if row[5] else []
    cores = str(row[6]).split("\n") if row[6] else []
    fipes_txt = str(row[7]).split("\n") if row[7] else []
    # Usa PREÇO CLIENTE (col 9) como custo - é onde está o valor neste PDF
    precos_txt = str(row[9]).split("\n") if row[9] else []

    # Placas são opcionais
    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", str(row[0])) if row[0] else []

    # Número de carros = máximo entre modelos encontrados ou 1
    num_cars = max(len(modelos), 1)

    for i in range(num_cars):
        car = {}

        # Placa (opcional)
        if i < len(placas):
            car["Placa"] = placas[i]
        else:
            car["Placa"] = f"SEM-{i + 1}"

        # Modelo
        raw_model = modelos[i] if i < len(modelos) else (modelos[-1] if modelos else "")
        car["Modelo"] = clean_model(raw_model)

        # Ano
        fab = anos_fab[i] if i < len(anos_fab) else (anos_fab[-1] if anos_fab else "")
        mod = anos_mod[i] if i < len(anos_mod) else (anos_mod[-1] if anos_mod else "")
        car["Ano"] = f"{fab}/{mod}".strip("/")

        # KM
        try:
            k_txt = kms[i] if i < len(kms) else "0"
            car["KM"] = int(re.sub(r"[^\d]", "", k_txt))
        except Exception:
            car["KM"] = 0

        # Cor
        cor_txt = cores[i] if i < len(cores) else (cores[-1] if cores else "OUTROS")
        car["Cor"] = cor_txt.split()[0] if cor_txt else "OUTROS"

        # FIPE
        fipe_raw = (
            fipes_txt[i] if i < len(fipes_txt) else (fipes_txt[-1] if fipes_txt else "")
        )
        fipe_val = parse_money(fipe_raw)

        # Custo Original - usa PREÇO CLIENTE (coluna 9)
        preco_raw = (
            precos_txt[i]
            if i < len(precos_txt)
            else (precos_txt[-1] if precos_txt else "")
        )
        preco_val = parse_money(preco_raw)

        if fipe_val and preco_val and preco_val > 5000:
            car["Fipe"] = fipe_val
            car["Custo_Original"] = preco_val
            extracted.append(car)

    return extracted


def process_pdf(file):
    final_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Extrai tabela (ajuda a separar as linhas visuais)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    # Verifica se a linha tem dados válidos (MODELO na coluna 2)
                    if (
                        not row
                        or len(row) < 3
                        or not row[2]
                        or "LOJA" in str(row[0] or "")
                    ):
                        continue

                    # Processa a linha (pode gerar 1 ou + carros)
                    cars = extract_cars_from_row(row)
                    final_data.extend(cars)
    return final_data


# --- APP ---
with st.sidebar:
    st.title("🏢 R3R Admin")
    margem = st.number_input("Margem Fixa (R$):", value=2000.0, step=100.0)

st.title("Importador Alphaville Oficial 🚀")
st.caption("Leitura de Células Mescladas Ativada")

up = st.file_uploader("PDF Alphaville (Novo)", type="pdf")

if up:
    with st.spinner("Processando..."):
        data = process_pdf(up)
        df = pd.DataFrame(data)

        if not df.empty:
            df["Venda"] = df["Custo_Original"] + margem
            df["Lucro"] = df["Venda"] - df["Custo_Original"]

            c1, c2 = st.columns(2)
            c1.metric("Veículos", len(df))
            c2.metric("Lucro Total", f"R$ {df['Lucro'].sum():,.0f}")

            st.dataframe(df, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            st.download_button("Baixar Excel", output.getvalue(), "Lista.xlsx")
        else:
            st.error(
                "Nenhum carro identificado. O PDF pode estar como imagem ou layout muito diferente."
            )
