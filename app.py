import streamlit as st
import pandas as pd
import re
import pdfplumber

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="FipeHunter Pro", layout="wide", page_icon="🎯")
st.markdown(
    """
    <style>
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        div[data-testid="stMetric"] { background-color: #1E1E1E; border: 1px solid #333; padding: 15px; border-radius: 10px; color: white; }
    </style>
""",
    unsafe_allow_html=True,
)

# --- FILTROS ---
MARCAS = [
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
]
CORES = ["BRANCO", "PRETO", "PRATA", "CINZA", "VERMELHO", "AZUL", "BEGE"]
ANOS = [2026, 2025, 2024, 2023, 2022, 2021, 2020]


# --- LOGIN ---
def check_password():
    if st.session_state.get("auth", False):
        return True
    pwd = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if pwd == "FIPE2026":
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Senha Errada")
    return False


if not check_password():
    st.stop()


# --- PARSER INTELIGENTE (MESMA LÓGICA DO B2B) ---
def parse_money(v):
    try:
        c = re.sub(r"[^\d,]", "", str(v))
        return (
            float(c.replace(".", "").replace(",", "."))
            if "," in c
            else float(c.replace(".", ""))
        )
    except:
        return None


def extract_cars(row):
    cars = []
    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", str(row[0]))
    if not placas:
        return []

    # Textos Base
    txt_mod = str(row[1]).split("\n") if len(row) > 1 else []
    txt_prc = str(row[5])  # Coluna Preço

    # Quebra de Preços/Chunk
    # Tenta quebrar por linha, mas limpa linhas vazias
    chunks = [x for x in re.split(r"\n+", txt_prc) if len(x) > 3]

    for i, placa in enumerate(placas):
        car = {"Placa": placa}

        # Modelo
        raw_m = txt_mod[i] if i < len(txt_mod) else (txt_mod[-1] if txt_mod else "")
        # Limpa Modelo
        ignore = ["VCPBR", "FLEX", "AUTOMATICO", "MANUAL"] + MARCAS
        m_words = [w for w in raw_m.split() if w.upper() not in ignore and len(w) > 2]
        car["Modelo"] = " ".join(m_words[:5])

        # Marca
        car["Marca"] = "OUTROS"
        for m in MARCAS:
            if m in car["Modelo"].upper():
                car["Marca"] = m
                break

        # Tenta achar preços no chunk
        # Se tiver menos chunks que carros, usa o texto todo
        search_text = chunks[i] if i < len(chunks) else txt_prc

        vals = sorted(
            [
                parse_money(m)
                for m in re.findall(r"R\$\s?[\d\.,]+", search_text)
                if parse_money(m)
            ],
            reverse=True,
        )

        if len(vals) >= 2:
            car["Fipe"] = vals[0]
            car["Repasse"] = vals[1]
            if car["Repasse"] > 5000:
                cars.append(car)

    return cars


def process(file):
    data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and row[0] and "LOJA" not in str(row[0]):
                        data.extend(extract_cars(row))
    return data


# --- APP ---
st.sidebar.header("Filtros")
f_marca = st.sidebar.multiselect("Marca", MARCAS)
f_invest = st.sidebar.number_input("Max Investimento", step=5000)

st.title("🎯 FipeHunter Pro")
up = st.file_uploader("PDF Alphaville", type="pdf")

if up:
    with st.spinner("Analisando..."):
        data = process(up)
        df = pd.DataFrame(data)

        if not df.empty:
            df["Lucro"] = df["Fipe"] - df["Repasse"]
            df["Margem"] = (df["Lucro"] / df["Fipe"]) * 100

            # Filtros
            if f_marca:
                df = df[df["Marca"].isin(f_marca)]
            if f_invest > 0:
                df = df[df["Repasse"] <= f_invest]
            df = df[df["Lucro"] > 0]

            st.success(f"{len(df)} Oportunidades!")
            st.dataframe(
                df[["Marca", "Modelo", "Repasse", "Fipe", "Lucro", "Margem"]],
                use_container_width=True,
            )
        else:
            st.warning("Sem dados.")
