# Financial Intelligence

Prototype éducatif Streamlit pour explorer les actions du S&P 500 à partir du moteur financier V4. Les cours Yahoo Finance peuvent être différés et les scores ne constituent pas des recommandations d’investissement.

## Lancer l’application

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Dans la barre latérale, lancez d’abord la collecte des fondamentaux, puis l’actualisation des cours et des scores. La collecte initiale peut prendre du temps et être limitée par Yahoo Finance.

## Déploiement

Sur Streamlit Community Cloud, sélectionnez ce dépôt et `app.py` comme fichier d’entrée. Le cache est local et peut disparaître après un redémarrage ou une reconstruction. L’application ne fournit pas de collecte planifiée permanente.

## Limites

- Les seuils de notation sont expérimentaux; les comparaisons sectorielles utilisent l’échantillon disponible du S&P 500.
- Les données peuvent être incomplètes, retardées ou indisponibles; vérifiez leur qualité et leur date avant toute utilisation.
- Il n’y a pas de backtest ni de base de données persistante.
