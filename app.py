"""Interface V5 Streamlit pour le moteur V4, sans Colab."""
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import modele_financier_V4 as moteur

st.set_page_config(page_title="Financial Intelligence | V5", page_icon="📈", layout="wide")
st.title("📈 Financial Intelligence")
st.caption("S&P 500 | Prototype éducatif • Cours Yahoo Finance possiblement différés • Aucun conseil d'investissement")

DOSSIER = Path("modele_v4_cache")
F_EXPORT = DOSSIER / "classement_web.csv"
DOSSIER.mkdir(exist_ok=True)

with st.sidebar:
    st.header("⚙️ Données")
    st.info("Cette app exécute directement le moteur Python V4 sur son serveur, sans connexion à Colab.")
    collecter = st.button("1 · Charger / actualiser les fondamentaux", use_container_width=True,
                          help="La première collecte peut être longue et subir des limites Yahoo.")
    cours = st.button("2 · Actualiser les cours et scores", use_container_width=True)
    st.caption("Lance d'abord la collecte fondamentale, puis l'actualisation des cours. Les données enregistrées localement peuvent disparaître après redémarrage de l'hébergement gratuit.")
    st.divider()
    st.caption("Pondérations : P/E 20 %, marge 25 %, croissance 25 %, ROE 10 %, dette 20 %. Comparaisons sectorielles pour marge et croissance lorsque l'échantillon du secteur est suffisant.")

if collecter:
    with st.status("Récupération de la liste et des fondamentaux...", expanded=True) as statut:
        try:
            composants = moteur.obtenir_composants()
            fond = moteur.recuperer_fondamentaux(composants)
            statut.update(label=f"Collecte terminée : {len(fond)} fiches en cache", state="complete")
        except Exception as exc:
            statut.update(label="Collecte interrompue", state="error")
            st.error(f"Impossible de terminer la collecte : {exc}")

if cours:
    with st.spinner("Téléchargement des cours, calcul des scores..."):
        try:
            composants = moteur.obtenir_composants()
            fond = moteur.charger_fondamentaux()
            # N'exige pas que tous les fondamentaux aient été collectés.
            prix = moteur.derniers_cours(composants["Action"].tolist())
            classement = moteur.construire_classement(composants, fond, prix)
            classement.to_csv(F_EXPORT, index=False, encoding="utf-8-sig")
            st.success(f"Classement recalculé : {len(classement)} actions, {classement['Score /100'].notna().sum()} classables.")
        except Exception as exc:
            st.error(f"Actualisation impossible : {exc}")

if F_EXPORT.exists():
    try:
        df = pd.read_csv(F_EXPORT)
    except Exception as exc:
        st.error(f"Impossible de lire le classement : {exc}")
        st.stop()
    st.caption(f"Dernière génération du classement : {pd.Timestamp(F_EXPORT.stat().st_mtime, unit='s', tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}. Ce n'est pas l'heure de chaque cotation.")
else:
    st.info("Bienvenue ! Commence par « Charger / actualiser les fondamentaux » dans la barre latérale, puis « Actualiser les cours et scores ». La première collecte du S&P 500 peut prendre du temps.")
    st.stop()

for col in ["Score /100", "Prix USD", "Marge %", "Croissance %", "PE utilisé", "Couverture %"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

c1,c2,c3,c4 = st.columns(4)
c1.metric("Actions recensées", len(df))
c2.metric("Scores disponibles", int(df["Score /100"].notna().sum()))
c3.metric("Cours disponibles", int(df["Prix USD"].notna().sum()))
c4.metric("Secteurs", int(df["Secteur"].nunique()))

st.subheader("🔎 Explorer les actions")
f1,f2,f3 = st.columns([2,2,1])
recherche = f1.text_input("Action ou entreprise", placeholder="Ex. NVDA, Apple...")
secteurs = sorted(df["Secteur"].dropna().unique().tolist())
choisis = f2.multiselect("Secteurs", secteurs, default=[])
min_score = f3.slider("Score minimum", 0,100,0)
vue = df.copy()
if recherche:
    vue = vue[vue["Action"].astype(str).str.contains(recherche, case=False, regex=False) | vue["Entreprise"].astype(str).str.contains(recherche, case=False, regex=False)]
if choisis:
    vue=vue[vue["Secteur"].isin(choisis)]
vue=vue[vue["Score /100"].fillna(-1)>=min_score]
vue=vue.sort_values("Score /100",ascending=False,na_position="last")
colonnes = [c for c in ["Action","Entreprise","Secteur","Prix USD","PE utilisé","Marge %","Croissance %","ROE %","Dette/capitaux propres %","Score /100","Couverture %","Âge cotation (min)","Âge fondamentaux (jours)","Statut"] if c in vue.columns]
st.dataframe(vue[colonnes],hide_index=True,use_container_width=True,height=450)

onglet1,onglet2,onglet3=st.tabs(["📊 Classement sectoriel","⚖️ Comparer deux actions","📥 Télécharger"])
with onglet1:
    valides=vue.dropna(subset=["Score /100"])
    if len(valides):
        top=valides.head(25).sort_values("Score /100")
        fig=px.bar(top,x="Score /100",y="Action",orientation="h",color="Secteur",hover_data=["Entreprise"],title="25 meilleurs scores parmi les filtres")
        fig.update_layout(height=660,legend_title="Secteur")
        st.plotly_chart(fig,use_container_width=True)
    else:
        st.info("Aucun score disponible pour ces filtres.")
with onglet2:
    options=df["Action"].dropna().astype(str).tolist()
    if len(options)>=2:
        x,y=st.columns(2)
        action1=x.selectbox("Première action",options,index=0)
        action2=y.selectbox("Deuxième action",options,index=min(1,len(options)-1))
        st.dataframe(df[df["Action"].isin([action1,action2])][colonnes],hide_index=True,use_container_width=True)
    else:
        st.info("Pas assez d'actions pour comparer.")
with onglet3:
    st.download_button("Télécharger le classement CSV", data=df.to_csv(index=False).encode("utf-8-sig"),file_name="classement_sp500.csv",mime="text/csv")
    st.caption("Le CSV contient des données de recherche; vérifie leur qualité, leur date et les éventuelles lacunes avant utilisation.")

st.divider()
st.caption("Limites : seuils expérimentaux, échantillon sectoriel S&P 500, absence de backtest, données Yahoo potentiellement retardées. Streamlit Community Cloud ne fournit pas ici une collecte planifiée permanente.")
