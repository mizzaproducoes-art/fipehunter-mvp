import streamlit as st
import pandas as pd
import re
import pdfplumber

st.set_page_config(page_title="FipeHunter v0.9", layout="wide")


# --- 🔒 SISTEMA DE PROTEÇÃO (PASSWORD GATE) ---
def check_password():
    """Retorna True se o usuário digitar a senha correta."""

    # Se já estiver autenticado na sessão, libera direto
    if st.session_state.get("authenticated", False):
        return True

    # Layout da Tela de Bloqueio
    st.markdown("### 🔒 Acesso Restrito - FipeHunter")
    st.markdown("Digite a senha enviada no seu e-mail de compra.")

    password = st.text_input("Senha de Acesso", type="password")

    if st.button("Entrar"):
        if password == "FIPE2026":  # <--- SUA SENHA MESTRA AQUI
            st.session_state["authenticated"] = True
            st.rerun()  # Recarrega a página para liberar o app
        else:
            st.error("Senha incorreta. Verifique seu e-mail ou contate o suporte.")
            return False

    return False


# 2. Bloqueio Real
if not check_password():
    st.stop()  # PARA TUDO AQUI SE A SENHA NÃO FOR VÁLIDA

# --- FUNCOES DE PARSING ESTRITO ---


def parse_money(value_str):
    """
    Converte string para float APENAS se parecer dinheiro (tem R$ ou virgula).
    Retorna None se nao parecer dinheiro, para evitar confusao com KM.
    """
    if not value_str:
        return None
    s = str(value_str).strip()

    # Verifica marcadores de dinheiro
    has_symbol = "R$" in s or "$" in s
    has_comma = "," in s

    # Regra Estrita: Se nao tem R$ nem virgula, nao eh dinheiro (provavelmente eh KM ou Ano)
    if not has_symbol and not has_comma:
        return None

    # Limpeza
    clean = re.sub(r"[^\d,]", "", s)  # Remove tudo que nao for digito ou virgula
    if not clean:
        return None

    # Conversao BR (virgula decimal)
    try:
        if "," in clean:
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(".", "")  # Caso raro de R$ 100000 sem virgula

        val = float(clean)
        return val if val > 2000 else None  # Filtra valores muito baixos (taxas)
    except:
        return None


def parse_km(value_str):
    """
    Converte string para int APENAS se parecer KM (sem R$, sem virgula).
    """
    if not value_str:
        return 0
    s = str(value_str).strip()

    # Se tem cara de dinheiro, rejeita
    if "R$" in s or "," in s:
        return 0

    # Limpa pontos de milhar e caracteres nao numericos
    clean = re.sub(r"[^\d]", "", s)
    try:
        val = int(clean)
        # Filtro de Sanidade KM: Entre 0 e 500.000
        return val if 0 <= val < 500000 else 0
    except:
        return 0


def clean_model_name(text):
    # Remove padroes para limpar o nome do carro
    text = str(text).replace("\n", " ")
    text = re.sub(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", "", text)  # Placa
    text = re.sub(r"R\$\s?[\d\.,]+", "", text)  # Dinheiro explicito

    stopwords = [
        "oferta",
        "disponivel",
        "sp",
        "barueri",
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
    # Pega palavras uteis (tamanho > 2 e nao numericas)
    clean = [
        w
        for w in words
        if w.lower() not in stopwords and len(w) > 2 and not w.isdigit()
    ]
    return " ".join(clean[:6])


# --- DRIVERS DE LEITURA ---


def driver_structured(pdf):
    """
    Para PDFs organizados em tabela (Desmobja, R3R, Alphaville).
    """
    data = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                # Converte linha para texto
                row_str = " ".join([str(c) for c in row if c])

                # Busca Placa (Ancora)
                plate_match = re.search(r"\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b", row_str)
                if not plate_match:
                    continue

                prices = []
                km = 0

                # Analisa celula por celula
                for cell in row:
                    c_str = str(cell).strip()

                    # Tenta extrair Dinheiro
                    m_val = parse_money(c_str)
                    if m_val:
                        prices.append(m_val)

                    # Tenta extrair KM (se nao foi dinheiro)
                    else:
                        k_val = parse_km(c_str)
                        if k_val > km:
                            km = k_val  # Pega o maior inteiro valido como KM

                # Logica de Precos
                prices = sorted(list(set(prices)), reverse=True)
                if len(prices) >= 2:
                    fipe = prices[0]
                    repasse = prices[1]

                    # Logica de IPVA (Se houver 3 valores e o 3o for custo compativel)
                    lucro = fipe - repasse
                    ipva = 0
                    if len(prices) > 2:
                        terceiro = prices[2]
                        # Se o terceiro valor for parecido com o lucro, eh apenas repeticao. Se for diferente, pode ser IPVA.
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
                            "Origem": "Tabela Estruturada",
                        }
                    )
    return data


def driver_unstructured(pdf):
    """
    Para PDFs caoticos (Barueri). Usa Regex no texto corrido.
    """
    text = ""
    for page in pdf.pages:
        text += page.extract_text() + "\n"

    data = []
    # Divide por placas encontrada
    parts = re.split(r"(\b[A-Z]{3}[0-9][A-Z0-9][0-9]{2}\b)", text)

    # Itera em pares (Placa, Conteudo)
    for i in range(1, len(parts) - 1, 2):
        placa = parts[i]
        content = parts[i + 1]

        # Extrai Dinheiro (Busca R$)
        prices_raw = re.findall(r"R\$\s?[\d\.,]+", content)
        prices = []
        for p in prices_raw:
            val = parse_money(p)
            if val:
                prices.append(val)

        prices = sorted(prices, reverse=True)

        # Extrai KM (Busca padrao KM ou numeros soltos)
        km = 0
        km_match = re.search(r"(?:KM|Km)\s?([\d\.]+)", content)
        if km_match:
            km = parse_km(km_match.group(1))

        if len(prices) >= 2:
            fipe = prices[0]
            repasse = prices[1]
            data.append(
                {
                    "Placa": placa,
                    "Modelo": clean_model_name(content),
                    "KM": km,
                    "Fipe": fipe,
                    "Repasse": repasse,
                    "IPVA": 0,
                    "Origem": "Texto Puro",
                }
            )
    return data


def process_file(file):
    # Detecta tipo de arquivo
    with pdfplumber.open(file) as pdf:
        first_page = pdf.pages[0].extract_text()

        # Se parece ter estrutura de grade visual (Alphaville, Desmobja, R3R)
        if (
            "Placa" in first_page
            or "Modelo" in first_page
            or "Desmob" in first_page
            or "R3R" in first_page
        ):
            return driver_structured(pdf)
        else:
            return driver_unstructured(pdf)


# --- INTERFACE ---
st.title("FIPEHUNTER v0.9")
st.markdown("Analise de margem real com distincao estrita de valores.")

uploaded_file = st.file_uploader("Upload do PDF", type="pdf")

if uploaded_file:
    with st.spinner("Processando..."):
        try:
            raw_data = process_file(uploaded_file)

            final_data = []
            for item in raw_data:
                lucro = item["Fipe"] - item["Repasse"] - item["IPVA"]
                if item["Fipe"] > 0:
                    margem = (lucro / item["Fipe"]) * 100
                    # Filtro de Sanidade
                    if 1 < margem < 70:
                        item["Lucro_Real"] = lucro
                        item["Margem_%"] = round(margem, 1)
                        final_data.append(item)

            df = pd.DataFrame(final_data)

            if not df.empty:
                df = df.sort_values(by="Lucro_Real", ascending=False)

                # Exibicao Top 3
                st.divider()
                st.subheader("Melhores Oportunidades")
                cols = st.columns(3)
                for i in range(min(3, len(df))):
                    row = df.iloc[i]
                    val_km = f"{row['KM']:,.0f} km" if row["KM"] > 0 else "KM N/A"
                    cols[i].metric(
                        label=row["Modelo"],
                        value=f"R$ {row['Lucro_Real']:,.2f}",
                        delta=f"{row['Margem_%']}%",
                    )
                    cols[i].caption(f"Placa: {row['Placa']} | {val_km}")

                # Tabela Completa
                st.divider()
                st.subheader("Lista Detalhada")
                st.dataframe(
                    df[
                        [
                            "Modelo",
                            "Placa",
                            "KM",
                            "Fipe",
                            "Repasse",
                            "Lucro_Real",
                            "Margem_%",
                            "Origem",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.error(
                    "Nenhum dado valido encontrado. Verifique se o PDF contem texto selecionavel."
                )

        except Exception as e:
            st.error(f"Erro no processamento: {e}")
