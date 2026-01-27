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


# --- LOGIN ---
def check_password():
    if st.session_state.get("auth", False):
        return True
    pwd = st.text_input("Senha de Acesso", type="password")
    if st.button("Entrar"):
        if pwd == "FIPE2026":
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Senha Incorreta")
    return False


if not check_password():
    st.stop()


# --- MOTOR DE LEITURA (V3.0 - IGUAL AO ADMIN) ---
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
    extracted = []
    raw_placas = str(row[0])
    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", raw_placas)

    if not placas:
        return []

    idx_price = -1
    for i, col in enumerate(row):
        if col and "R$" in str(col):
            idx_price = i
            break

    if idx_price == -1:
        return []

    raw_prices = str(row[idx_price])
    raw_models = str(row[1]) if len(row) > 1 else ""

    price_chunks = [x for x in re.split(r"\n+", raw_prices) if len(x) > 5]
    model_chunks = [x for x in re.split(r"\n+", raw_models) if len(x) > 3]

    for i, placa in enumerate(placas):
        car = {"Placa": placa}

        try:
            raw_m = model_chunks[i] if i < len(model_chunks) else model_chunks[-1]
        except:
            raw_m = "Modelo N/D"
        car["Modelo"] = clean_model(raw_m)

        # Extrai Marca do Modelo
        car["Marca"] = "OUTROS"
        for m in [
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
        ]:
            if m in car["Modelo"]:
                car["Marca"] = m
                break

        search_text = price_chunks[i] if i < len(price_chunks) else raw_prices
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
                extracted.append(car)
    return extracted


def process_pdf(file):
    data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and row[0] and "LOJA" not in str(row[0]):
                        data.extend(extract_cars_alphaville(row))
    return data


# --- APP ---
st.sidebar.header("Filtros de Caça")
f_marca = st.sidebar.multiselect(
    "Montadoras",
    [
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
    ],
)
f_invest = st.sidebar.number_input("Max Investimento (R$)", step=5000.0)

st.title("🎯 FipeHunter Pro")

uploaded_file = st.file_uploader("Arraste o PDF aqui", type="pdf")

if uploaded_file:
    with st.spinner("Analisando Oportunidades..."):
        raw_data = process_pdf(uploaded_file)
        df = pd.DataFrame(raw_data)

        if not df.empty:
            df["Lucro"] = df["Fipe"] - df["Repasse"]
            df["Margem"] = (df["Lucro"] / df["Fipe"]) * 100

            # Filtros
            if f_marca:
                df = df[df["Marca"].isin(f_marca)]
            if f_invest > 0:
                df = df[df["Repasse"] <= f_invest]

            # Ordena por Lucro
            df = df.sort_values(by="Lucro", ascending=False)

            st.success(f"{len(df)} Oportunidades Encontradas!")

            # Top 3
            cols = st.columns(3)
            for i in range(min(3, len(df))):
                row = df.iloc[i]
                cols[i].metric(
                    label=row["Modelo"],
                    value=f"Lucro: R$ {row['Lucro']:,.0f}",
                    delta=f"{row['Margem']:.1f}%",
                )
                cols[i].markdown(f"**Paga:** R$ {row['Repasse']:,.0f}")
                cols[i].markdown(f"Fipe: R$ {row['Fipe']:,.0f}")

            st.divider()
            st.dataframe(
                df[["Marca", "Modelo", "Repasse", "Fipe", "Lucro", "Margem"]],
                use_container_width=True,
            )

        else:
            st.warning("Nenhum carro encontrado. Verifique se o PDF está correto.")
