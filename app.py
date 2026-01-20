import streamlit as st
import pandas as pd
import re
import pdfplumber

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FipeHunter Pro", layout="wide", page_icon="🎯")


# --- 2. SISTEMA DE SEGURANÇA (PASSWORD GATE) ---
def check_password():
    """Bloqueia o app até digitar a senha correta."""
    if st.session_state.get("authenticated", False):
        return True

    st.markdown("### 🔒 Acesso Restrito - FipeHunter")
    st.markdown("Digite a senha enviada no seu e-mail de compra.")

    password = st.text_input("Senha de Acesso", type="password")

    if st.button("Entrar"):
        if password == "FIPE2026":  # <--- SUA SENHA MESTRA
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
            return False
    return False


if not check_password():
    st.stop()

# --- 3. INTELIGÊNCIA DE DADOS (PARSERS) ---


def parse_money(value_str):
    """Converte string para dinheiro. Exige R$ ou vírgula para não confundir com KM."""
    if not value_str:
        return None
    s = str(value_str).strip()

    # Se não tem cara de dinheiro (sem R$ e sem vírgula), ignora
    if "R$" not in s and "," not in s:
        return None

    clean = re.sub(r"[^\d,]", "", s)  # Remove letras e pontos de milhar
    if not clean:
        return None

    try:
        # Padrão BR: 1.000,00 -> remove ponto, troca virgula por ponto
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(".", "")
        val = float(clean)
        return val if val > 2000 else None  # Filtra taxas pequenas
    except Exception:
        return None


def parse_km(value_str):
    """Converte string para KM. Exige que NÃO tenha R$ ou vírgula."""
    if not value_str:
        return 0
    s = str(value_str).strip()
    if "R$" in s or "," in s:
        return 0  # Se tem R$, é dinheiro, não KM

    clean = re.sub(r"[^\d]", "", s)  # Mantém só números
    try:
        val = int(clean)
        return val if 0 <= val < 400000 else 0  # Filtro de sanidade KM
    except Exception:
        return 0


def clean_model_name(text):
    text = str(text).replace("\n", " ").replace('"', "").replace("'", "")
    # Remove Placa
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)
    # Remove Preços
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
    # Pega palavras úteis
    clean = [
        w
        for w in words
        if w.lower() not in stopwords and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(clean[:6])


# --- 4. DRIVERS DE LEITURA (CAMADAS DE DEFESA) ---


def driver_structured(pdf):
    """CAMADA 1: Tenta ler tabelas organizadas (R3R, Alphaville, Desmobja)."""
    data = []
    try:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    # Converte linha para texto
                    row_str = " ".join([str(c) for c in row if c])

                    # Procura Placa
                    plate_match = re.search(
                        r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", row_str
                    )
                    if not plate_match:
                        continue

                    prices = []
                    km = 0

                    for cell in row:
                        c_str = str(cell).strip()
                        # Tenta ler Dinheiro
                        m_val = parse_money(c_str)
                        if m_val:
                            prices.append(m_val)
                        else:
                            # Se não for dinheiro, tenta ler KM
                            k_val = parse_km(c_str)
                            if k_val > km:
                                km = k_val

                    prices = sorted(list(set(prices)), reverse=True)

                    if len(prices) >= 2:
                        fipe = prices[0]
                        repasse = prices[1]

                        # Logica de IPVA (Se tiver 3 valores e o 3º for custo)
                        lucro = fipe - repasse
                        ipva = 0
                        if len(prices) > 2:
                            terceiro = prices[2]
                            if 1000 < terceiro < 15000 and abs(terceiro - lucro) > 100:
                                ipva = terceiro

                        data.append(
                            {
                                "Placa": plate_match.group(),
                                "Modelo": clean_model_name(row_str),
                                "KM": km,
                                "Fipe": fipe,
                                "Repasse": repasse,
                                "IPVA": ipva,
                                "Origem": "Tabela",
                            }
                        )
    except:
        pass
    return data


def driver_universal_fallback(pdf):
    """CAMADA 2 (MacGyver): Lê texto bruto. (Mauá, Barueri)."""
    data = []
    try:
        text = ""
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

        # Divide o texto pelas Placas encontradas
        parts = re.split(r"(\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b)", text)

        # Itera: [Lixo, PLACA, Conteudo, PLACA, Conteudo...]
        for i in range(1, len(parts) - 1, 2):
            placa = parts[i]
            content = parts[i + 1]  # Texto logo após a placa

            # Acha todos os preços no texto do carro
            prices_raw = re.findall(r"R\$\s?[\d\.,]+", content)
            prices = sorted(
                [p for p in [parse_money(pr) for pr in prices_raw] if p], reverse=True
            )

            # Acha KM (procura por "KM" ou numeros soltos grandes)
            km = 0
            km_match = re.search(r"(?:KM|Km)\s?([\d\.]+)", content)
            if km_match:
                km = parse_km(km_match.group(1))
            else:
                # Tenta achar numero solto grande (ex: 71024 no arquivo Maua)
                # Regex procura numero de 4 a 6 digitos isolado
                loose_num = re.search(r"\b(\d{4,6})\b", content)
                if loose_num:
                    k_cand = int(loose_num.group(1))
                    if 0 < k_cand < 300000:
                        km = k_cand

            if len(prices) >= 2:
                data.append(
                    {
                        "Placa": placa,
                        "Modelo": clean_model_name(content),
                        "KM": km,
                        "Fipe": prices[0],
                        "Repasse": prices[1],
                        "IPVA": 0,
                        "Origem": "Universal/Texto",
                    }
                )
    except:
        pass
    return data


def process_file_bulletproof(file):
    """CAMADA 3 (Gerente): Tenta estratégias em ordem."""
    with pdfplumber.open(file) as pdf:
        # Checagem 0: O PDF é imagem?
        first_page_text = pdf.pages[0].extract_text()
        if not first_page_text or len(first_page_text) < 10:
            return [], "IMAGE_ERROR"

        # Estratégia A: Tentar Estruturado (Tabela - Preferencial para R3R/Alphaville)
        results = driver_structured(pdf)
        if len(results) > 0:
            return results, "OK"

        # Estratégia B: Se não achou nada em tabela, tenta Universal Fallback (Maua/Barueri)
        results = driver_universal_fallback(pdf)
        if len(results) > 0:
            return results, "OK"

    return [], "NO_MATCH"


# --- 5. FRONTEND COM FILTROS ---

# Barra Lateral
with st.sidebar:
    st.header("🔍 Filtros Avançados")
    st.caption("Filtre o que cabe no seu bolso.")

    max_invest = st.number_input(
        "💰 Valor Máximo de Compra (R$):", min_value=0.0, value=0.0, step=10000.0
    )
    st.caption("Deixe 0,00 para ver todos")

    target_km = st.slider("🚗 KM Máxima aceitável:", 0, 200000, 150000, step=10000)

    min_margin = st.slider("📈 Margem Mínima (%):", 0, 50, 10)

    st.divider()
    st.caption("v1.1 Pro | Atualizado em: 20/01/2026")

st.title("🎯 FipeHunter Pro")
st.markdown("### Inteligência de Mercado para Repasses")

uploaded_file = st.file_uploader(
    "Arraste seu PDF (R3R, Alphaville, Mauá, Barueri...)", type="pdf"
)

if uploaded_file:
    with st.spinner("Processando inteligência de dados..."):
        try:
            # Chama o processador blindado
            raw_data, status = process_file_bulletproof(uploaded_file)

            # Tratamento de Erros Amigável
            if status == "IMAGE_ERROR":
                st.error("⚠️ Não conseguimos ler o texto deste PDF.")
                st.info(
                    "Dica: Parece que este arquivo é uma imagem escaneada. O sistema precisa de PDFs com texto selecionável."
                )
                st.stop()

            if not raw_data:
                st.warning("⚠️ Nenhum carro encontrado.")
                st.info(
                    "O sistema tentou ler mas não encontrou padrões claros. Verifique se o arquivo está correto."
                )
                st.stop()

            # Processamento de Dados (Se chegou aqui, temos carros!)
            final_data = []
            for item in raw_data:
                lucro = item["Fipe"] - item["Repasse"] - item["IPVA"]

                if item["Fipe"] > 0:
                    margem = (lucro / item["Fipe"]) * 100

                    # Filtros do Usuário
                    pass_invest = (
                        True if max_invest == 0 else (item["Repasse"] <= max_invest)
                    )
                    pass_km = True if item["KM"] <= target_km else False
                    pass_margin = True if margem >= min_margin else False

                    # Filtro de Segurança (Margem entre 1% e 70%)
                    if pass_invest and pass_km and pass_margin and (1 < margem < 70):
                        item["Lucro_Real"] = lucro
                        item["Margem_%"] = round(margem, 1)
                        final_data.append(item)

            df = pd.DataFrame(final_data)

            if not df.empty:
                df = df.sort_values(by="Lucro_Real", ascending=False)

                st.success(f"Análise concluída: {len(df)} veículos encontrados.")

                # --- TOP 3 OPORTUNIDADES ---
                st.divider()
                st.subheader("🔥 Top 3 Oportunidades")
                cols = st.columns(3)

                for i in range(min(3, len(df))):
                    row = df.iloc[i]
                    val_km = f"{row['KM']:,.0f} km" if row["KM"] > 0 else "KM N/A"

                    cols[i].metric(
                        label=row["Modelo"],
                        value=f"Lucro: R$ {row['Lucro_Real']:,.0f}",
                        delta=f"{row['Margem_%']}% Margem",
                    )
                    cols[i].markdown(f"💸 **Paga:** R$ {row['Repasse']:,.0f}")
                    cols[i].caption(f"Fipe: R$ {row['Fipe']:,.0f} | {val_km}")
                    cols[i].markdown(f"`{row['Placa']}`")

                # --- TABELA DETALHADA ---
                st.divider()
                st.subheader("📋 Lista Completa")
                st.dataframe(
                    df[
                        [
                            "Modelo",
                            "Placa",
                            "Repasse",
                            "Fipe",
                            "KM",
                            "Lucro_Real",
                            "Margem_%",
                            "Origem",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Repasse": st.column_config.NumberColumn(
                            "Valor Compra", format="R$ %.2f"
                        ),
                        "Fipe": st.column_config.NumberColumn("Fipe", format="R$ %.2f"),
                        "Lucro_Real": st.column_config.NumberColumn(
                            "Lucro Líquido", format="R$ %.2f"
                        ),
                        "KM": st.column_config.NumberColumn("KM", format="%d km"),
                    },
                )
            else:
                st.warning(
                    "Carros foram encontrados, mas nenhum passou nos seus filtros de Investimento/KM/Margem."
                )

        except Exception as e:
            st.error("Ocorreu um erro inesperado na leitura.")
            with st.expander("Ver detalhes técnicos (para suporte)"):
                st.code(e)
