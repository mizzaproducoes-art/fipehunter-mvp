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
        .top-card { background: linear-gradient(135deg, #1a5f2a 0%, #0d3018 100%); border: 2px solid #2ecc71; border-radius: 12px; padding: 20px; margin: 10px 0; }
        .top-card h3 { color: #2ecc71; margin: 0 0 10px 0; }
        .top-card p { color: white; margin: 5px 0; font-size: 14px; }
        .lucro-destaque { color: #2ecc71; font-size: 24px; font-weight: bold; }
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
LAUDOS = ["APROVADO", "REPROVADO", "PENDENTE", ""]


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


# --- PARSER INTELIGENTE ---
def parse_money(v):
    """Converte valores monetários para float, tratando formatos como 'R$ 6 2.095,00'"""
    try:
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


def parse_km(v):
    """Extrai quilometragem do texto"""
    try:
        km_str = re.sub(r"[^\d]", "", str(v).replace(" ", ""))
        return int(km_str) if km_str else 0
    except Exception:
        return 0


def extract_cars(row):
    """
    Extrai carros da linha usando layout de 16 colunas ALPHAVILLE:
    0: PLACA, 1: LOJA, 2: MODELO, 3: ANO FAB, 4: ANO MOD, 5: KM, 6: COR,
    7: FIPE, 8: MARGEM (R$), 9: PREÇO CLIENTE (=Repasse), 10: ORÇAMENTO,
    11: ENDEREÇO, 12: BAIRRO, 13: CIDADE, 14: ESTADO, 15: LAUDO
    """
    cars = []

    if len(row) < 10:
        return []

    if not row[2] or "MODELO" in str(row[2]).upper():
        return []

    # Dados da linha
    modelos = str(row[2]).split("\n") if row[2] else []
    kms_txt = str(row[5]).split("\n") if len(row) > 5 and row[5] else []
    fipes_txt = str(row[7]).split("\n") if len(row) > 7 and row[7] else []
    precos_txt = str(row[9]).split("\n") if len(row) > 9 and row[9] else []
    laudo_txt = str(row[15]).strip().upper() if len(row) > 15 and row[15] else ""

    placas = re.findall(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", str(row[0])) if row[0] else []
    num_cars = max(len(modelos), 1)

    for i in range(num_cars):
        car = {}

        # Placa
        car["Placa"] = placas[i] if i < len(placas) else f"SEM-{i + 1}"

        # Modelo
        raw_m = modelos[i] if i < len(modelos) else (modelos[-1] if modelos else "")
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

        # Marca
        car["Marca"] = "OUTROS"
        for m in MARCAS:
            if m in raw_m.upper():
                car["Marca"] = m
                break

        # KM
        km_raw = kms_txt[i] if i < len(kms_txt) else (kms_txt[-1] if kms_txt else "0")
        car["KM"] = parse_km(km_raw)

        # Laudo
        car["Laudo"] = laudo_txt if laudo_txt else "N/A"

        # FIPE
        fipe_raw = (
            fipes_txt[i] if i < len(fipes_txt) else (fipes_txt[-1] if fipes_txt else "")
        )
        fipe_val = parse_money(fipe_raw)

        # Repasse/Custo
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


def process(file):
    data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if (
                        row
                        and len(row) > 2
                        and row[2]
                        and "LOJA" not in str(row[0] or "")
                    ):
                        data.extend(extract_cars(row))
    return data


# --- APP ---
st.title("🎯 FipeHunter Pro")

# SIDEBAR - Filtros
st.sidebar.header("🔍 Filtros")
f_marca = st.sidebar.multiselect("Marca", MARCAS)
f_modelo = st.sidebar.text_input("Modelo (busca)")
f_km_max = st.sidebar.number_input("KM Máximo", min_value=0, value=0, step=10000)
f_laudo = st.sidebar.multiselect("Laudo", ["APROVADO", "REPROVADO", "PENDENTE", "N/A"])
f_invest = st.sidebar.number_input(
    "Max Investimento (R$)", min_value=0, value=0, step=5000
)

up = st.file_uploader("📄 Envie o PDF Alphaville", type="pdf")

if up:
    with st.spinner("🔎 Analisando oportunidades..."):
        data = process(up)
        df = pd.DataFrame(data)

        if not df.empty:
            df["Lucro"] = df["Fipe"] - df["Repasse"]
            df["Margem"] = (df["Lucro"] / df["Fipe"]) * 100

            # Aplicar filtros
            df_filtrado = df.copy()
            if f_marca:
                df_filtrado = df_filtrado[df_filtrado["Marca"].isin(f_marca)]
            if f_modelo:
                df_filtrado = df_filtrado[
                    df_filtrado["Modelo"].str.contains(
                        f_modelo.upper(), case=False, na=False
                    )
                ]
            if f_km_max > 0:
                df_filtrado = df_filtrado[df_filtrado["KM"] <= f_km_max]
            if f_laudo:
                df_filtrado = df_filtrado[df_filtrado["Laudo"].isin(f_laudo)]
            if f_invest > 0:
                df_filtrado = df_filtrado[df_filtrado["Repasse"] <= f_invest]

            df_filtrado = df_filtrado[df_filtrado["Lucro"] > 0]

            # ========== TOP 10 OPORTUNIDADES (Margem >= 20%) ==========
            st.subheader("🏆 TOP 10 OPORTUNIDADES (Margem ≥ 20%)")

            top10 = df_filtrado[df_filtrado["Margem"] >= 20].nlargest(10, "Margem")

            if not top10.empty:
                cols = st.columns(2)
                for idx, (_, car) in enumerate(top10.iterrows()):
                    with cols[idx % 2]:
                        st.markdown(
                            f"""
                        <div class="top-card">
                            <h3>#{idx + 1} {car["Modelo"]}</h3>
                            <p><b>Placa:</b> {car["Placa"]} | <b>KM:</b> {car["KM"]:,} | <b>Laudo:</b> {car["Laudo"]}</p>
                            <p><b>FIPE:</b> R$ {car["Fipe"]:,.2f}</p>
                            <p><b>Valor de Compra:</b> R$ {car["Repasse"]:,.2f}</p>
                            <p class="lucro-destaque">💰 LUCRO: R$ {car["Lucro"]:,.2f} ({car["Margem"]:.1f}%)</p>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
            else:
                st.info(
                    "Nenhuma oportunidade com margem ≥ 20% encontrada com os filtros atuais."
                )

            st.divider()

            # ========== TABELA COMPLETA ==========
            st.subheader(f"📋 Todas as Oportunidades ({len(df_filtrado)})")

            # Formatar para exibição
            df_display = df_filtrado[
                [
                    "Placa",
                    "Marca",
                    "Modelo",
                    "KM",
                    "Laudo",
                    "Repasse",
                    "Fipe",
                    "Lucro",
                    "Margem",
                ]
            ].copy()
            df_display = df_display.sort_values("Margem", ascending=False)
            df_display["Margem"] = df_display["Margem"].apply(lambda x: f"{x:.1f}%")
            df_display["Repasse"] = df_display["Repasse"].apply(
                lambda x: f"R$ {x:,.2f}"
            )
            df_display["Fipe"] = df_display["Fipe"].apply(lambda x: f"R$ {x:,.2f}")
            df_display["Lucro"] = df_display["Lucro"].apply(lambda x: f"R$ {x:,.2f}")
            df_display["KM"] = df_display["KM"].apply(lambda x: f"{x:,}")

            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhum dado encontrado no PDF.")
