import streamlit as st
import pandas as pd
import re
import pdfplumber
import io

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="FipeHunter Pro", layout="wide", page_icon="🎯")
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

# --- FILTROS PRÉ-CARREGADOS ---
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
CORES = ["BRANCO", "PRETO", "PRATA", "CINZA", "VERMELHO", "AZUL", "BEGE", "VERDE"]
ANOS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]


# --- LOGIN ---
def check_password():
    if st.session_state.get("auth", False):
        return True
    st.markdown("### 🔒 Acesso Restrito - FipeHunter")
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

# --- MOTOR DE LEITURA MATRIX (V4.0 - 15 COLUNAS) ---


def parse_money(value_str):
    if not value_str or pd.isna(value_str):
        return 0.0
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
    data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 10:
                        continue

                    placa = clean_text(row[0])
                    if placa == "PLACA" or not placa or len(placa) < 7:
                        continue

                    # Mapping v4.0 Matrix:
                    # 0: Placa, 2: Modelo, 3: Ano Fab, 4: Ano Mod, 5: KM, 6: Cor, 7: Fipe, 9: Repasse
                    modelo = clean_text(row[2])
                    ano_fab = clean_text(row[3])
                    ano_mod = (
                        int(clean_text(row[4])) if clean_text(row[4]).isdigit() else 0
                    )
                    km_raw = clean_text(row[5])
                    cor = clean_text(row[6])
                    fipe = parse_money(row[7])
                    repasse = parse_money(row[9])

                    # KM Clean
                    try:
                        km = int(re.sub(r"\D", "", km_raw))
                    except:
                        km = 0

                    # Extrai Marca para filtros
                    marca_det = "OUTROS"
                    for m in MARCAS:
                        if m in modelo:
                            marca_det = m
                            break

                    if fipe > 0 and repasse > 0:
                        data.append(
                            {
                                "Marca": marca_det,
                                "Modelo": modelo,
                                "Ano": ano_mod,
                                "Cor": cor,
                                "Placa": placa,
                                "KM": km,
                                "Fipe": fipe,
                                "Repasse": repasse,
                            }
                        )
    return data


# --- FRONTEND ---
st.sidebar.header("🔍 Filtros de Caça")
sel_marcas = st.sidebar.multiselect("Montadora:", MARCAS)
sel_anos = st.sidebar.multiselect("Ano Modelo:", ANOS)
max_val = st.sidebar.number_input("💰 Máx. Investimento (R$):", step=5000)
txt_busca = st.sidebar.text_input("🔍 Buscar Modelo (ex: Corolla):")

st.title("🎯 FipeHunter Pro")
st.caption("Motor Matrix v4.0 (15 Colunas)")

uploaded = st.file_uploader("Arraste o PDF Alphaville aqui", type="pdf")

if uploaded:
    with st.spinner("Decodificando Colunas Matrix..."):
        raw = process_pdf_v4(uploaded)
        df = pd.DataFrame(raw)

        if not df.empty:
            final = []
            for _, r in df.iterrows():
                lucro = r["Fipe"] - r["Repasse"]
                margem = (lucro / r["Fipe"] * 100) if r["Fipe"] > 0 else 0

                # Filtros
                ok = True
                if sel_marcas and r["Marca"] not in sel_marcas:
                    ok = False
                if sel_anos and r["Ano"] not in sel_anos:
                    ok = False
                if max_val > 0 and r["Repasse"] > max_val:
                    ok = False
                if txt_busca and txt_busca.upper() not in r["Modelo"].upper():
                    ok = False

                if ok and lucro > 0:
                    r["Lucro"] = lucro
                    r["Margem"] = margem
                    final.append(r)

            df_final = pd.DataFrame(final).sort_values(by="Lucro", ascending=False)

            if not df_final.empty:
                st.success(f"{len(df_final)} veículos encontrados!")

                # Top 10 Oportunidades
                st.subheader("🔥 Top 10 Melhores Oportunidades")
                for start_idx in range(0, 10, 5):
                    cols = st.columns(5)
                    for j in range(5):
                        idx = start_idx + j
                        if idx < len(df_final):
                            r = df_final.iloc[idx]
                            with cols[j]:
                                st.metric(
                                    label=f"{r['Modelo'][:25]}...",
                                    value=f"R$ {r['Lucro']:,.0f}",
                                    delta=f"{r['Margem']:.1f}%",
                                )
                                st.caption(f"**Custo:** R$ {r['Repasse']:,.0f}")
                                st.caption(f"{r['Ano']} | {r['Placa']}")
                                st.divider()

                # Tabela
                st.divider()
                st.dataframe(
                    df_final[
                        [
                            "Marca",
                            "Modelo",
                            "Ano",
                            "Cor",
                            "Repasse",
                            "Fipe",
                            "Lucro",
                            "Margem",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

                # Exportação
                st.divider()
                c_ex1, c_ex2 = st.columns(2)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df_final.to_excel(writer, index=False, sheet_name="Oportunidades")

                c_ex1.download_button(
                    "📥 Exportar Excel", output.getvalue(), "fipehunter_matrix_v4.xlsx"
                )
                c_ex2.download_button(
                    "📄 Exportar CSV",
                    df_final.to_csv(index=False).encode("utf-8"),
                    "fipehunter_matrix_v4.csv",
                )

            else:
                st.warning("Nenhum carro passou nos filtros.")
        else:
            st.error(
                "Nenhum veículo detectado. Verifique se o PDF segue o padrão de 15 colunas."
            )
else:
    st.info("👈 Configure os filtros e suba o PDF Alphaville.")
