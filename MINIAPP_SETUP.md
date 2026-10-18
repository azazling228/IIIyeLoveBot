# Telegram Mini App setup

The Mini App is served by the same process as the bot and reads the same SQLite
database. Deploy the bot and Mini App together, with the existing persistent
`/app/data` volume mounted for the database.

Set `MINI_APP_URL` to the public HTTPS root URL of the deployed service, for
example `https://dating.example.com`. The hosting platform should pass its
assigned listening port in `PORT`; the app binds to `0.0.0.0` on that port.
The Mini App button is added to the bot's main keyboard when `MINI_APP_URL` is
configured. Restart the bot and send `/start` to refresh the keyboard.

Install dependencies from `requirements.txt` when deploying. The web server
also exposes `/healthz` for a hosting-platform health check.

Telegram's signed `initData` is verified by the server on every API request.
Requests without a valid Telegram launch context are rejected. Profile
discovery, likes, matches, and messages use the same database tables as the
bot, so chats and message history stay shared.
