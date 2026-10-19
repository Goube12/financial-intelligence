"""Modèle V4 S&P 500 : prototype d'analyse financière éducatif.

Exécution recommandée : Google Colab. Les cotations Yahoo peuvent être différées.
Les résultats ne constituent pas des recommandations d'investissement.
"""
from __future__ import annotations

import io
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from IPython.display import display, clear_output

# -------------------- PARAMÈTRES À MODIFIER --------------------
DOSSIER = Path('modele_v4_cache')
DOSSIER.mkdir(exist_ok=True)
CACHE_FONDAMENTAUX = DOSSIER / 'fondamentaux.csv'
CACHE_COMPOSANTS = DOSSIER / 'sp500.csv'
CACHE_META = DOSSIER / 'meta.json'
DUREE_CACHE_FONDAMENTAUX_HEURES = 168  # 7 jours : changer à 24 pour une recherche quotidienne
DUREE_CACHE_COMPOSANTS_HEURES = 24
TAILLE_LOT_COURS = 35
PAUSE_REQUETES_FONDAMENTALES = 0.6
NB_MIN_COMPARABLES_SECTEUR = 8
INTERVALLE_ACTUALISATION_SECONDES = 300
NB_ACTUALISATIONS = 1  # Mettre 12 pour environ 1 h, Colab doit rester actif

POIDS = {'PE': 0.20, 'Marge': 0.25, 'Croissance': 0.25,
         'ROE': 0.10, 'Dette': 0.20}
FINANCE_GICS = 'Financials'
WIKI = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'


def fichier_restant_valide(chemin: Path, heures: int) -> bool:
    return chemin.exists() and (time.time() - chemin.stat().st_mtime) < heures * 3600


def nombre_ou_nan(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else np.nan
    except (ValueError, TypeError):
        return np.nan


def obtenir_composants() -> pd.DataFrame:
    if fichier_restant_valide(CACHE_COMPOSANTS, DUREE_CACHE_COMPOSANTS_HEURES):
        return pd.read_csv(CACHE_COMPOSANTS, dtype={'Action': str})
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; educational notebook)'}
        page = requests.get(WIKI, headers=headers, timeout=30)
        page.raise_for_status()
        tables = pd.read_html(io.StringIO(page.text))
        table = next(t for t in tables if {'Symbol', 'Security', 'GICS Sector'}.issubset(t.columns))
        df = table[['Symbol', 'Security', 'GICS Sector']].rename(columns={
            'Symbol': 'Action', 'Security': 'Entreprise', 'GICS Sector': 'Secteur'
        }).copy()
        df['Action'] = df['Action'].str.strip().str.replace('.', '-', regex=False)
        df = df.dropna(subset=['Action']).drop_duplicates('Action')
        df.to_csv(CACHE_COMPOSANTS, index=False)
        return df.reset_index(drop=True)
    except Exception as exc:
        if CACHE_COMPOSANTS.exists():
            print(f'Liste S&P 500 indisponible ({exc}). Utilisation du cache local.')
            return pd.read_csv(CACHE_COMPOSANTS)
        raise RuntimeError('Impossible de récupérer la liste S&P 500. Réessayez plus tard.') from exc


def charger_fondamentaux() -> pd.DataFrame:
    if CACHE_FONDAMENTAUX.exists():
        df = pd.read_csv(CACHE_FONDAMENTAUX)
        if 'Action' in df:
            return df.drop_duplicates('Action', keep='last')
    return pd.DataFrame(columns=['Action', 'BPA', 'PE fourni', 'Marge', 'Croissance', 'ROE', 'Dette', 'Collecte UTC'])


def recuperer_fondamentaux(composants: pd.DataFrame) -> pd.DataFrame:
    """Reprend la collecte et sauvegarde tous les 10 titres. Ne fabrique pas les manquants."""
    ancien = charger_fondamentaux()
    existants = ancien.set_index('Action').to_dict('index') if not ancien.empty else {}
    nouveau = dict(existants)
    maintenant = pd.Timestamp.now(tz='UTC')
    a_actualiser = []
    for symbole in composants['Action']:
        entree = existants.get(symbole, {})
        date = pd.to_datetime(entree.get('Collecte UTC'), errors='coerce', utc=True)
        if pd.isna(date) or (maintenant - date).total_seconds() >= DUREE_CACHE_FONDAMENTAUX_HEURES * 3600:
            a_actualiser.append(symbole)
    print(f'Données fondamentales : {len(composants) - len(a_actualiser)} déjà en cache, '
          f'{len(a_actualiser)} à collecter/actualiser.')
    for i, symbole in enumerate(a_actualiser, 1):
        try:
            infos = yf.Ticker(symbole).info
            if not isinstance(infos, dict) or not infos:
                raise ValueError('fiche vide')
            entree = {
                'Action': symbole,
                'BPA': nombre_ou_nan(infos.get('trailingEps')),
                'PE fourni': nombre_ou_nan(infos.get('trailingPE')),
                'Marge': nombre_ou_nan(infos.get('profitMargins')),
                'Croissance': nombre_ou_nan(infos.get('revenueGrowth')),
                'ROE': nombre_ou_nan(infos.get('returnOnEquity')),
                'Dette': nombre_ou_nan(infos.get('debtToEquity')),
                'Collecte UTC': maintenant.isoformat(),
            }
            nouveau[symbole] = entree
        except Exception as exc:
            print(f'  {symbole} : indisponible ({type(exc).__name__})')
            # Ne pas inventer de données ; un cache ancien peut être conservé, avec date visible.
        if i % 10 == 0 or i == len(a_actualiser):
            pd.DataFrame(list(nouveau.values())).to_csv(CACHE_FONDAMENTAUX, index=False)
            print(f'  Progression fondamentaux : {i}/{len(a_actualiser)}')
        time.sleep(PAUSE_REQUETES_FONDAMENTALES)
    if not CACHE_FONDAMENTAUX.exists():
        pd.DataFrame(list(nouveau.values()), columns=['Action', 'BPA', 'PE fourni', 'Marge', 'Croissance', 'ROE', 'Dette', 'Collecte UTC']).to_csv(CACHE_FONDAMENTAUX, index=False)
    return charger_fondamentaux()


def derniers_cours(symboles: list[str]) -> pd.DataFrame:
    lignes = []
    for debut in range(0, len(symboles), TAILLE_LOT_COURS):
        lot = symboles[debut: debut + TAILLE_LOT_COURS]
        try:
            donnees = yf.download(
                tickers=lot, period='5d', interval='5m', group_by='ticker',
                auto_adjust=False, multi_level_index=True, progress=False,
                threads=5, timeout=20
            )
            if donnees is None or donnees.empty:
                continue
            for symbole in lot:
                try:
                    bloc = donnees[symbole] if isinstance(donnees.columns, pd.MultiIndex) else donnees
                    cours = pd.to_numeric(bloc['Close'], errors='coerce').dropna()
                    if cours.empty:
                        continue
                    ts = pd.Timestamp(cours.index[-1])
                    if ts.tzinfo is None:
                        ts = ts.tz_localize('America/New_York')
                    ts = ts.tz_convert('UTC')
                    lignes.append({'Action': symbole, 'Prix USD': float(cours.iloc[-1]),
                                   'Dernière cotation UTC': ts.isoformat()})
                except (KeyError, TypeError, IndexError, ValueError):
                    continue
        except Exception as exc:
            print(f'Lot cours {debut // TAILLE_LOT_COURS + 1}: {type(exc).__name__}')
        time.sleep(0.8)
    return pd.DataFrame(lignes, columns=['Action', 'Prix USD', 'Dernière cotation UTC'])


def note_absolue(valeur, seuils, inverse=False):
    v = nombre_ou_nan(valeur)
    if pd.isna(v):
        return np.nan
    return 25 * sum(v <= s if inverse else v >= s for s in seuils)


def scores_secteur(frame: pd.DataFrame, colonne: str, seuils_defaut: list[float],
                    titre: str) -> pd.Series:
    """Percentile de comparaison, seulement si >= 8 valeurs valides dans le secteur."""
    base = frame[colonne].apply(nombre_ou_nan)
    notes = pd.Series(index=frame.index, dtype=float)
    for _, indexes in frame.groupby('Secteur').groups.items():
        valeurs = base.loc[indexes].dropna()
        if len(valeurs) >= NB_MIN_COMPARABLES_SECTEUR:
            # (rank-1)/(n-1) : 0 = moins bon, 100 = meilleur
            rang = valeurs.rank(method='average', ascending=True)
            notes.loc[valeurs.index] = (100 * (rang - 1) / (len(valeurs) - 1)).round(2)
        else:
            notes.loc[indexes] = base.loc[indexes].apply(
                lambda x: note_absolue(x, seuils_defaut)
            )
    return notes


def construire_classement(composants: pd.DataFrame, fondamentaux: pd.DataFrame,
                           cours: pd.DataFrame) -> pd.DataFrame:
    tableau = composants.merge(fondamentaux, on='Action', how='left')
    tableau = tableau.merge(cours, on='Action', how='left')
    for cle in ('BPA', 'PE fourni', 'Marge', 'Croissance', 'ROE', 'Dette', 'Prix USD'):
        tableau[cle] = pd.to_numeric(tableau[cle], errors='coerce')
    # Recalcule P/E sur le dernier cours quand le BPA positif est disponible.
    pe_recalcule = tableau['Prix USD'] / tableau['BPA']
    condition_pe = (tableau['BPA'] > 0) & (tableau['Prix USD'] > 0)
    tableau['PE utilisé'] = pe_recalcule.where(condition_pe, tableau['PE fourni'])
    tableau['Source PE'] = np.where(condition_pe, 'Cours / BPA',
                                    np.where(tableau['PE fourni'].notna(), 'PE fourni', 'Absent'))
    # BPA <= 0 : pas de P/E pertinent. Pénalisation plutôt qu'ignorer la perte.
    perte = tableau['BPA'].notna() & (tableau['BPA'] <= 0)
    tableau.loc[perte, 'PE utilisé'] = np.nan
    tableau.loc[perte, 'Source PE'] = 'BPA <= 0'

    tableau['Note PE'] = tableau['PE utilisé'].apply(
        lambda x: note_absolue(x, [40, 30, 20, 10], inverse=True))
    tableau.loc[perte, 'Note PE'] = 0
    tableau['Note Marge'] = scores_secteur(
        tableau, 'Marge', [0.05, 0.10, 0.20, 0.30], 'Marge')
    tableau['Note Croissance'] = scores_secteur(
        tableau, 'Croissance', [0, 0.05, 0.10, 0.20], 'Croissance')
    tableau['Note ROE'] = tableau['ROE'].apply(
        lambda x: note_absolue(x, [0.05, 0.10, 0.15, 0.25]))
    tableau['Note Dette'] = tableau['Dette'].apply(
        lambda x: note_absolue(x, [200, 100, 50, 25], inverse=True)
        if pd.notna(x) and x >= 0 else np.nan)
    # Dette/capitaux propres n'est pas une notation pertinente pour les financières.
    tableau.loc[tableau['Secteur'] == FINANCE_GICS, 'Note Dette'] = np.nan

    criteres = list(POIDS)
    for cle in criteres:
        tableau[f'Note {cle}'] = pd.to_numeric(tableau[f'Note {cle}'], errors='coerce')
    notes = pd.DataFrame({c: tableau[f'Note {c}'] for c in criteres})
    disponibles = notes.notna()
    poids_actifs = disponibles.mul(pd.Series(POIDS), axis=1)
    couverture = poids_actifs.sum(axis=1)
    points = notes.fillna(0).mul(pd.Series(POIDS), axis=1).sum(axis=1)
    tableau['Couverture %'] = (couverture * 100).round(0)
    tableau['Indicateurs'] = disponibles.sum(axis=1)
    # Ne pas classer si moins de 70 % des poids théoriques sont couverts.
    tableau['Score /100'] = (points / couverture.where(couverture >= 0.70)).round(1)
    tableau['Statut'] = np.where(tableau['Score /100'].notna(), 'Classable', 'Données insuffisantes')
    tableau['Marge %'] = (tableau['Marge'] * 100).round(1)
    tableau['Croissance %'] = (tableau['Croissance'] * 100).round(1)
    tableau['ROE %'] = (tableau['ROE'] * 100).round(1)
    tableau['Dette/capitaux propres %'] = tableau['Dette'].round(1)
    moyenne = tableau.groupby('Secteur')['Marge %'].transform('mean')
    tableau['Marge moyenne secteur %'] = moyenne.round(1)
    tableau['Écart marge (points)'] = (tableau['Marge %'] - moyenne).round(1)
    tableau['Rang marge secteur'] = tableau.groupby('Secteur')['Marge %'].rank(
        ascending=False, method='min').astype('Int64')
    tableau['Nb sociétés secteur'] = tableau.groupby('Secteur')['Action'].transform('count')
    tableau['Âge cotation (min)'] = (
        (pd.Timestamp.now(tz='UTC') - pd.to_datetime(tableau['Dernière cotation UTC'], utc=True))
        .dt.total_seconds().div(60).round(0))
    tableau['Âge fondamentaux (jours)'] = (
        (pd.Timestamp.now(tz='UTC') - pd.to_datetime(tableau['Collecte UTC'], utc=True))
        .dt.total_seconds().div(86400).round(1))
    return tableau.sort_values('Score /100', ascending=False, na_position='last').reset_index(drop=True)


COLONNES = [
    'Action', 'Entreprise', 'Secteur', 'Prix USD', 'Dernière cotation UTC',
    'Âge cotation (min)', 'PE utilisé', 'Source PE', 'Marge %', 'Croissance %',
    'ROE %', 'Dette/capitaux propres %', 'Score /100', 'Couverture %',
    'Indicateurs', 'Statut', 'Rang marge secteur', 'Nb sociétés secteur',
    'Marge moyenne secteur %', 'Écart marge (points)', 'Âge fondamentaux (jours)'
]


def afficher_et_exporter(resultat: pd.DataFrame):
    print('Dernière récupération (UTC) :', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    print('Actions dans la liste :', len(resultat))
    print('Scores calculables :', resultat['Score /100'].notna().sum())
    print('Cours récupérés :', resultat['Prix USD'].notna().sum())
    print('Attention : scores expérimentaux, et cotations potentiellement différées.')
    display(resultat[COLONNES].head(30))
    print('\nTOP 10 PAR SECTEUR')
    for secteur, groupe in resultat.groupby('Secteur'):
        print('\n', secteur)
        display(groupe[COLONNES].head(10))
    resultat.to_csv('classement_sp500_v4.csv', index=False, encoding='utf-8-sig')
    print('\nFichier enregistré : classement_sp500_v4.csv')


def executer_v4(nb_actualisations=NB_ACTUALISATIONS, pause=INTERVALLE_ACTUALISATION_SECONDES):
    composants = obtenir_composants()
    print('Constituants récupérés :', len(composants), '(peut dépasser 500 : catégories d’actions)')
    fondamentaux = recuperer_fondamentaux(composants)
    for tour in range(nb_actualisations):
        cours = derniers_cours(composants['Action'].tolist())
        resultat = construire_classement(composants, fondamentaux, cours)
        clear_output(wait=True)
        print(f'Actualisation {tour + 1}/{nb_actualisations}')
        afficher_et_exporter(resultat)
        if tour < nb_actualisations - 1:
            time.sleep(pause)
    return resultat


if __name__ == '__main__':
    classement_v4 = executer_v4()
