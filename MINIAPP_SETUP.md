# Telegram Mini App setup

The Mini App is served by the same process as the bot and reads the same SQLite
database. Deploy the bot and Mini App together, with the existing persistent
`/app/data` volume mounted for the database.

Use the repository `Dockerfile` for deployment. It runs `python bot.py`; do not
set a Node.js build or start command. The Mini App's `app.js` is a browser
script, not a Node server entry point.

Set `MINI_APP_URL` to the public HTTPS root URL of the deployed service, for
example `https://dating.example.com`. The hosting platform should pass its
assigned listening port in `PORT`; the app binds to `0.0.0.0` on that port.
The Mini App button is added to the bot's main keyboard when `MINI_APP_URL` is
configured. Restart the bot and send `/start` to refresh the keyboard.

Install dependencies from `requirements.txt` when deploying. The web server
also exposes `/healthz` for a hosting-platform health check.

Run exactly one bot process for this bot token. Multiple replicas or a second
polling service can compete for Telegram `getUpdates` and cause flood control.

Telegram's signed `initData` is verified by the server on every API request.
Requests without a valid Telegram launch context are rejected. Profile
discovery, likes, matches, and messages use the same database tables as the
bot, so matches and chat history stay shared. The Mini App also lets users edit
their name, city, and description; profile photos can still be changed in the
Telegram bot. Deleting a match from the Mini App removes its shared match and
message records, so the chat disappears from both the app and bot.
Profile statistics show current matches and the lifetime number of received
likes. Existing likes are used as the initial count during migration; likes
removed before this counter existed cannot be reconstructed. Search gender and
age-range preferences can be updated from the discovery tab and are shared with
the Telegram bot. Discovery settings open in a bottom sheet, and the light/dark
theme choice is saved in the user's Mini App browser storage.
