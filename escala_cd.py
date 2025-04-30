import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime, timedelta, date

# Função para conectar ao Google Sheets usando credenciais dos secrets
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()
    return gspread.service_account(filename=temp_file.name)

# Gera a escala de plantão atualizada para os próximos 30 dias
def atualizar_escala_proximos_30_dias():
    try:
        df_escala, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except:
        df_escala = pd.DataFrame(columns=["data", "dia da semana", "turno", "nome", "crm", "status"])
        ws_escala = gc.open(NOME_PLANILHA_ESCALA).sheet1

    df_fixos, _ = carregar_planilha(NOME_PLANILHA_FIXOS)
    hoje = datetime.today().date()
    dias_novos = []

    dias_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    turnos = ["manhã", "tarde", "noite"]
    qtd_plantonistas = {
        "manhã":   {"SEGUNDA": 9, "TERÇA": 9, "QUARTA": 9, "QUINTA": 9, "SEXTA": 9, "SÁBADO": 8, "DOMINGO": 8},
        "tarde":   {"SEGUNDA": 9, "TERÇA": 9, "QUARTA": 9, "QUINTA": 9, "SEXTA": 9, "SÁBADO": 8, "DOMINGO": 8},
        "noite":   {"SEGUNDA": 8, "TERÇA": 8, "QUARTA": 8, "QUINTA": 8, "SEXTA": 8, "SÁBADO": 8, "DOMINGO": 8},
    }

    for i in range(1, 31):
        data = hoje + timedelta(days=i)
        dia_nome = dias_semana[data.weekday()]
        data_str = data.strftime("%d/%m/%Y")

        for turno in turnos:
            existe = ((df_escala["data"] == data_str) & (df_escala["turno"] == turno) & (df_escala["dia da semana"] == dia_nome)).any()
            if existe:
                continue

            fixos_sel = df_fixos[(df_fixos["Dia da Semana"].str.upper() == dia_nome.upper()) & (df_fixos["Turno"].str.lower() == turno)]
            nomes = list(fixos_sel["Nome"])
            crms = list(fixos_sel["CRM"])

            total = qtd_plantonistas[turno][dia_nome.upper()]
            add_cinderela = False
            if turno == "noite":
                if dia_nome.upper() in ["TERÇA", "QUARTA", "QUINTA", "SEXTA", "SÁBADO"]:
                    add_cinderela = True
                    total = 7
                elif dia_nome.upper() == "DOMINGO":
                    add_cinderela = False
                    total = 8

            while len(nomes) < total:
                nomes.append("VAGA")
                crms.append("")

            if add_cinderela:
                nomes.append("CINDERELA")
                crms.append("")

            for nome, crm in zip(nomes, crms):
                status = "fixo" if nome not in ["VAGA", "CINDERELA"] else "livre"
                dias_novos.append({
                    "data": data_str,
                    "dia da semana": dia_nome.lower(),
                    "turno": turno,
                    "nome": nome,
                    "crm": crm,
                    "status": status
                })

    if dias_novos:
        df_novos = pd.DataFrame(dias_novos)
        df_escala = pd.concat([df_escala, df_novos], ignore_index=True)
        df_escala = df_escala.drop_duplicates(subset=["data", "turno", "nome", "crm"], keep="first")
        salvar_planilha(df_escala, ws_escala)

# Nome das planilhas
NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_USUARIOS = 'usuarios'
NOME_PLANILHA_FIXOS = 'Plantonistas_Fixos_Completo_real'

# Conectar
gc = conectar_gspread()

# Funções auxiliares
def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

# Login
st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

autenticado = False
nome_usuario = ""

# Dados de usuários
df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
df_usuarios["crm"] = df_usuarios["crm"].apply(lambda x: str(int(float(x)))).str.strip()
df_usuarios["senha"] = df_usuarios["senha"].apply(lambda x: str(int(float(x)))).str.strip()
crm_input_str = str(crm_input).strip()
senha_input_str = str(senha_input).strip()

user_row = df_usuarios[df_usuarios["crm"] == crm_input_str]

if not user_row.empty:
    senha_correta = user_row["senha"].values[0]
    nome_usuario = user_row["nome"].values[0]
    if senha_input_str == senha_correta:
        st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
        autenticado = True
    else:
        st.sidebar.error("Senha incorreta.")
else:
    st.sidebar.error("Contate o chefe da escala para realizar o cadastro.")

# App principal
st.title("Escala de Plantão")

if autenticado:
    df, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.date
    df["turno"] = df["turno"].str.lower()

    data_plantoa = st.date_input("Selecione a data do plantão")
    turno = st.selectbox("Selecione o turno", ["manhã", "tarde", "noite", "cinderela"])

    st.markdown(f"**Data selecionada:** {data_plantoa.strftime('%d/%m/%Y')} - **Turno:** {turno.capitalize()}")

    df_turno = df[(df["data"] == data_plantoa) & (df["turno"] == turno)]
    df_usuario_turno = df_turno[df_turno["nome"].fillna("").astype(str).str.lower().str.strip() == nome_usuario.lower().strip()]

    if df_turno.empty:
        st.warning("Nenhum plantonista encontrado para essa data e turno.")
    else:
        for idx, row in df_turno.iterrows():
            nome = row["nome"] if pd.notna(row["nome"]) and row["nome"] != "" else "Vaga livre"
            status = row["status"].strip().lower() if pd.notna(row["status"]) else "livre"

            col1, col2 = st.columns([3, 1])
            with col1:
                if status == "repasse":
                    st.warning(f"**{nome}** está repassando o plantão.")
                elif status == "livre" or nome.strip().lower() == "vaga livre":
                    st.error("**Vaga disponível**")
                else:
                    st.success(f"**{nome}** está escalado como `{status}`")

            with col2:
                ja_escalado = not df_usuario_turno.empty

                if (status == "livre" or nome.strip().lower() == "vaga livre") and not ja_escalado:
                    if st.button("Pegar vaga", key=f"pegar_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, ws_escala)
                        st.success("Você pegou a vaga com sucesso! Atualize a página para ver a mudança.")

                elif status == "repasse" and not ja_escalado:
                    if st.button("Assumir", key=f"assumir_{idx}"):
                        df.at[idx, "nome"] = nome_usuario
                        df.at[idx, "status"] = "extra"
                        salvar_planilha(df, ws_escala)
                        st.success("Você assumiu o plantão com sucesso! Atualize a página para ver a mudança.")

                elif nome_usuario.strip().lower() in nome.strip().lower() and status != "repasse":
                    if st.button("Repassar", key=f"repassar_{idx}"):
                        df.at[idx, "status"] = "repasse"
                        salvar_planilha(df, ws_escala)
                        st.warning("Você colocou seu plantão para repasse. Atualize a página para ver a mudança.")

                elif nome_usuario.strip().lower() in nome.strip().lower() and status == "repasse":
                    if st.button("Cancelar repasse", key=f"cancelar_{idx}"):
                        df.at[idx, "status"] = "fixo"
                        salvar_planilha(df, ws_escala)
                        st.success("Você reassumiu o plantão. Atualize a página para ver a mudança.")

    # Função administrativa
    if nome_usuario.lower().startswith("thiago"):
        st.markdown("---")
        if st.button("Regenerar Escala de Plantão para os próximos 30 dias"):
            atualizar_escala_proximos_30_dias()
            st.success("Escala regenerada com sucesso!")
else:
    st.info("Faça login na barra lateral para acessar a escala de plantão.")
