import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

turnos_disponiveis = ["manhã", "tarde", "tardista", "noite", "cinderela"]

def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\n", "\n".replace("\\n", "\n"))
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()
    return gspread.service_account(filename=temp_file.name)

NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_USUARIOS = 'usuarios'

gc = conectar_gspread()

def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

autenticado = False
nome_usuario = ""

try:
    df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar usuários: {e}")
    st.stop()

def tratar_campo(valor):
    try:
        return str(int(float(valor))).strip()
    except:
        return str(valor).strip()

df_usuarios["crm"] = df_usuarios["crm"].apply(tratar_campo)
df_usuarios["senha"] = df_usuarios["senha"].apply(tratar_campo)
crm_input_str = str(crm_input).strip()
senha_input_str = str(senha_input).strip()

user_row = df_usuarios[df_usuarios["crm"] == crm_input_str]

if not user_row.empty:
    senha_correta = user_row["senha"].values[0]
    nome_usuario = user_row["nome"].values[0]
    if senha_input_str == senha_correta:
        if senha_input_str == crm_input_str:
            nova_senha = st.sidebar.text_input("Escolha uma nova senha (apenas números)", type="password")
            if nova_senha:
                if nova_senha.isdigit():
                    df_usuarios.loc[df_usuarios["crm"] == crm_input_str, "senha"] = nova_senha
                    salvar_planilha(df_usuarios, ws_usuarios)
                    st.sidebar.success("Senha atualizada com sucesso. Refaça o login.")
                    st.stop()
                else:
                    st.sidebar.error("A nova senha deve conter apenas números.")
            else:
                st.sidebar.warning("Por favor, escolha uma nova senha para continuar.")
        else:
            st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
            autenticado = True
    else:
        st.sidebar.error("Senha incorreta.")
else:
    st.sidebar.error("Contate o chefe da escala para realizar o cadastro.")

st.title("Escala de Plantão")
st.caption("Versão: 2025-05-16 19h")

if autenticado:
    try:
        df, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except Exception as e:
        st.error(f"Erro ao carregar escala: {e}")
        st.stop()

    df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.date
    df["turno"] = df["turno"].str.lower()

    dias_em_portugues = {
        "Monday": "segunda-feira",
        "Tuesday": "terça-feira",
        "Wednesday": "quarta-feira",
        "Thursday": "quinta-feira",
        "Friday": "sexta-feira",
        "Saturday": "sábado",
        "Sunday": "domingo"
    }

    aba_calendario, aba_mural = st.tabs(["📅 Calendário", "📌 Mural de Vagas"])

    with aba_calendario:
        data_plantoa = st.date_input("Selecione a data do plantão", format="DD/MM/YYYY")
        turno = st.selectbox("Selecione o turno", turnos_disponiveis)

        df_turno = df[(df["data"] == data_plantoa) & (df["turno"] == turno)]
        df_usuario_turno = df_turno[df_turno["nome"].fillna("").astype(str).str.lower().str.strip() == nome_usuario.lower().strip()]

        if df_turno.empty:
            st.warning("Nenhum plantonista encontrado para essa data e turno.")
        else:
            for idx, row in df_turno.iterrows():
                nome = row["nome"] if pd.notna(row["nome"]) and row["nome"] != "" else "Vaga livre"
                status = row["status"].strip().lower() if pd.notna(row["status"]) else "livre"

                funcao_exibida = ""
                if "funcao" in df.columns and pd.notna(row.get("funcao", "")):
                    funcao_exibida = str(row["funcao"]).strip()
                nome_formatado = f"**{nome.strip()}**"
                if funcao_exibida:
                    texto = f"{nome_formatado} <span style='color:red'>({funcao_exibida})</span> está escalado como `{status}`"
                else:
                    texto = f"{nome_formatado} está escalado como `{status}`"

                col1, col2 = st.columns([3, 1])
                with col1:
                    if status == "repasse":
                        st.warning(texto, unsafe_allow_html=True)
                    elif status == "livre" or nome.strip().lower() == "vaga livre":
                        st.error("🚨 Vaga disponível")
                    else:
                        st.success(texto, unsafe_allow_html=True)

                with col2:
                    ja_escalado = not df_usuario_turno.empty
                    if (status == "livre" or nome.strip().lower() == "vaga livre") and not ja_escalado:
                        ja_escalado_mesmo_turno = not df[(df["data"] == data_plantoa) & (df["turno"] == turno) & (df["nome"].str.lower().str.strip() == nome_usuario.lower().strip())].empty
                        if not ja_escalado_mesmo_turno:
                            if st.button("Pegar vaga", key=f"pegar_{idx}"):
                                df.at[idx, "nome"] = nome_usuario
                                df.at[idx, "status"] = "extra"
                                salvar_planilha(df, ws_escala)
                                st.success("Você pegou a vaga com sucesso!")
                                st.rerun()
                        else:
                            st.info("Você já está escalado neste turno.")
                    elif status == "repasse" and not ja_escalado:
                        if st.button("Assumir", key=f"assumir_{idx}"):
                            df.at[idx, "nome"] = nome_usuario
                            df.at[idx, "status"] = "extra"
                            salvar_planilha(df, ws_escala)
                            st.success("Você assumiu o plantão com sucesso!")
                            st.rerun()
                    elif nome_usuario.strip().lower() in nome.strip().lower() and status != "repasse":
                        if st.button("Repassar", key=f"repassar_{idx}"):
                            df.at[idx, "status"] = "repasse"
                            salvar_planilha(df, ws_escala)
                            st.warning("Você colocou seu plantão para repasse.")
                            st.rerun()
                    elif nome_usuario.strip().lower() in nome.strip().lower() and status == "repasse":
                        if st.button("Cancelar repasse", key=f"cancelar_{idx}"):
                            df.at[idx, "status"] = "fixo"
                            salvar_planilha(df, ws_escala)
                            st.success("Você reassumiu o plantão.")
                            st.rerun()

    with aba_mural:
        st.subheader("Mural de Plantões Disponíveis")
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("Data Inicial", value=date.today(), format="DD/MM/YYYY")
        with col2:
            data_fim = st.date_input("Data final", value=date.today(), format="DD/MM/YYYY")

        turno_filtro = st.selectbox("Turno", ["todos"] + turnos_disponiveis)

        df_mural = df[(df["data"] >= data_inicio) & (df["data"] <= data_fim)]
        if turno_filtro != "todos":
            df_mural = df_mural[df_mural["turno"] == turno_filtro.lower()]

        df_vagas = df_mural[
            ((df_mural["nome"].fillna('').str.strip().str.lower() == "vaga livre") |
             (df_mural["status"].fillna('').str.lower() == "livre") |
             (df_mural["status"].fillna('').str.lower() == "repasse"))
        ]

        if df_vagas.empty:
            st.info("Nenhum plantão disponível com os filtros selecionados.")
        else:
            for idx, row in df_vagas.iterrows():
                data_str = row["data"].strftime("%d/%m/%Y")
                turno_str = row["turno"].capitalize()
                nome = row["nome"] if pd.notna(row["nome"]) else "Vaga livre"
                status = row["status"].strip().lower() if pd.notna(row["status"]) else "livre"

                col1, col2 = st.columns([4, 1])
                with col1:
                    if status == "repasse":
                        st.warning(f"📆 {data_str} | {turno_str} — **{nome} está repassando o plantão.**")
                    elif status == "livre" or nome.lower().strip() == "vaga livre":
                        st.error(f"📆 {data_str} | {turno_str} — **Vaga disponível**")
                with col2:
                    ja_escalado = not df[
                        (df["data"] == row["data"]) &
                        (df["turno"] == row["turno"]) &
                        (df["nome"].str.lower().str.strip() == nome_usuario.lower().strip())
                    ].empty
                    if status == "livre" or nome.strip().lower() == "vaga livre":
                        if not ja_escalado:
                            if st.button("Pegar", key=f"pegar_mural_{idx}"):
                                df.at[idx, "nome"] = nome_usuario
                                df.at[idx, "status"] = "extra"
                                salvar_planilha(df, ws_escala)
                                st.success(f"Você pegou a vaga de {data_str} ({turno_str}) com sucesso!")
                                st.rerun()
                    elif status == "repasse":
                        if not ja_escalado:
                            if st.button("Assumir", key=f"assumir_mural_{idx}"):
                                df.at[idx, "nome"] = nome_usuario
                                df.at[idx, "status"] = "extra"
                                salvar_planilha(df, ws_escala)
                                st.success(f"Você assumiu o plantão de {data_str} ({turno_str}) com sucesso!")
                                st.rerun()
else:
    st.info("Faça login na barra lateral para acessar a escala de plantão.")
