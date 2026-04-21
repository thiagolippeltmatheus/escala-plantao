import unicodedata
import streamlit as st
import pandas as pd
import gspread
import json
import tempfile
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

turnos_disponiveis = ["manhã", "tarde", "noite", "cinderela"]


# Funções principais
def conectar_gspread():
    credenciais_info = json.loads(st.secrets["CREDENCIAIS_JSON"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")
    temp_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json")
    json.dump(credenciais_info, temp_file)
    temp_file.flush()
    temp_file.close()
    return gspread.service_account(filename=temp_file.name)


@st.cache_data(ttl=60)
def carregar_planilha(nome_planilha):
    sh = gc.open(nome_planilha)
    worksheet = sh.sheet1
    df = get_as_dataframe(worksheet).dropna(how="all")
    return df, worksheet


def salvar_planilha(df, worksheet):
    worksheet.clear()
    set_with_dataframe(worksheet, df)


def get_escala_em_tempo_real(nome_planilha):
    try:
        sh = gc.open(nome_planilha)
        worksheet = sh.sheet1
        df = get_as_dataframe(worksheet).dropna(how="all")
        return df, worksheet
    except Exception:
        st.error("⚠️ Estamos com muitos acessos neste momento. Por favor, tente novamente em 1 a 2 minutos.")
        st.stop()


def tratar_campo(valor):
    try:
        if pd.isna(valor):
            return ""
        return str(int(float(valor))).strip()
    except Exception:
        return str(valor).strip()


def garantir_colunas_escala(df):
    colunas_necessarias = [
        "data", "turno", "nome", "status", "crm",
        "crm original", "repassado por", "funcao"
    ]

    for col in colunas_necessarias:
        if col not in df.columns:
            df[col] = ""

    # Forçar colunas sensíveis para object para evitar erro com string[pyarrow]
    df["crm"] = df["crm"].astype(object)
    df["crm original"] = df["crm original"].astype(object)
    df["nome"] = df["nome"].astype(object)
    df["status"] = df["status"].astype(object)
    df["repassado por"] = df["repassado por"].astype(object)
    df["funcao"] = df["funcao"].astype(object)

    # Padronizações
    df["crm"] = df["crm"].apply(tratar_campo)
    df["crm original"] = df["crm original"].apply(tratar_campo)
    df["nome"] = df["nome"].fillna("").astype(str).str.strip()
    df["status"] = df["status"].fillna("").astype(str).str.strip().str.lower()
    df["turno"] = df["turno"].fillna("").astype(str).str.strip().str.lower()
    df["repassado por"] = df["repassado por"].fillna("").astype(str).str.strip()
    df["funcao"] = df["funcao"].fillna("").astype(str).str.strip()

    return df


def mostrar_notificacoes(nome_usuario, df):
    crm_usuario = tratar_campo(df_usuarios[df_usuarios["nome"] == nome_usuario]["crm"].values[0])

    df_notif = df.copy()
    df_notif["crm original"] = df_notif["crm original"].apply(tratar_campo)

    df_notif = df_notif[df_notif["crm original"] == crm_usuario].copy()

    df_notif["data"] = pd.to_datetime(df_notif["data"], errors="coerce").dt.date
    df_notif = df_notif[df_notif["data"].notna()]
    hoje = date.today()
    df_notif = df_notif[df_notif["data"] >= hoje]

    if df_notif.empty:
        st.info("Você não possui notificações.")
    else:
        st.subheader("🔔 Suas notificações:")
        for _, row in df_notif.iterrows():
            data_str = row["data"].strftime("%d/%m/%Y")
            turno_str = str(row["turno"]).capitalize()
            quem_pegou = row["nome"]
            st.markdown(f"- {quem_pegou} pegou seu plantão do dia {data_str} turno {turno_str}")


# Nomes das planilhas
NOME_PLANILHA_ESCALA = "Escala_Maio_2025"
NOME_PLANILHA_USUARIOS = "usuarios"

# Conecta e carrega planilhas
gc = conectar_gspread()

try:
    df_usuarios, ws_usuarios = carregar_planilha(NOME_PLANILHA_USUARIOS)
except Exception as e:
    st.error(f"Erro ao carregar usuários: {e}")
    st.stop()

if "crm" not in df_usuarios.columns:
    df_usuarios["crm"] = ""
if "senha" not in df_usuarios.columns:
    df_usuarios["senha"] = ""
if "nome" not in df_usuarios.columns:
    df_usuarios["nome"] = ""

df_usuarios["crm"] = df_usuarios["crm"].apply(tratar_campo)
df_usuarios["senha"] = df_usuarios["senha"].apply(tratar_campo)
df_usuarios["nome"] = df_usuarios["nome"].fillna("").astype(str).str.strip()

# Estado de sessão
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "nome_usuario" not in st.session_state:
    st.session_state.nome_usuario = ""
if "modo_nova_senha" not in st.session_state:
    st.session_state.modo_nova_senha = False

# Sidebar Login
st.sidebar.header("Login")
crm_input = st.sidebar.text_input("CRM")
senha_input = st.sidebar.text_input("Senha", type="password")

# Botão de login
if st.sidebar.button("Entrar"):
    crm_input_str = tratar_campo(crm_input)
    senha_input_str = tratar_campo(senha_input)

    user_row = df_usuarios[df_usuarios["crm"] == crm_input_str]
    if not user_row.empty:
        senha_correta = user_row["senha"].values[0]
        nome_usuario = user_row["nome"].values[0]

        if senha_input_str == senha_correta:
            if senha_input_str == crm_input_str:
                st.session_state.modo_nova_senha = True
            else:
                st.session_state.autenticado = True
                st.session_state.nome_usuario = nome_usuario
                st.sidebar.success(f"Bem-vindo, {nome_usuario}!")
                st.rerun()
        else:
            st.sidebar.error("Senha incorreta.")
    else:
        st.sidebar.error("Contate o chefe da escala para realizar o cadastro.")

# Troca de senha
if st.session_state.modo_nova_senha:
    nova_senha = st.sidebar.text_input("Escolha uma nova senha (apenas números)", type="password")
    if nova_senha:
        if nova_senha.isdigit():
            df_usuarios.loc[df_usuarios["crm"] == tratar_campo(crm_input), "senha"] = nova_senha
            try:
                gc_local = conectar_gspread()
                sh_usuarios = gc_local.open(NOME_PLANILHA_USUARIOS)
                ws_usuarios_atual = sh_usuarios.sheet1
                salvar_planilha(df_usuarios, ws_usuarios_atual)
                st.sidebar.success("Senha atualizada com sucesso. Refaça o login.")
                st.session_state.modo_nova_senha = False
                st.session_state.autenticado = False
                st.stop()
            except Exception as e:
                st.sidebar.error(f"Erro ao salvar nova senha: {e}")
                st.stop()
        else:
            st.sidebar.error("A nova senha deve conter apenas números.")

# Definir variáveis
autenticado = st.session_state.autenticado
nome_usuario = st.session_state.nome_usuario

st.title("Escala de Plantão")

if autenticado:
    try:
        df, ws_escala = get_escala_em_tempo_real(NOME_PLANILHA_ESCALA)
    except Exception as e:
        st.error(f"Erro ao carregar escala: {e}")
        st.stop()

    df = garantir_colunas_escala(df)
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.date

    aba_calendario, aba_mural, aba_meus_plantoes, aba_notificacoes = st.tabs(
        ["📅 Calendário", "📌 Mural de Vagas", "🗓️ Meus Plantões", "🔔 Notificações"]
    )

    with aba_notificacoes:
        mostrar_notificacoes(nome_usuario, df)

    with aba_calendario:
        data_plantoa = st.date_input("Selecione a data do plantão", format="DD/MM/YYYY")
        turno = st.selectbox("Selecione o turno", turnos_disponiveis)

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

        st.markdown(
            f"**Data selecionada:** {data_plantoa.strftime('%d/%m/%Y')} "
            f"({dia_semana_pt}) - **Turno:** {turno.capitalize()}"
        )

        df_turno = df[(df["data"] == data_plantoa) & (df["turno"] == turno)].copy()
        df_usuario_turno = df_turno[
            df_turno["nome"].fillna("").astype(str).str.lower().str.strip() == nome_usuario.lower().strip()
        ]

        if df_turno.empty:
            st.warning("Nenhum plantonista encontrado para essa data e turno.")
        else:
            for idx, row in df_turno.iterrows():
                nome_base = row["nome"] if pd.notna(row["nome"]) and row["nome"] != "" else "Vaga livre"
                funcao = row.get("funcao", "")
                nome = f"{nome_base} ({funcao})" if pd.notna(funcao) and str(funcao).strip() else nome_base
                status = str(row["status"]).strip().lower() if pd.notna(row["status"]) else "livre"

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
                        ja_escalado_mesmo_turno = not df[
                            (df["data"] == data_plantoa) &
                            (df["turno"] == turno) &
                            (df["nome"].str.lower().str.strip() == nome_usuario.lower().strip())
                        ].empty

                        if not ja_escalado_mesmo_turno:
                            if st.button("Pegar vaga", key=f"pegar_{idx}"):
                                df.at[idx, "nome"] = nome_usuario
                                df.at[idx, "status"] = "extra"
                                df.at[idx, "crm"] = tratar_campo(
                                    df_usuarios[df_usuarios["nome"] == nome_usuario]["crm"].values[0]
                                )
                                salvar_planilha(df, ws_escala)
                                st.success("Você pegou a vaga com sucesso!")
                                st.rerun()
                        else:
                            st.info("Você já está escalado neste turno.")

                    elif status == "repasse" and not ja_escalado:
                        if st.button("Assumir", key=f"assumir_{idx}"):
                            df.at[idx, "repassado por"] = str(df.at[idx, "nome"]).strip()
                            df.at[idx, "crm original"] = str(tratar_campo(df.at[idx, "crm"]))
                            df.at[idx, "nome"] = nome_usuario
                            df.at[idx, "crm"] = str(
                                tratar_campo(df_usuarios[df_usuarios["nome"] == nome_usuario]["crm"].values[0])
                            )
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
        st.subheader("🔍 Mural de Vagas e Repasses")

        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("De", value=date.today(), format="DD/MM/YYYY")
        with col2:
            data_fim = st.date_input("Até", value=date.today(), format="DD/MM/YYYY")

        turno_filtro = st.selectbox("Turno", ["todos"] + turnos_disponiveis)
        dias_semana_filtro = st.multiselect(
            "Dia da semana",
            options=[
                "segunda-feira", "terça-feira", "quarta-feira",
                "quinta-feira", "sexta-feira", "sábado", "domingo"
            ],
            default=[]
        )

        df_mural = df.copy()
        df_mural["dia_semana"] = pd.to_datetime(df_mural["data"]).dt.strftime("%A").map({
            "Monday": "segunda-feira",
            "Tuesday": "terça-feira",
            "Wednesday": "quarta-feira",
            "Thursday": "quinta-feira",
            "Friday": "sexta-feira",
            "Saturday": "sábado",
            "Sunday": "domingo"
        })

        df_mural = df_mural[(df_mural["data"] >= data_inicio) & (df_mural["data"] <= data_fim)]

        if turno_filtro != "todos":
            df_mural = df_mural[df_mural["turno"] == turno_filtro.lower()]

        if dias_semana_filtro:
            df_mural = df_mural[df_mural["dia_semana"].isin(dias_semana_filtro)]

        df_vagas_repasses = df_mural[
            ((df_mural["nome"].fillna("").str.strip().str.lower() == "vaga livre") |
             (df_mural["status"].fillna("").str.lower() == "livre") |
             (df_mural["status"].fillna("").str.lower() == "repasse"))
        ].copy()

        if df_vagas_repasses.empty:
            st.info("Nenhum plantão disponível ou em repasse com os filtros selecionados.")
        else:
            for idx, row in df_vagas_repasses.iterrows():
                data_str = row["data"].strftime("%d/%m/%Y")
                turno_str = row["turno"].capitalize()
                dia_semana_str = row["data"].strftime("%A")

                dias_em_portugues = {
                    "Monday": "segunda-feira",
                    "Tuesday": "terça-feira",
                    "Wednesday": "quarta-feira",
                    "Thursday": "quinta-feira",
                    "Friday": "sexta-feira",
                    "Saturday": "sábado",
                    "Sunday": "domingo"
                }

                dia_semana_pt = dias_em_portugues.get(dia_semana_str, dia_semana_str)
                nome_base = row["nome"] if pd.notna(row["nome"]) and row["nome"] != "" else "Vaga livre"
                funcao = row.get("funcao", "")
                nome = f"{nome_base} ({funcao})" if pd.notna(funcao) and str(funcao).strip() else nome_base
                status = row["status"].strip().lower() if pd.notna(row["status"]) else "livre"

                col1, col2 = st.columns([4, 1])

                with col1:
                    if status == "repasse":
                        st.warning(f"📆 {data_str} ({dia_semana_pt}) | {turno_str} — **{nome} está repassando o plantão.**")
                    elif status == "livre" or nome.lower().strip() == "vaga livre":
                        st.error(f"📆 {data_str} ({dia_semana_pt}) | {turno_str} — **Vaga disponível**")
                    else:
                        st.success(f"📆 {data_str} ({dia_semana_pt}) | {turno_str} — **{nome} está escalado como `{status}`**")

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
                                df.at[idx, "crm"] = tratar_campo(
                                    df_usuarios[df_usuarios["nome"] == nome_usuario]["crm"].values[0]
                                )
                                salvar_planilha(df, ws_escala)
                                st.success(f"Você pegou a vaga de {data_str} ({turno_str}) com sucesso!")
                                st.rerun()

                    elif status == "repasse":
                        if not ja_escalado:
                            if st.button("Assumir", key=f"assumir_mural_{idx}"):
                                df.at[idx, "repassado por"] = str(df.at[idx, "nome"]).strip()
                                df.at[idx, "crm original"] = str(tratar_campo(df.at[idx, "crm"]))
                                df.at[idx, "nome"] = nome_usuario
                                df.at[idx, "crm"] = str(
                                    tratar_campo(df_usuarios[df_usuarios["nome"] == nome_usuario]["crm"].values[0])
                                )
                                df.at[idx, "status"] = "extra"
                                salvar_planilha(df, ws_escala)
                                st.success(f"Você assumiu o plantão de {data_str} ({turno_str}) com sucesso!")
                                st.rerun()

    with aba_meus_plantoes:
        st.subheader("🗓️ Plantões do Usuário")

        df_usuario = df[
            df["nome"].str.lower().str.strip() == nome_usuario.lower().strip()
        ].copy()

        if df_usuario.empty:
            st.info("Você não possui plantões cadastrados.")
        else:
            df_usuario["mes"] = pd.to_datetime(df_usuario["data"]).dt.to_period("M").astype(str)

            meses_disponiveis = sorted(df_usuario["mes"].dropna().unique(), reverse=True)

            if not meses_disponiveis:
                st.info("Você não possui plantões neste mês.")
            else:
                meses_traduzidos = {
                    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
                    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
                    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro"
                }

                meses_formatados = [
                    f"{meses_traduzidos[m.split('-')[1]]}/{m.split('-')[0]}"
                    for m in meses_disponiveis
                ]

                mes_formatado = st.selectbox("Filtrar por mês", meses_formatados)
                mes_selecionado = meses_disponiveis[meses_formatados.index(mes_formatado)]

                df_filtrado = df_usuario[df_usuario["mes"] == mes_selecionado].sort_values("data")

                if df_filtrado.empty:
                    st.info("Você não possui plantões neste mês.")
                else:
                    dias_em_portugues = {
                        "Monday": "segunda-feira",
                        "Tuesday": "terça-feira",
                        "Wednesday": "quarta-feira",
                        "Thursday": "quinta-feira",
                        "Friday": "sexta-feira",
                        "Saturday": "sábado",
                        "Sunday": "domingo"
                    }

                    for _, row in df_filtrado.iterrows():
                        dia_semana_en = row["data"].strftime("%A")
                        dia_semana_pt = dias_em_portugues.get(dia_semana_en, dia_semana_en)
                        data_str = row["data"].strftime("%d/%m/%Y")
                        turno_str = row["turno"].capitalize()
                        status_str = row["status"] if pd.notna(row["status"]) else "sem status"
                        st.markdown(f"- 📆 **{data_str} ({dia_semana_pt})** — 🕒 **{turno_str}** — 🏷️ *{status_str}*")

else:
    st.info("Faça login na barra lateral para acessar a escala de plantão (seta no canto superior esquerdo).")
