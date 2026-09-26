
# 🏍️ Radar BMW R nineT Suisse

Radar gratuit qui surveille périodiquement MotoScout24 et AutoScout24 et envoie une notification Telegram pour les nouvelles annonces correspondant aux critères.

## Critères
- Suisse
- BMW R nineT Pure
- BMW R 1200 NineT Pure
- BMW R 12 nineT
- année >= 2021
- kilométrage <= 10'000 km
- prix < CHF 14'000

## Important
GitHub Actions est gratuit pour les petits workflows publics, mais les horaires `cron` peuvent être décalés. Le système est donc conçu pour vérifier régulièrement, pas pour garantir une alerte à la seconde.

## Installation
1. Créer un dépôt GitHub **public** et y envoyer ces fichiers.
2. Créer un bot Telegram avec `@BotFather`.
3. Récupérer le token du bot.
4. Envoyer un premier message au bot.
5. Récupérer ton `chat_id` avec l'API Telegram.
6. Dans GitHub: Settings → Secrets and variables → Actions → New repository secret.
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
7. Activer Actions et lancer une première exécution manuellement.

Le fichier `seen.json` sert de mémoire : une annonce déjà signalée ne sera pas renotifiée.

## Limitation
Les sites peuvent modifier leur structure ou limiter les robots. Si cela arrive, il faut adapter le parseur.
