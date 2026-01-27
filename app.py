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
    """Converte valores monetários para float, tratando formatos como 'R$ 6 2.095,00'"""
    try:
        # Remove tudo exceto dígitos e vírgula, incluindo espaços
        c = re.sub(r"[^\d,]", "", str(v).replace(" ", ""))
        if not c:
            return None
        return (
            float(c.replace(".", "").replace(",", "."))
            if "," in c
            else float(c.replace(".", ""))
        )
    except Exception:
        return None


def extract_cars(row):
    """
    Extrai carros da linha usando layout de 16 colunas ALPHAVILLE:
    0: PLACA, 1: LOJA, 2: MODELO, 3: ANO FAB, 4: ANO MOD, 5: KM, 6: COR,
    7: FIPE, 8: MARGEM (R$), 9: PREÇO CLIENTE (=Repasse), 10: ORÇAMENTO,
    11: ENDEREÇO, 12: BAIRRO, 13: CIDADE, 14: ESTADO, 15: LAUDO
    """
    cars = []

    # Verifica se tem colunas suficientes
    if len(row) < 10:
        return []

    # Verifica se tem modelo (coluna essencial)
    if not row[2] or "MODELO" in str(row[2]).upper():
        return []  # Pula cabeçalho ou linha vazia

    # Dados da linha (podem ter múltiplos carros separados por \n)
    modelos = str(row[2]).split("\n") if row[2] else []
    fipes_txt = str(row[7]).split("\n") if row[7] else []
    # Usa PREÇO CLIENTE (col 9) como Repasse - é onde está o valor de custo neste PDF
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
        raw_m = modelos[i] if i < len(modelos) else (modelos[-1] if modelos else "")
        # Limpa Modelo
        ignore = [
            "VCPBR",
            "VCPER",
            "FLEX",
            "AUTOMATICO",
            "MANUAL",
            "C/AR",
            "4P",
            "2P",
        ] + MARCAS
        m_words = [w for w in raw_m.split() if w.upper() not in ignore and len(w) > 2]
        car["Modelo"] = " ".join(m_words[:5])

        # Marca - detecta no texto bruto do modelo
        car["Marca"] = "OUTROS"
        for m in MARCAS:
            if m in raw_m.upper():
                car["Marca"] = m
                break

        # FIPE
        fipe_raw = (
            fipes_txt[i] if i < len(fipes_txt) else (fipes_txt[-1] if fipes_txt else "")
        )
        fipe_val = parse_money(fipe_raw)

        # Repasse/Custo - usa PREÇO CLIENTE (coluna 9)
        preco_raw = (
            precos_txt[i]
            if i < len(precos_txt)
            else (precos_txt[-1] if precos_txt else "")
        )
        preco_val = parse_money(preco_raw)

        if fipe_val and preco_val and preco_val > 5000:
            car["Fipe"] = fipe_val
            car["Repasse"] = preco_val
            cars.append(car)

    return cars


def process(file, debug=False):
    data = []
    debug_info = []
    with pdfplumber.open(file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table_num, table in enumerate(tables):
                if debug and table:
                    # Mostra estrutura da tabela para debug
                    debug_info.append(
                        {
                            "page": page_num + 1,
                            "table": table_num + 1,
                            "num_cols": len(table[0]) if table else 0,
                            "first_rows": table[:3] if len(table) >= 3 else table,
                        }
                    )
                for row in table:
                    # Verifica se a linha tem dados válidos (MODELO na coluna 2)
                    if (
                        row
                        and len(row) > 2
                        and row[2]
                        and "LOJA" not in str(row[0] or "")
                    ):
                        data.extend(extract_cars(row))
    return data, debug_info if debug else (data, [])


# --- APP ---
st.sidebar.header("Filtros")
f_marca = st.sidebar.multiselect("Marca", MARCAS)
f_invest = st.sidebar.number_input("Max Investimento", step=5000)
debug_mode = st.sidebar.checkbox("🔧 Modo Debug")

st.title("🎯 FipeHunter Pro")
up = st.file_uploader("PDF Alphaville", type="pdf")

if up:
    with st.spinner("Analisando..."):
        data, debug_info = process(up, debug=debug_mode)
        df = pd.DataFrame(data)

        # Mostra debug se ativado
        if debug_mode and debug_info:
            st.subheader("🔍 Estrutura do PDF (Debug)")
            for info in debug_info[:3]:  # Primeiras 3 tabelas
                st.write(
                    f"**Página {info['page']}, Tabela {info['table']}** - {info['num_cols']} colunas"
                )
                for i, row in enumerate(info["first_rows"]):
                    st.code(f"Linha {i}: {row}", language="python")
            st.divider()

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
            st.warning("Sem dados. Ative o Modo Debug para ver a estrutura do PDF.")
