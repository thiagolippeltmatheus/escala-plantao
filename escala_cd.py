import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

# Função para conectar ao Google Sheets usando credenciais dos secrets
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])

    # Corrigir a chave privada para ter quebras de linha reais
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")

    # Criar arquivo temporário
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()

    # Agora conecta ao gspread
    gc = gspread.service_account(filename=temp_file.name)
    return gc

# Nome das planilhas
NOME_PLANILHA_ESCALA = 'Escala_Maio_2025'
NOME_PLANILHA_USUARIOS = 'usuarios'

# Conectar
gc = conectar_gspread()

# Funções para carregar e salvar dados
def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet

def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)

# Carregar dados de usuários
try:
    df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar usuários: {e}")
    st.stop()

# Login
st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

autenticado = False
nome_usuario = ""

# Forçar CRM e senha para texto correto
# Converte float para int, depois para string (ex: 11384.0 -> "11384")
df_usuarios["crm"] = df_usuarios["crm"].apply(lambda x: str(int(float(x)))).str.strip()
df_usuarios["senha"] = df_usuarios["senha"].apply(lambda x: str(int(float(x)))).str.strip()
crm_input_str = str(crm_input).strip()
senha_input_str = str(senha_input).strip()

# Procurar usuário com CRM igual
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

# App principal
st.title("Escala de Plantão")

if autenticado:
    try:
        df, ws_escala = carregar_planilha(NOME_PLANILHA_ESCALA)
    except Exception as e:
        st.error(f"Erro ao carregar escala: {e}")
        st.stop()

    df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.date
    df["turno"] = df["turno"].str.lower()

    data_plantoa = st.date_input("Selecione a data do plantão")
    turno = st.selectbox("Selecione o turno", ["manhã", "tarde", "noite", "cinderela"])

    
    dia_semana = data_plantoa.strftime("%A")
    dias_em_portugues = {
        "Monday": "segunda-feira",
        "Tuesday": "terça-feira",
        "Wednesday": "quarta-feira",
        "Thursday": "quinta-feira",
        "Friday": "sexta-feira",
        "Saturday": "sábado",
        "Sunday": "domingo"
    }
    dia_semana_pt = dias_em_portugues.get(dia_semana, dia_semana)
    st.markdown(f"**Data selecionada:** {data_plantoa.strftime('%d/%m/%Y')} ({dia_semana_pt}) - **Turno:** {turno.capitalize()}")


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
else:
    st.info("Faça login na barra lateral para acessar a escala de plantão.")
