from flask import Flask, render_template, request
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import plotly
import plotly.express as px
import json
from geopy.distance import geodesic

app = Flask(__name__)

# Coordonnées GPS de Nema (chef-lieu)
nema_coords = (16.6167, -7.2500)  # Exemple de coordonnées

def clean_text_column(series):
    return series.apply(lambda x: str(x) if pd.notnull(x) else '')

@app.route('/', methods=['GET', 'POST'])
def index():
    # Charger les données depuis le fichier Excel
    file_path = 'Enq_H_Chargui_a_corige.xlsx'
    data = pd.read_excel(file_path)

    # Nettoyer les données : supprimer les lignes avec des valeurs manquantes dans 'Nom du point de vaccinatio'
    data_clean = data.dropna(subset=['Nom du point de vaccinatio'])

    # Calculer les statistiques générales
    total_enfants_vaccination = data_clean["Nombre d'enfants en âge de vaccination"].sum()
    total_enfants_vaccines = total_enfants_vaccination - data_clean["Nombre d'enfants (zéro dose)"].sum()
    total_enfants_zero_dose = data_clean["Nombre d'enfants (zéro dose)"].sum()
    moyenne_enfants_vaccination = data_clean["Nombre d'enfants en âge de vaccination"].mean()
    moyenne_enfants_zero_dose = data_clean["Nombre d'enfants (zéro dose)"].mean()

    # Compter le nombre total de points de santé
    nombre_points_sante = len(data_clean)
    nombre_communes = data_clean['Commune'].nunique()

    # Obtenir les listes des points de santé, des communes, et des enquêteurs
    points_sante = ['Tous'] + sorted(data_clean['Nom du point de vaccinatio'].unique().tolist())
    communes = ['Tous'] + sorted(data_clean['Commune'].unique().tolist())
    enqueteurs = ['Tous'] + sorted(data_clean['Nom du responsable'].unique().tolist())

    # Vérifiez si les colonnes 'Numéro WhatsApp' existent
    whatsapps = ['Tous']
    if 'Numéro WhatsApp' in data_clean.columns:
        whatsapps += sorted(data_clean['Numéro WhatsApp'].unique().tolist())

    # Filtrer les données en fonction des sélections de l'utilisateur
    selected_point = request.form.get('point_sante', 'Tous')
    selected_commune = request.form.get('commune', 'Tous')
    selected_enqueteur = request.form.get('enqueteur', 'Tous')
    selected_whatsapp = request.form.get('whatsapp', 'Tous')

    # Filtrer les données
    filtered_data = data_clean
    if selected_point != 'Tous':
        filtered_data = filtered_data[filtered_data['Nom du point de vaccinatio'] == selected_point]
    if selected_commune != 'Tous':
        filtered_data = filtered_data[filtered_data['Commune'] == selected_commune]
    if selected_enqueteur != 'Tous':
        filtered_data = filtered_data[filtered_data['Nom du responsable'] == selected_enqueteur]
    if selected_whatsapp != 'Tous' and 'Numéro WhatsApp' in data_clean.columns:
        filtered_data = filtered_data[filtered_data['Numéro WhatsApp'] == selected_whatsapp]

    # Calculer les statistiques par point de santé
    stats_par_point = filtered_data.groupby('Nom du point de vaccinatio').agg({
        'Nombre d\'enfants en âge de vaccination': 'sum',
        'Nombre d\'enfants (zéro dose)': 'sum',
        "Source d'énergie de l'unité": lambda x: ', '.join(clean_text_column(x).unique())
    }).reset_index()

    # Calculer les statistiques par commune
    stats_par_commune = filtered_data.groupby('Commune').agg({
        'Nombre d\'enfants en âge de vaccination': 'sum',
        'Nombre d\'enfants (zéro dose)': 'sum',
        "Source d'énergie de l'unité": lambda x: ', '.join(clean_text_column(x).unique())
    }).reset_index()

    # Ajouter les défis et solutions
    defis_solutions_par_point = filtered_data.groupby('Nom du point de vaccinatio').agg({
        'Quels sont les principaux défis que vous rencontrez ?': lambda x: ', '.join(clean_text_column(x).unique()),
        'Quelles sont vos propositions de solutions ?': lambda x: ', '.join(clean_text_column(x).unique())
    }).reset_index()

    defis_solutions_par_commune = filtered_data.groupby('Commune').agg({
        'Quels sont les principaux défis que vous rencontrez ?': lambda x: ', '.join(clean_text_column(x).unique()),
        'Quelles sont vos propositions de solutions ?': lambda x: ', '.join(clean_text_column(x).unique())
    }).reset_index()

    # Convertir les statistiques en dictionnaire pour les passer au template
    stats_par_point_dict = stats_par_point.to_dict(orient='records')
    stats_par_commune_dict = stats_par_commune.to_dict(orient='records')
    defis_solutions_par_point_dict = defis_solutions_par_point.to_dict(orient='records')
    defis_solutions_par_commune_dict = defis_solutions_par_commune.to_dict(orient='records')

    # Créer un graphique avec Plotly pour les points de santé
    fig_point = px.bar(stats_par_point, x='Nom du point de vaccinatio',
                       y=['Nombre d\'enfants en âge de vaccination', 'Nombre d\'enfants (zéro dose)'],
                       title='Statistiques par Point de Santé', barmode='group')
    graphJSON_point = json.dumps(fig_point, cls=plotly.utils.PlotlyJSONEncoder)

    # Créer un graphique avec Plotly pour les communes
    fig_commune = px.bar(stats_par_commune, x='Commune',
                         y=['Nombre d\'enfants en âge de vaccination', 'Nombre d\'enfants (zéro dose)'],
                         title='Statistiques par Commune', barmode='group')
    graphJSON_commune = json.dumps(fig_commune, cls=plotly.utils.PlotlyJSONEncoder)

    # Filtrer les données pour ne garder que celles avec des coordonnées GPS valides
    filtered_data_with_gps = filtered_data.dropna(subset=['_Localisation GPS du point_latitude', '_Localisation GPS du point_longitude'])

    # Créer une carte GPS avec Folium
    if not filtered_data_with_gps.empty:
        m = folium.Map(location=[filtered_data_with_gps['_Localisation GPS du point_latitude'].mean(),
                                  filtered_data_with_gps['_Localisation GPS du point_longitude'].mean()],
                       zoom_start=6)
        marker_cluster = MarkerCluster().add_to(m)

        # Calculer les distances entre chaque point et Nema
        filtered_data_with_gps['Distance à Nema (km)'] = filtered_data_with_gps.apply(
            lambda row: geodesic((row['_Localisation GPS du point_latitude'], row['_Localisation GPS du point_longitude']), nema_coords).km, axis=1)

        for idx, row in filtered_data_with_gps.iterrows():
            folium.Marker(
                location=[row['_Localisation GPS du point_latitude'], row['_Localisation GPS du point_longitude']],
                popup=f"""
                <b>Nom du point:</b> {row['Nom du point de vaccinatio']}<br>
                <b>Commune:</b> {row.get('Commune', '')}<br>
                <b>Responsable:</b> {row.get('Nom du responsable', '')}<br>
                <b>WhatsApp:</b> {row.get('Numéro WhatsApp', '')}<br>
                <b>Enfants en âge de vaccination:</b> {row.get("Nombre d'enfants en âge de vaccination", '')}<br>
                <b>Enfants zéro dose:</b> {row.get("Nombre d'enfants (zéro dose)", '')}<br>
                <b>Source d'énergie:</b> {row.get("Source d'énergie de l'unité", '')}<br>
                <b>Distance à Nema:</b> {row.get('Distance à Nema (km)', ''):.2f} km
                """,
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(marker_cluster)

        m.save('templates/map.html')
        with open('templates/map.html', 'r', encoding='utf-8') as f:
            map_html = f.read()
    else:
        map_html = "<p>Aucune donnée GPS valide disponible pour afficher la carte.</p>"

    # Statistiques générales
    stats_generales = {
        'Total enfants en âge de vaccination': total_enfants_vaccination,
        'Total enfants vaccinés': total_enfants_vaccines,
        'Total enfants zéro dose': total_enfants_zero_dose,
        'Moyenne enfants en âge de vaccination': round(moyenne_enfants_vaccination, 2),
        'Moyenne enfants zéro dose': round(moyenne_enfants_zero_dose, 2),
        'Nombre de points de santé': nombre_points_sante,
        'Nombre de communes': nombre_communes
    }

    return render_template('index.html', stats_generales=stats_generales,
                           stats_par_point=stats_par_point_dict, points_sante=points_sante,
                           stats_par_commune=stats_par_commune_dict, communes=communes,
                           selected_point=selected_point, selected_commune=selected_commune,
                           graphJSON_point=graphJSON_point, graphJSON_commune=graphJSON_commune,
                           map_html=map_html, whatsapps=whatsapps, selected_whatsapp=selected_whatsapp,
                           enqueteurs=enqueteurs, selected_enqueteur=selected_enqueteur,
                           defis_solutions_par_point=defis_solutions_par_point_dict,
                           defis_solutions_par_commune=defis_solutions_par_commune_dict)

if __name__ == '__main__':
    app.run(debug=True)
