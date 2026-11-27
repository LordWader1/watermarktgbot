# A Advanced Video Watermark TG Bot 

## Deploy Button
Replace `REPLACE_WITH_GITHUB_USERNAME/REPLACE_WITH_REPOSITORY` in `app.json`
with the public GitHub mirror that contains this project. The Heroku Button
cannot use the GitLab URL as its template source.

Use this badge in the README after replacing the GitHub path:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://www.heroku.com/deploy?template=https://github.com/REPLACE_WITH_GITHUB_USERNAME/REPLACE_WITH_REPOSITORY)

## Bot Features
📍 Position: Your Text Positin

🔠 Font Size: 24px to 120px

🎨 Color: any colour

💧 Opacity: 0 to 100%

🎞 Mode: 📌 Static / Moving or Scrolling


##  Required Config Variables

- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `OWNER_ID`
* Optional Configs
   `MONGO_URI`, `DB_NAME`, `LOG_CHANNEL`, `FORCE_SUB_CHANNEL`,
`MAX_CONCURRENT_JOBS`, `MAX_USER_QUEUE`, `MIN_FREE_DISK_MB`.


After deployment, open Heroku Dashboard → app → Resources and ensure the
`worker` process is running. This is a Telegram long-polling bot; it does not
need a `web` dyno unless you add an HTTP endpoint.

## Important limitations

The app's code currently configures a 2 GiB application-level maximum, but
that does not guarantee Telegram, Heroku dyno memory/disk, network, or MTProto
transfer limits will permit every 2 GB file. Test with your target dyno and
Telegram account. Heroku's filesystem is ephemeral; temporary video files
must not be treated as permanent storage.

Never commit `.env`, bot tokens, API hashes, MongoDB credentials, or session
files. If a secret was ever committed, rotate it even if the file is later
deleted.

