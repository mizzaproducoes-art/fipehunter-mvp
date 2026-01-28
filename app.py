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

# --- MOTOR DE LEITURA BLINDADO (V3.0 - BIDIRECIONAL) ---


def parse_money(value_str):
    if not value_str:
        return None
    clean = re.sub(r"[^\d,]", "", str(value_str))
    if not clean:
        return None
    try:
        if "," in clean:
            val = float(clean.replace(".", "").replace(",", "."))
        else:
            val = float(clean.replace(".", ""))
        return val if val > 2000 else None
    except:
        return None


def clean_info_v3(text):
    text = str(text).upper().replace("\n", " ")
    # Extrai Marca
    marca = "OUTROS"
    for m in MARCAS:
        if m in text:
            marca = m
            break
    # Extrai Cor
    cor = "OUTROS"
    for c in CORES:
        if c in text:
            cor = c
            break

    # Extrai Ano
    anos = re.findall(r"\b(20[1-2][0-9])\b", text)
    ano_fab = anos[0] if len(anos) > 0 else "0"
    ano_mod = int(anos[1]) if len(anos) >= 2 else (int(anos[0]) if anos else 0)

    # Limpa Modelo
    clean = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)
    clean = re.sub(r"R\$\s?[\d\.,]+", "", clean)
    clean = re.sub(r"\b20[1-2][0-9]\b", "", clean)
    words = clean.split()
    ignore = (
        [
            "OFERTA",
            "DISPONIVEL",
            "VCPBR",
            "VCPER",
            "APROVADO",
            "BARUERI",
            "ALPHAVILLE",
            "SP",
            "KM",
            "FIPE",
            "ORCAMENTO",
        ]
        + MARCAS
        + CORES
    )
    modelo = " ".join(
        [w for w in words if w not in ignore and len(w) > 2 and not w.isdigit()][:6]
    )

    return marca, modelo, cor, ano_mod


def process_pdf_v3(file):
    data = []
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"

    if not full_text:
        return []

    plate_pattern = r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b"
    plates_found = list(re.finditer(plate_pattern, full_text))

    for match in plates_found:
        placa = match.group()
        start = match.start()
        end = match.end()

        # Contexto 250 antes, 500 depois
        ctx_start = max(0, start - 250)
        ctx_end = min(len(full_text), end + 500)
        ctx = full_text[ctx_start:ctx_end]

        # Extrai Dinheiro
        prices_raw = re.findall(
            r"R\$\s?[\d\.,]+|(?<=\s)[\d\.]{5,8},[\d]{2}(?=\s|$)|\b\d{2}\.\d{3}\b", ctx
        )
        prices = []
        for p in prices_raw:
            val = parse_money(p)
            if val and val > 10000:
                prices.append(val)

        prices = sorted(list(set(prices)), reverse=True)

        if len(prices) >= 2:
            fipe = prices[0]
            repasse = prices[1]

            marca, modelo, cor, ano = clean_info_v3(ctx)

            # KM
            km = 0
            km_matches = re.findall(r"\b\d{1,3}\.?\d{3}\b", ctx)
            for km_cand in km_matches:
                k_val = int(str(km_cand).replace(".", ""))
                if 1000 < k_val < 300000:
                    km = k_val
                    break

            data.append(
                {
                    "Marca": marca,
                    "Modelo": modelo,
                    "Cor": cor,
                    "Ano": ano,
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
st.caption("Motor Blindado v3.0 (Bidirecional)")

uploaded = st.file_uploader("Arraste o PDF Alphaville aqui", type="pdf")

if uploaded:
    with st.spinner("Analisando Oportunidades com Motor v3.0..."):
        raw = process_pdf_v3(uploaded)
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
                st.success(f"{len(df_final)} oportunidades encontradas!")

                # Top 3
                st.subheader("🔥 Top Oportunidades")
                cols = st.columns(3)
                for i in range(min(3, len(df_final))):
                    r = df_final.iloc[i]
                    cols[i].metric(
                        f"{r['Marca']} {r['Modelo']}",
                        f"Lucro: R$ {r['Lucro']:,.0f}",
                        f"{r['Margem']:.1f}%",
                    )
                    cols[i].markdown(
                        f"**Paga:** R$ {r['Repasse']:,.0f} | **Fipe:** R$ {r['Fipe']:,.0f}"
                    )
                    cols[i].caption(
                        f"{r['Cor']} | {r['Ano']} | {r['Placa']} | {r['KM']}km"
                    )

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
                    "📥 Exportar Excel", output.getvalue(), "fipehunter_v3.xlsx"
                )
                c_ex2.download_button(
                    "📄 Exportar CSV",
                    df_final.to_csv(index=False).encode("utf-8"),
                    "fipehunter_v3.csv",
                )

            else:
                st.warning("Nenhum carro passou nos filtros.")
        else:
            st.error("Nenhum veículo detectado. Verifique o layout do PDF.")
else:
    st.info("👈 Configure os filtros e suba o PDF Alphaville.")
