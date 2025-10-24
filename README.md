# Popsink Mintlify Migration 🚀

Ce package contient la documentation Popsink migrée de MkDocs vers Mintlify.

## 📦 Contenu

- ✅ **20+ fichiers .mdx** migrés avec le design Mintlify
- ✅ **docs.json** complet avec navigation structurée
- ✅ **Structure de dossiers** organisée
- ✅ **Composants Mintlify** (Cards, Accordions, Steps, etc.)

## 📂 Structure

```
mintlify-docs/
├── docs.json                    # Configuration Mintlify
├── introduction.mdx             # Page d'accueil
├── quickstart.mdx               # Guide de démarrage
├── connectors/
│   ├── sources/
│   │   ├── overview.mdx
│   │   ├── postgres.mdx
│   │   ├── mysql.mdx
│   │   ├── bigquery.mdx
│   │   ├── salesforce.mdx
│   │   └── attio.mdx
│   └── targets/
│       ├── overview.mdx
│       ├── bigquery.mdx
│       ├── clickhouse.mdx
│       ├── mongodb.mdx
│       └── slack.mdx
├── features/
│   ├── alerting.mdx
│   └── deployment.mdx
├── snowflake-ibmi/
│   └── quickstart.mdx
├── on-prem/
│   └── overview.mdx
└── images/                      # Dossier pour vos images
```

## 🚀 Installation

### 1. Copier dans votre repo local

```bash
# Sur votre Mac
cd ~/Documents/mintmig/docs/

# Extraire le ZIP (téléchargé depuis Claude)
unzip popsink-mintlify-docs.zip

# Copier le contenu
cp -r mintlify-docs/* .
```

### 2. Tester localement

```bash
# Installer Mintlify CLI si ce n'est pas déjà fait
npm i -g mintlify

# Démarrer le serveur de dev
mint dev
```

Ouvrez http://localhost:3000 dans votre navigateur.

### 3. Pousser vers GitHub

```bash
cd ~/Documents/mintmig/docs/

# Vérifier les changements
git status

# Ajouter tous les fichiers
git add .

# Commit
git commit -m "feat: migrate documentation from MkDocs to Mintlify

- Converted 20+ .md files to .mdx format
- Added Mintlify components (Cards, Accordions, Steps)
- Structured navigation with docs.json
- Improved documentation design and UX"

# Pousser vers votre repo de migration
git push origin main
```

### 4. Créer une Pull Request vers le repo client

```bash
# Ajouter le repo client comme remote (si pas déjà fait)
git remote add upstream git@github.com:Popsink/docs.git

# Pousser vers une nouvelle branche
git checkout -b feature/mintlify-migration
git push origin feature/mintlify-migration

# Créer une PR sur GitHub vers Popsink/docs
```

## ✅ Ce qui est migré

### Pages Principales
- ✅ Introduction (ex-index.md)
- ✅ Quickstart
- ✅ Sources Overview (ex-source.md)
- ✅ Targets Overview (ex-target.md)
- ✅ Alerting
- ✅ Deployment Options

### Source Connectors
- ✅ PostgreSQL
- ✅ MySQL
- ✅ BigQuery
- ✅ Salesforce
- ✅ Attio

### Target Connectors
- ✅ BigQuery
- ✅ ClickHouse
- ✅ MongoDB
- ✅ Slack

### Sections Spéciales
- ✅ Snowflake IBMi Quickstart
- ✅ On-Prem Overview

## 📝 À compléter

Les fichiers suivants n'ont pas encore été migrés (vous pouvez les ajouter plus tard) :

- [ ] Autres source connectors (Oracle, HubSpot, Kafka, etc.)
- [ ] Autres target connectors (Snowflake, Postgres, Oracle, Airtable, etc.)
- [ ] Pages Snowflake IBMi (db2_setup.mdx, journaling.mdx)
- [ ] On-Prem API guide complète
- [ ] Changelog pages
- [ ] API Reference complète

## 🎨 Personnalisation

### Logo
Placez vos logos dans `/logo/`:
- `dark.svg` - Logo pour le thème sombre
- `light.svg` - Logo pour le thème clair

### Couleurs
Modifiez les couleurs dans `docs.json` :
```json
"colors": {
  "primary": "#000000",
  "light": "#FFFFFF",
  "dark": "#000000"
}
```

### Navigation
Ajoutez de nouvelles pages dans `docs.json` section `navigation`.

## 🐛 Troubleshooting

### `mint dev` ne fonctionne pas
```bash
# Réinstaller Mintlify CLI
npm uninstall -g mintlify
npm i -g mintlify

# Vérifier la version
mint --version
```

### Les images ne s'affichent pas
- Placez toutes les images dans `/images/`
- Référencez-les avec `/images/votre-image.png`

### Erreur de parsing dans docs.json
- Validez le JSON sur https://jsonlint.com
- Vérifiez les virgules et accolades

## 📞 Support

- **Documentation Mintlify** : https://mintlify.com/docs
- **Popsink** : support@popsink.com

## 🎉 Migration complétée !

Vous êtes maintenant prêt à utiliser votre nouvelle documentation Mintlify !

**Bon travail ! 🚀**
