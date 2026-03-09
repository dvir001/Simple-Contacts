# Simple Contacts

Standalone directory integration service providing **MicroSIP JSON** and **Yealink XML** phone directory feeds from Azure AD employee data.

<img width="790" height="890" alt="image" src="https://github.com/user-attachments/assets/454cd2e0-0b3f-4219-9989-82cd56338fee" />
<img width="633" height="867" alt="image" src="https://github.com/user-attachments/assets/6612ebc1-7680-45de-894f-79cb14e35c04" />

## Features

- **Azure AD sync** – fetch employees directly from Microsoft Graph (same client-credentials flow as Simple-Org-Chart)
- **MicroSIP JSON directory** – softphone-compatible contact feed
- **Yealink XML phonebook** – remote phonebook for Yealink desk phones (T31P, T33G, T46U, etc.)
- **Custom contacts** – append extra contacts not in Azure AD via the configure page
- **Number swaps** – find/replace rules applied to phone numbers before export (e.g. strip country prefix, remap extensions)
- **Azure AD SSO** – optional single sign-on via MSAL with password fallback
- **Docker-ready** – multi-stage Dockerfile with Gunicorn

## Quick Start

### Docker (recommended)

```bash
cp .env.template .env        # edit APP_PASSWORD & SECRET_KEY
docker compose up -d --build
```

The app will be available at `http://localhost:5000`.

### Local Development

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.template .env
python -m simple_contacts.app_main
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Flask session secret |
| `APP_PASSWORD` | `admin` | Login password (fallback when SSO is off) |
| `PORT` | `5000` | Server port |
| `GUNICORN_WORKERS` | `2` | Gunicorn worker count |
| `AZURE_TENANT_ID` | _(none)_ | Azure AD tenant ID (optional – Graph sync) |
| `AZURE_CLIENT_ID` | _(none)_ | App registration client ID (optional) |
| `AZURE_CLIENT_SECRET` | _(none)_ | App registration client secret (optional) |
| `GRAPH_API_ENDPOINT` | `https://graph.microsoft.com/v1.0` | Graph API base URL (optional) |
| `SSO_TENANT_ID` | _(none)_ | Azure AD tenant for SSO (optional) |
| `SSO_CLIENT_ID` | _(none)_ | SSO app registration client ID (optional) |
| `SSO_CLIENT_SECRET` | _(none)_ | SSO app registration client secret (optional) |
| `SSO_REDIRECT_PATH` | `/auth/callback` | SSO redirect URI path (optional) |
| `MAX_CUSTOM_CONTACTS` | `200` | Maximum custom directory contacts |

### Azure AD Setup (Graph sync)

1. Create an **App Registration** in Azure Portal.
2. Grant **Application** permission `User.Read.All` and admin-consent it.
3. Create a client secret.
4. Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` in `.env`.
5. Use the **Sync Now** button on the configure page to pull employees.

### Azure AD SSO (optional)

1. Create a **separate** App Registration for SSO.
2. Add a **Web** redirect URI: `https://your-domain/auth/callback`.
3. Grant **Delegated** permission `User.Read`.
4. Create a client secret.
5. Set `SSO_TENANT_ID`, `SSO_CLIENT_ID`, and `SSO_CLIENT_SECRET` in `.env`.
6. When configured, the password login form is auto-disabled.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | No | Health check |
| `GET/POST` | `/api/settings` | Yes | Read / update settings |
| `GET/DELETE` | `/api/employees` | Yes | Read / clear synced employees |
| `GET` | `/api/azure/status` | Yes | Check if Azure AD credentials are set |
| `POST` | `/api/azure/sync` | Yes | Fetch employees from Microsoft Graph |
| `GET` | `/directory/<name>.json` | No | MicroSIP JSON feed |
| `GET` | `/directory/<name>.xml` | No | Yealink XML feed |

## Running Tests

```bash
pip install pytest
pytest
```

## Project Structure

```
Simple-Contacts/
├── simple_contacts/       # Python package
│   ├── app_main.py        # Flask application
│   ├── auth.py            # Authentication (SSO + password)
│   ├── config.py          # Paths & configuration
│   ├── data_update.py     # Azure AD sync helpers
│   ├── exports.py         # MicroSIP / Yealink builders
│   ├── msgraph.py         # Microsoft Graph API client
│   ├── scheduler.py       # Background sync scheduler
│   ├── settings.py        # Settings load/save
│   └── utils/
├── static/                # Front-end assets
│   ├── configure.css
│   ├── configure.js
│   ├── i18n.js
│   └── locales/en-US.json
├── templates/             # Jinja2 templates
│   ├── configure.html
│   └── login.html
├── tests/                 # Pytest suite
├── deploy/                # Gunicorn config
├── data/                  # Runtime data (gitignored)
├── Dockerfile
├── docker-compose.yml
├── docker-compose-dev.yml
├── requirements.txt
└── pyproject.toml
```

## License

MIT
